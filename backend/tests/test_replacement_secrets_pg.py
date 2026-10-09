"""Actual encrypted seed admission, group consistency, rotation and shared purge."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.cleanup.service import purge_unavailable_content
from app.db.crypto import KeyRing, ProtectedValue
from app.db.models import Document
from app.db.replacement_secrets import DocumentReplacementSecret
from app.db.rotate_keys import rotate_replacement_secrets
from app.transformations.service import load_preview
from tests.intake_support import _login
from tests.styles_support import decide, draft


def test_standins_scoped_secret_rotation_and_purge(intake_site, monkeypatch):
    owner, _, engine, workspace, actor = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    base, state = draft(owner, headers, workspace, "Nora Caldwell", [("Nora Caldwell", "person")])
    saved = decide(owner, headers, base, state, state["findings"][0], "label", "stand_in")
    assert saved.status_code == 200
    document = UUID(state["version"]["document_id"])
    with Session(engine) as session:
        row = session.get(DocumentReplacementSecret, document)
        assert row is not None and row.secret_ciphertext.startswith(b"gAAAA")
        old = KeyRing.from_settings(owner.app.state.settings)
        payload = old.decrypt_text(ProtectedValue(row.secret_ciphertext, row.key_id))
        ciphertext = row.secret_ciphertext
    calls = []
    actual = KeyRing.decrypt_text

    def counted(keys, protected):
        if protected.ciphertext == ciphertext:
            calls.append(1)
        return actual(keys, protected)

    monkeypatch.setattr(KeyRing, "decrypt_text", counted)
    preview = owner.get(base + "/preview").json()
    assert calls == [1]
    assert preview["fictional_finding_ids"] == [state["findings"][0]["finding_id"]]
    assert "Nora Caldwell" not in preview["text"]
    assert not {"seed", "offset", "secret_ciphertext", "key_id"} & preview.keys()
    assert payload not in str(preview)
    newer = KeyRing(
        "rotated",
        {
            "rotated": Fernet.generate_key(),
            "test": owner.app.state.settings.content_keys["test"].get_secret_value().encode(),
        },
    )
    with Session(engine) as session, session.begin():
        assert rotate_replacement_secrets(session, newer) == 1
        row = session.get(DocumentReplacementSecret, document)
        assert row.key_id == "rotated"
        assert newer.decrypt_text(ProtectedValue(row.secret_ciphertext, row.key_id)) == payload
    rotated = load_preview(
        engine, document_id=document, actor_id=actor, keys=newer, now=datetime.now(UTC)
    )
    assert rotated.text == preview["text"]
    assert owner.get(base + "/preview").status_code == 503
    assert owner.delete(base, headers=headers).status_code == 200
    with Session(engine) as session:
        assert session.get(DocumentReplacementSecret, document) is None


def test_group_scope_affected_ids_and_undo(intake_site):
    owner, _, _, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    source = "Nora Caldwell met Nora Caldwell."
    base, state = draft(owner, headers, workspace, source, [("Nora Caldwell", "person")])
    first = state["findings"][0]
    second_start = source.rindex("Nora Caldwell")
    added = owner.post(
        base + "/findings",
        json={
            "expected": state["version"],
            "span": {"start": second_start, "end": second_start + 13},
            "category": "person",
        },
        headers=headers,
    )
    assert added.status_code == 200
    state = decide(owner, headers, base, added.json(), first, "label").json()
    second = state["findings"][1]
    merged = owner.post(
        base + "/findings/" + second["finding_id"] + "/merge",
        json={"expected": state["version"], "target_finding_id": first["finding_id"]},
        headers=headers,
    )
    assert merged.status_code == 200
    state = merged.json()
    denied = decide(owner, headers, base, state, first, "label", "stand_in", group_scope=True)
    assert denied.status_code == 422
    saved = decide(
        owner,
        headers,
        base,
        state,
        first,
        "label",
        "stand_in",
        group_scope=True,
        affected_finding_ids=[first["finding_id"], second["finding_id"]],
    )
    assert saved.status_code == 200
    preview = owner.get(base + "/preview").json()
    replacements = [
        preview["text"][item["preview_span"]["start"] : item["preview_span"]["end"]]
        for item in preview["mappings"]
    ]
    assert replacements[0] == replacements[1] and len(preview["fictional_finding_ids"]) == 2
    undone = owner.post(
        base + "/review/undo", json={"expected": saved.json()["version"]}, headers=headers
    )
    assert undone.status_code == 200
    assert undone.json()["findings"][0]["style"] == "token"
    assert undone.json()["findings"][1]["action"] is None


def test_separate_documents_have_unrelated_standins_and_identical_export_bytes(intake_site):
    owner, other, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    _login(other, "intake-other@example.invalid")
    outputs, seeds = [], []
    keys = KeyRing.from_settings(owner.app.state.settings)
    for _ in range(2):
        base, state = draft(
            owner, headers, workspace, "Nora Caldwell", [("Nora Caldwell", "person")]
        )
        state = decide(
            owner, headers, base, state, state["findings"][0], "label", "stand_in"
        ).json()
        preview = owner.get(base + "/preview").json()
        assert other.get(base + "/preview").status_code == 404
        assert (
            owner.post(
                base + "/complete",
                json={"expected": state["version"], "confirmed_preview": True},
                headers=headers,
            ).status_code
            == 200
        )
        copy = owner.post(
            base + "/exports/copy-payload", json={"expected": state["version"]}, headers=headers
        )
        txt = owner.post(
            base + "/exports/txt",
            json={"expected": state["version"], "event_id": str(uuid4())},
            headers=headers,
        )
        assert copy.status_code == txt.status_code == 200
        assert copy.json()["text"] == preview["text"] and txt.content == preview["text"].encode(
            "utf-8"
        )
        summary = owner.get(base + "/summary").json()
        assert summary["fictional_replacements"] == 1
        assert summary["counts_by_action_and_style"]["label"]["stand_in"] == 1
        assert "Nora Caldwell" not in str(summary) and preview["text"] not in str(summary)
        outputs.append(preview["text"])
        with Session(engine) as session:
            row = session.get(DocumentReplacementSecret, UUID(state["version"]["document_id"]))
            seeds.append(keys.decrypt_text(ProtectedValue(row.secret_ciphertext, row.key_id)))
    # Unrelated seeds are guaranteed; finite fictional name lists can coincide.
    assert seeds[0] != seeds[1]


def test_expiry_denies_and_purges_replacement_configuration(intake_site):
    owner, _, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    base, state = draft(owner, headers, workspace, "Nora Caldwell", [("Nora Caldwell", "person")])
    saved = decide(owner, headers, base, state, state["findings"][0], "label", "stand_in")
    assert saved.status_code == 200
    document = UUID(state["version"]["document_id"])
    with Session(engine) as session, session.begin():
        row = session.get(Document, document)
        row.created_at = datetime.now(UTC) - timedelta(days=2)
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert owner.get(base + "/preview").status_code == 410
    assert purge_unavailable_content(engine, now=datetime.now(UTC)).documents_purged == 1
    with Session(engine) as session:
        assert session.get(DocumentReplacementSecret, document) is None
        assert session.get(Document, document).current_revision_id is None
