"""Real decisions, current-version confirmation and identical preview/copy/TXT."""

import json
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.db.crypto import KeyRing
from app.db.models import Document
from app.db.replacement_secrets import DocumentReplacementSecret
from tests.docx_fixtures import read_word
from tests.intake_support import _login
from tests.styles_support import decide, draft


@pytest.mark.parametrize(
    "value,category,action,style,option,expected",
    [
        ("Nóra Caldwell", "person", "redact", "partial_mask", "full", "**** ********"),
        ("Nóra Caldwell", "person", "redact", "partial_mask", "first_letters", "N*** C*******"),
        ("123-45-6789", "national_id", "redact", "partial_mask", "last4", "***-**-6789"),
        (
            "nora@example.test",
            "email",
            "redact",
            "partial_mask",
            "email_domain",
            "****@example.test",
        ),
        (
            "nora@example.test",
            "email",
            "redact",
            "partial_mask",
            "email_first",
            "n***@*******.test",
        ),
        (
            "https://example.test/path?id=42",
            "url",
            "redact",
            "partial_mask",
            "url_host",
            "https://example.test/****?**=**",
        ),
        (
            "ghp_Fictional7654",
            "secret",
            "redact",
            "partial_mask",
            "secret_prefix",
            "ghp_*************",
        ),
        ("3rd October 2026", "date", "label", "date_shift", None, "2nd November 2026"),
        ("3 October 2026", "date", "redact", "generalize", "month_year", "October 2026"),
        ("3 October 2026", "date", "redact", "generalize", "year", "2026"),
        ("2000-01-01", "date", "redact", "generalize", "age_band", "aged 20–29"),
    ],
)
def test_exact_style_parity(intake_site, value, category, action, style, option, expected):
    owner, _, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    prefix = "😀 DOB: " if option == "age_band" else "😀 Detail: "
    base, state = draft(owner, headers, workspace, prefix + value, [(value, category)])
    if style == "date_shift":
        keys = KeyRing.from_settings(owner.app.state.settings)
        protected = keys.encrypt_text(
            json.dumps({"version": 1, "seed": bytes(32).hex(), "offset": 30})
        )
        with Session(engine) as session, session.begin():
            session.add(
                DocumentReplacementSecret(
                    document_id=UUID(state["version"]["document_id"]),
                    secret_ciphertext=protected.ciphertext,
                    key_id=protected.key_id,
                    created_at=datetime.now(UTC),
                )
            )
    saved = decide(owner, headers, base, state, state["findings"][0], action, style, option)
    assert saved.status_code == 200
    state = saved.json()
    assert state["findings"][0]["style"] == style and state["findings"][0]["style_option"] == option
    preview = owner.get(base + "/preview").json()
    assert preview["text"] == prefix + expected and preview["status"] == "complete"
    assert preview["version"] == state["version"]
    completed = owner.post(
        base + "/complete",
        json={"expected": state["version"], "confirmed_preview": True},
        headers=headers,
    )
    assert completed.status_code == 200
    copy = owner.post(
        base + "/exports/copy-payload", json={"expected": state["version"]}, headers=headers
    )
    assert copy.status_code == 200 and copy.json()["text"] == preview["text"]
    txt = owner.post(
        base + "/exports/txt",
        json={"expected": state["version"], "event_id": str(uuid4())},
        headers=headers,
    )
    assert txt.status_code == 200 and txt.content == preview["text"].encode("utf-8")
    word = owner.post(
        base + "/exports/docx",
        json={"expected": state["version"], "event_id": str(uuid4())},
        headers=headers,
    )
    assert word.status_code == 200 and read_word(word.content)[0] == preview["text"]
    summary = owner.get(base + "/summary").json()
    assert summary["counts_by_action_and_style"][action][style] == 1
    assert summary["fictional_replacements"] == 0
    changed = decide(owner, headers, base, state, state["findings"][0], "redact")
    assert changed.status_code == 200
    assert (
        owner.post(
            base + "/exports/txt",
            json={"expected": state["version"], "event_id": str(uuid4())},
            headers=headers,
        ).status_code
        == 409
    )
    assert owner.get(base + "/summary").status_code == 409
    undo = owner.post(
        base + "/review/undo", json={"expected": changed.json()["version"]}, headers=headers
    )
    assert undo.status_code == 200
    assert undo.json()["findings"][0]["style"] == style
    assert owner.get(base + "/preview").json()["text"] == preview["text"]
    assert owner.get(base + "/summary").status_code == 409


