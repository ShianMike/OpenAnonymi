"""Actual OCR/Markdown/edit-save review, encrypted storage and late auth boundaries."""

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.batches import api as batch_api
from app.db.models import Document, Membership, SourceRevision, User
from app.db.models import Session as StoredSession
from app.intake import api, import_api, imports
from tests.batch_support import batch_client
from tests.docx_fixtures import read_word
from tests.import_fixtures import docx_sample
from tests.intake_support import ORIGIN, _login
from tests.ocr_fixtures import image_sample, scanned_pdf


@pytest.mark.parametrize("kind", ["png", "pdf", "md", "csv", "docx"])
def test_actual_preview_edit_save_scan_confirm_outputs_preserve_corrected_source(intake_site, kind):
    owner, other, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    original = {
        "png": lambda: image_sample(),
        "pdf": lambda: scanned_pdf(),
        "md": lambda: b"# Fictional original\nContact: nora@example.test",
        "csv": lambda: b"Name,Contact\nOriginal,nora@example.test\n",
        "docx": docx_sample,
    }[kind]()
    filename = "original-filename-private." + kind
    preview = owner.post(
        "/api/v1/documents/import-preview",
        data={"workspace_id": str(workspace)},
        files={"file": (filename, original)},
        headers=headers,
    )
    assert preview.status_code == 200
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count(Document.id)).where(Document.workspace_id == workspace)
            )
            == 0
        )
    edited = (
        "Name,Contact\nCorrected,corrected@example.test\n"
        if kind == "csv"
        else ("Corrected 😀 scan\n<script>literal</script>\nContact: corrected@example.test")
    )
    created = owner.post(
        "/api/v1/documents/from-file",
        data={
            "workspace_id": str(workspace),
            "categories": "email",
            "edited_text_json": json.dumps(edited),
        },
        files={"file": (filename, original)},
        headers=headers,
    )
    assert created.status_code == 201
    version = created.json()["version"]
    base = "/api/v1/documents/" + version["document_id"]
    source = owner.get(base + "/source").json()
    assert source["text"] == edited and source["title"] is None
    assert other.get(base + "/source").status_code == 401
    with Session(engine) as session:
        revision = session.get(SourceRevision, UUID(version["source_revision_id"]))
        assert b"corrected@example.test" not in revision.source_ciphertext
    scanned = owner.post(base + "/scan", json={"expected": version}, headers=headers)
    assert scanned.status_code == 200 and len(scanned.json()["suggestions"]) == 1
    finding = scanned.json()["suggestions"][0]["finding_id"]
    decision = owner.post(
        base + "/findings/" + finding + "/decision",
        json={
            "expected": scanned.json()["version"],
            "action": "redact",
            "affected_finding_ids": [finding],
        },
        headers=headers,
    )
    assert decision.status_code == 200
    version = decision.json()["version"]
    confirmed = owner.post(
        base + "/complete", json={"expected": version, "confirmed_preview": True}, headers=headers
    )
    assert confirmed.status_code == 200
    canonical = edited.replace("corrected@example.test", "[REDACTED]")
    for format in ("txt", "docx"):
        exported = owner.post(
            base + "/exports/" + format,
            json={"expected": version, "event_id": str(uuid4())},
            headers=headers,
        )
        assert exported.status_code == 200
        actual = exported.content.decode() if format == "txt" else read_word(exported.content)[0]
        assert actual == canonical
    assert owner.get(base + "/source").json()["text"] == edited
    if kind == "csv":
        assert source["csv"]["columns"] == 2 and source["csv"]["data_rows"] == 1
    if kind == "docx":
        assert source["structure"] == "none"


