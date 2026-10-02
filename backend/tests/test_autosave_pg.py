"""Protected working drafts must survive interruption without changing a review."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cleanup.service import purge_unavailable_content
from app.db.crypto import KeyRing, ProtectedValue
from app.db.recovery import RecoverySnapshot
from app.db.rotate_keys import rotate_recovery
from tests.intake_support import _draft_body, _login


def path(workspace, snapshot=None):
    base = f"/api/v1/workspaces/{workspace}/recovery"
    return f"{base}/{snapshot}" if snapshot else base


def body(*, version=0, document=None, base=None, source="😀 cafe\u0301\r\n東京 draft"):
    return {
        "expected_version": version,
        "document_id": document,
        "payload": {
            "source": source,
            "title": "Fictional working draft",
            "categories": ["email"],
            "phone_region": "PH",
            "retention_days": 3,
            "base_version": base,
        },
    }


def test_encrypted_intake_roundtrip_and_version_guard(intake_site):
    owner, other, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    other_headers = _login(other, "intake-other@example.invalid")
    snapshot = uuid4()
    payload = body()
    saved = owner.put(path(workspace, snapshot), json=payload, headers=headers)
    assert saved.status_code == 200
    assert saved.json()["version"] == 1
    restored = owner.get(path(workspace, snapshot))
    assert restored.status_code == 200
    assert restored.headers["Cache-Control"] == "no-store"
    assert restored.json()["payload"] == payload["payload"] | {"preset_id": None}
    with Session(engine) as session:
        row = session.get(RecoverySnapshot, snapshot)
        assert payload["payload"]["source"].encode() not in row.payload_ciphertext
        assert b"Fictional working draft" not in row.payload_ciphertext
    assert other.get(path(workspace, snapshot)).status_code == 404
    assert (
        other.put(
            path(workspace, snapshot), json=body(version=1), headers=other_headers
        ).status_code
        == 404
    )
    assert other.get(path(workspace)).json() == []
    assert owner.put(path(workspace, snapshot), json=body(), headers=headers).status_code == 409
    changed = owner.put(
        path(workspace, snapshot), json=body(version=1, source="Changed"), headers=headers
    )
    assert changed.json()["version"] == 2
    assert (
        owner.delete(path(workspace, snapshot) + "?expected_version=1", headers=headers).status_code
        == 409
    )
    assert owner.get(path(workspace, snapshot)).json()["payload"]["source"] == "Changed"
    assert (
        owner.delete(path(workspace, snapshot) + "?expected_version=2", headers=headers).status_code
        == 204
    )
    assert owner.get(path(workspace, snapshot)).status_code == 404


def test_autosave_preserves_immutable_source_and_separate_tab_copies(intake_site):
    owner, _, _, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    draft = owner.post("/api/v1/documents", json=_draft_body(workspace), headers=headers).json()
    document = draft["version"]["document_id"]
    base = f"/api/v1/documents/{document}/source"
    original = owner.get(base).json()
    copies = [uuid4(), uuid4()]
    for index, snapshot in enumerate(copies):
        response = owner.put(
            path(workspace, snapshot),
            headers=headers,
            json=body(
                document=document,
                base=draft["version"],
                source=f"Separate tab {index} 😀\r\n",
            ),
        )
        assert response.status_code == 200
    assert owner.get(base).json() == original
    listing = owner.get(path(workspace) + f"?document_id={document}").json()
    assert {item["id"] for item in listing} == {str(item) for item in copies}
    assert all("payload" not in item for item in listing)
    committed = owner.put(
        base,
        headers=headers,
        json={
            "expected": draft["version"],
            "source": "A new saved revision.",
        },
    )
    assert committed.status_code == 200
    for index, snapshot in enumerate(copies):
        assert (
            owner.get(path(workspace, snapshot)).json()["payload"]["source"]
            == f"Separate tab {index} 😀\r\n"
        )
    stale = owner.put(
        base,
        headers=headers,
        json={
            "expected": draft["version"],
            "source": "An older tab's revision.",
        },
    )
    assert stale.status_code == 409
    assert owner.get(base).json()["text"] == "A new saved revision."


def test_concurrent_autosaves_cannot_overwrite_each_other(intake_site):
    owner, _, _, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    snapshot = uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda text: owner.put(
                    path(workspace, snapshot),
                    headers=headers,
                    json=body(source=text),
                ),
                ["First simultaneous copy", "Second simultaneous copy"],
            )
        )
    assert sorted(response.status_code for response in responses) == [200, 409]
    winner = next(response for response in responses if response.status_code == 200)
    assert winner.json()["version"] == 1
    assert owner.get(path(workspace, snapshot)).json()["version"] == 1


def test_deleted_expired_and_revoked_content_cannot_recover(intake_site):
    owner, _, engine, workspace, actor = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    snapshot = uuid4()
    draft = owner.post("/api/v1/documents", json=_draft_body(workspace), headers=headers).json()
    document = draft["version"]["document_id"]
    assert (
        owner.put(
            path(workspace, snapshot),
            headers=headers,
            json=body(
                document=document,
                base=draft["version"],
            ),
        ).status_code
        == 200
    )
    assert owner.delete(f"/api/v1/documents/{document}", headers=headers).status_code == 200
    assert owner.get(path(workspace, snapshot)).status_code == 410
    assert owner.get(path(workspace) + f"?document_id={document}").status_code == 410
    purge_unavailable_content(engine, now=datetime.now(UTC))
    with Session(engine) as session:
        assert session.get(RecoverySnapshot, snapshot) is None
    intake_copy = uuid4()
    assert owner.put(path(workspace, intake_copy), headers=headers, json=body()).status_code == 200
    with Session(engine) as session, session.begin():
        row = session.get(RecoverySnapshot, intake_copy)
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert owner.get(path(workspace, intake_copy)).status_code == 410
    purge_unavailable_content(engine, now=datetime.now(UTC))
    with Session(engine) as session:
        assert session.get(RecoverySnapshot, intake_copy) is None
    from app.db.models import Membership

    with Session(engine) as session, session.begin():
        session.get(Membership, (workspace, actor)).revoked_at = datetime.now(UTC)
    assert owner.get(path(workspace)).status_code == 401


def test_limits_csrf_and_key_rotation(intake_site):
    from cryptography.fernet import Fernet

    owner, _, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    snapshot = uuid4()
    assert owner.put(path(workspace, snapshot), json=body()).status_code == 403
    for source in ("x" * 100_001, "\ud800"):
        response = owner.put(
            path(workspace, snapshot),
            headers={**headers, "Content-Type": "application/json"},
            content=json.dumps(body(source=source)),
        )
        assert response.status_code == 422
        assert "Fictional working draft" not in response.text
    assert (
        owner.put(path(workspace, snapshot), headers=headers, json=body(source="")).status_code
        == 200
    )
    old = owner.app.state.settings
    new_key = Fernet.generate_key()
    ring = KeyRing(
        "rotated",
        {
            "rotated": new_key,
            **{key: value.get_secret_value().encode() for key, value in old.content_keys.items()},
        },
    )
    with Session(engine) as session, session.begin():
        assert rotate_recovery(session, ring) == 1
    with Session(engine) as session:
        row = session.scalar(select(RecoverySnapshot).where(RecoverySnapshot.id == snapshot))
        assert row.payload_key_id == "rotated"
        assert '"source":""' in ring.decrypt_text(
            ProtectedValue(row.payload_ciphertext, row.payload_key_id)
        )