def test_incompatible_style_is_atomic_and_content_free(intake_site):
    owner, _, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    base, state = draft(owner, headers, workspace, "123-45-6789", [("123-45-6789", "national_id")])
    denied = decide(owner, headers, base, state, state["findings"][0], "label", "stand_in")
    assert denied.status_code == 422 and denied.json()["code"] == "style_not_available"
    assert owner.get(base + "/findings").json() == state
    with Session(engine) as session:
        assert session.get(DocumentReplacementSecret, UUID(state["version"]["document_id"])) is None


@pytest.mark.parametrize(
    "value,category,action,style,option",
    [
        ("+63 917 123 4567", "phone", "label", "stand_in", None),
        ("31/2/2026", "date", "label", "date_shift", None),
        ("Private\nvalue", "custom", "redact", "partial_mask", "full"),
    ],
)
def test_value_incompatible_styles_leave_no_decision_or_secret(
    intake_site, value, category, action, style, option
):
    owner, _, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    base, state = draft(owner, headers, workspace, value, [(value, category)])
    caps = owner.get(base + "/preview").json()["style_capabilities"][
        state["findings"][0]["finding_id"]
    ]
    assert not any(choice["style"] == style for choice in caps[action])
    denied = decide(owner, headers, base, state, state["findings"][0], action, style, option)
    assert denied.status_code == 422 and denied.json()["code"] == "style_not_available"
    assert value not in denied.text and owner.get(base + "/findings").json() == state
    with Session(engine) as session:
        assert session.get(DocumentReplacementSecret, UUID(state["version"]["document_id"])) is None


def test_date_shift_range_rejection_preserves_version_and_encrypted_configuration(intake_site):
    owner, _, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    base, state = draft(owner, headers, workspace, "1900-01-01", [("1900-01-01", "date")])
    protected = KeyRing.from_settings(owner.app.state.settings).encrypt_text(
        json.dumps({"version": 1, "seed": bytes(32).hex(), "offset": -30})
    )
    document = UUID(state["version"]["document_id"])
    with Session(engine) as session, session.begin():
        session.add(
            DocumentReplacementSecret(
                document_id=document,
                secret_ciphertext=protected.ciphertext,
                key_id=protected.key_id,
                created_at=datetime.now(UTC),
            )
        )
    denied = decide(owner, headers, base, state, state["findings"][0], "label", "date_shift")
    assert denied.status_code == 422 and denied.json()["code"] == "date_shift_out_of_range"
    assert owner.get(base + "/findings").json() == state
    assert "-30" not in denied.text and "1900-01-01" not in denied.text
    with Session(engine) as session:
        assert (
            session.get(DocumentReplacementSecret, document).secret_ciphertext
            == protected.ciphertext
        )


@pytest.mark.parametrize("birth,expected", [("2008-01-01", "aged under 18"), ("2026-01-01", None)])
def test_age_uses_document_creation_in_utc_across_midnight(intake_site, birth, expected):
    owner, _, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    base, state = draft(owner, headers, workspace, "DOB: " + birth, [(birth, "date")])
    with Session(engine) as session, session.begin():
        document = session.get(Document, UUID(state["version"]["document_id"]))
        document.created_at = datetime(2026, 1, 1, 0, 30, tzinfo=timezone(timedelta(hours=8)))
    denied_or_saved = decide(
        owner, headers, base, state, state["findings"][0], "redact", "generalize", "age_band"
    )
    if expected is None:
        assert (
            denied_or_saved.status_code == 422
            and denied_or_saved.json()["code"] == "style_not_available"
        )
        assert owner.get(base + "/findings").json() == state
    else:
        assert denied_or_saved.status_code == 200
        assert owner.get(base + "/preview").json()["text"] == "DOB: " + expected