@pytest.mark.parametrize("route", ["import-preview", "from-file", "batch"])
@pytest.mark.parametrize(
    "change", ["session_revoked", "session_expired", "user_disabled", "membership_revoked"]
)
def test_late_auth_change_after_actual_ocr_blocks_preview_or_persistence(
    intake_site, monkeypatch, route, change
):
    owner, _, engine, workspace, actor = intake_site
    if route == "batch":
        owner, headers, base = batch_client(intake_site)
        target = base + "/documents"
    else:
        headers = _login(owner, "intake-owner@example.invalid")
        target = "/api/v1/documents/" + route
    real_extract = imports.extract_import

    def extract_then_revoke(*args):
        value = real_extract(*args)
        with Session(engine) as session, session.begin():
            if change == "session_revoked":
                session.execute(
                    update(StoredSession)
                    .where(StoredSession.user_id == actor)
                    .values(revoked_at=datetime.now(UTC))
                )
            elif change == "user_disabled":
                session.get(User, actor).disabled_at = datetime.now(UTC)
            elif change == "session_expired":
                session.execute(
                    update(StoredSession)
                    .where(StoredSession.user_id == actor)
                    .values(expires_at=datetime.now(UTC) - timedelta(milliseconds=1))
                )
            else:
                session.get(Membership, (workspace, actor)).revoked_at = datetime.now(UTC)
        return value

    module = {"import-preview": import_api, "from-file": api, "batch": batch_api}[route]
    monkeypatch.setattr(module, "extract_import", extract_then_revoke)
    response = owner.post(
        target,
        data={} if route == "batch" else {"workspace_id": str(workspace)},
        files={"file": ("scan.png", image_sample())},
        headers=headers,
    )
    assert response.status_code == 401
    assert "nora@example.test" not in response.text
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count(Document.id)).where(Document.workspace_id == workspace)
            )
            == 0
        )


def test_editor_invalid_source_or_csv_structure_never_creates_document(intake_site):
    owner, _, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    for filename, payload, edited in [
        ("a.md", b"Fictional source", ""),
        ("a.md", b"Fictional source", "control\x00canary"),
        ("a.csv", b"Name,Value\nOriginal,contact\n", "Name,Value,Third\nChanged,contact,extra\n"),
    ]:
        response = owner.post(
            "/api/v1/documents/from-file",
            data={"workspace_id": str(workspace), "edited_text_json": json.dumps(edited)},
            files={"file": (filename, payload)},
            headers=headers,
        )
        assert response.status_code == 422 and "control\x00canary" not in response.text
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count(Document.id)).where(Document.workspace_id == workspace)
            )
            == 0
        )


@pytest.mark.parametrize("route", ["import-preview", "from-file"])
def test_scan_intake_denies_missing_session_csrf_foreign_origin_and_workspace(intake_site, route):
    owner, anonymous, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    payload = image_sample()
    target = "/api/v1/documents/" + route
    for client, request_headers, workspace_id, status in [
        (anonymous, headers, workspace, 401),
        (owner, {"Origin": ORIGIN}, workspace, 403),
        (owner, {**headers, "Origin": "https://foreign.invalid"}, workspace, 403),
        (owner, headers, uuid4(), 404),
    ]:
        result = client.post(
            target,
            data={"workspace_id": str(workspace_id)},
            files={"file": ("scan.png", payload)},
            headers=request_headers,
        )
        assert result.status_code == status and "nora@example.test" not in result.text
    with Session(engine) as session:
        assert session.scalar(select(func.count(Document.id))) == 0


def test_duplicate_extracted_text_corrections_are_rejected(intake_site):
    owner, _, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    response = owner.post(
        "/api/v1/documents/from-file",
        data={"workspace_id": str(workspace)},
        files=[
            ("file", ("a.md", b"Fictional source")),
            ("edited_text_json", (None, json.dumps("First correction"))),
            ("edited_text_json", (None, json.dumps("Second correction"))),
        ],
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_source"
    with Session(engine) as session:
        assert session.scalar(select(func.count(Document.id))) == 0


def test_json_correction_preserves_mixed_line_endings_and_unicode(intake_site):
    owner, _, _, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    text = 'Fictional 😀\nSecond line\r\nLiteral "quotes" and \\backslash'
    response = owner.post(
        "/api/v1/documents/from-file",
        data={"workspace_id": str(workspace), "edited_text_json": json.dumps(text)},
        files={"file": ("a.md", b"Fictional source")},
        headers=headers,
    )
    assert response.status_code == 201
    base = "/api/v1/documents/" + response.json()["version"]["document_id"]
    assert owner.get(base + "/source").json()["text"] == text


@pytest.mark.parametrize("correction", ["", "not-json-private-canary", "null", "42", "{}", "[]"])
def test_invalid_json_correction_does_not_save_original_source(intake_site, correction):
    owner, _, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    response = owner.post(
        "/api/v1/documents/from-file",
        data={"workspace_id": str(workspace), "edited_text_json": correction},
        files={"file": ("a.md", b"Fictional source")},
        headers=headers,
    )
    assert response.status_code == 422
    assert "private-canary" not in response.text
    with Session(engine) as session:
        assert session.scalar(select(func.count(Document.id))) == 0
