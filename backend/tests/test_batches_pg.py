import asyncio
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID
from zipfile import ZIP_STORED, ZipFile

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.batches import Batch, ScanJob
from app.db.crypto import KeyRing, ProtectedValue
from app.db.models import Document, Membership, SourceRevision
from app.intake.imports import MAX_FILE_BYTES
from tests.batch_support import batch_client, upload
from tests.import_fixtures import docx_sample, pdf_sample
from tests.intake_support import ORIGIN, _login
from tests.ocr_fixtures import image_sample, scanned_pdf
from tests.test_custom_rules_pg import RULE


@pytest.mark.parametrize(
    "filename,content",
    [
        ("private.txt", "Fictional nora@example.test 😀\r\n".encode()),
        ("private.csv", b'Email,Notes\r\nnora@example.test,"line1\nline2"\r\n'),
        ("private.pdf", None),
        ("private.docx", None),
        ("private.md", b"# Fictional scan\nContact: nora@example.test"),
        ("private.png", None),
        ("private-scanned.pdf", None),
    ],
)
def test_batch_upload_uses_real_imports_and_persists_atomic_scan_job(
    intake_site, filename, content
):
    owner, headers, base = batch_client(intake_site)
    _, other, engine, _, _ = intake_site
    content = (
        content
        if content is not None
        else image_sample()
        if filename.endswith(".png")
        else scanned_pdf()
        if filename == "private-scanned.pdf"
        else pdf_sample()
        if filename.endswith(".pdf")
        else docx_sample()
    )
    version = upload(owner, headers, base, content, filename)
    assert other.get(base).status_code == 401
    _login(other, "intake-other@example.invalid")
    assert other.get(base).status_code == 404
    document_base = f"/api/v1/documents/{version['document_id']}"
    source = owner.get(document_base + "/source").json()
    assert source["title"] is None and source["phone_region"] == "GB"
    assert source["categories"] == ["email"] and "nora@" in source["text"]
    state = owner.get(base).json()
    assert state["counts"] == {"queued": 1} and state["processing"]
    keys = KeyRing.from_settings(owner.app.state.settings)
    with Session(engine) as session:
        batch = session.get(Batch, UUID(state["id"]))
        assert batch.uploaded_bytes == len(content) and b"Fictional" not in batch.name_ciphertext
        assert (
            keys.decrypt_text(ProtectedValue(batch.name_ciphertext, batch.name_key_id))
            == "Fictional batch 😀"
        )
        document = session.get(Document, UUID(version["document_id"]))
        job = session.scalar(select(ScanJob).where(ScanJob.document_id == document.id))
        assert job.batch_id == batch.id and document.batch_position == 1
        assert job.source_revision_id == document.current_revision_id and job.status == "queued"
        revision = session.get(SourceRevision, document.current_revision_id)
        assert source["text"].encode() not in revision.source_ciphertext
    # A new worker instance resumes jobs written before it existed.
    from app.batches.worker import ScanWorker

    worker = ScanWorker(engine, owner.app.state.settings)
    assert asyncio.run(worker.run_one())
    assert not asyncio.run(worker.run_one())
    state = owner.get(base).json()
    assert state["counts"] == {"needs_review": 1} and not state["processing"]
    assert state["next_document_id"] == version["document_id"]
    assert owner.get(document_base + "/scan").json()["status"] == "completed"


def test_batch_authorization_and_rejected_uploads_leave_no_metadata(intake_site):
    owner, headers, base = batch_client(intake_site)
    _, other, engine, workspace, _ = intake_site
    other_headers = _login(other, "intake-other@example.invalid")
    other_id = UUID(other.get("/api/v1/auth/session").json()["user_id"])
    with Session(engine) as session, session.begin():
        session.get(Membership, (workspace, other_id)).role = "administrator"
    response = other.get("/api/v1/batches", params={"workspace_id": str(workspace)})
    assert response.status_code == 200 and response.json() == {
        "own_batches": [],
        "workspace_total": 1,
    }
    assert (
        other.post(
            base + "/documents", files={"file": ("private.txt", b"a")}, headers=other_headers
        ).status_code
        == 404
    )
    assert (
        other.request("DELETE", base, json={"confirmed": True}, headers=other_headers).status_code
        == 404
    )
    assert (
        owner.post(
            base + "/documents", files={"file": ("a.txt", b"a")}, headers={"Origin": ORIGIN}
        ).status_code
        == 403
    )
    bad_origin = {**headers, "Origin": "https://outside.invalid"}
    assert (
        owner.post(
            base + "/documents", files={"file": ("a.txt", b"a")}, headers=bad_origin
        ).status_code
        == 403
    )
    overridden = owner.post(
        base + "/documents",
        data={"categories": "email"},
        files={"file": ("a.txt", b"a")},
        headers=headers,
    )
    assert overridden.status_code == 422 and overridden.json()["code"] == "batch_settings_fixed"
    duplicated = owner.post(
        base + "/documents",
        files=[("file", ("a.txt", b"a")), ("file", ("b.txt", b"b"))],
        headers=headers,
    )
    assert duplicated.status_code == 422 and duplicated.json()["code"] == "invalid_file"
    invalid = owner.post(
        base + "/documents", files={"file": ("secret.exe", b"not a document")}, headers=headers
    )
    assert invalid.status_code == 422
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count(Document.id)).where(Document.workspace_id == workspace)
            )
            == 0
        )
        assert session.get(Batch, UUID(base.rsplit("/", 1)[1])).uploaded_bytes == 0


def test_simultaneous_uploads_enforce_twenty_document_limit(intake_site):
    owner, headers, base = batch_client(intake_site)
    _, _, engine, workspace, _ = intake_site

    def submit(index):
        return owner.post(
            base + "/documents",
            files={"file": ("fixture.txt", f"Fictional {index}".encode())},
            headers=headers,
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(submit, range(22)))
    assert sum(response.status_code == 201 for response in responses) == 20
    refused = [response for response in responses if response.status_code != 201]
    assert all(
        response.status_code == 422 and response.json()["code"] == "batch_full"
        for response in refused
    )
    with Session(engine) as session:
        documents = session.scalars(
            select(Document).where(Document.workspace_id == workspace)
        ).all()
        assert sorted(row.batch_position for row in documents) == list(range(1, 21))
        assert (
            session.scalar(
                select(func.count(ScanJob.id)).where(ScanJob.batch_id == documents[0].batch_id)
            )
            == 20
        )


def test_batch_byte_limit_counts_accepted_raw_file_bytes(intake_site):
    owner, headers, base = batch_client(intake_site)
    payload = io.BytesIO(docx_sample())
    extra_name = "word/media/fictional.bin"
    padding = MAX_FILE_BYTES - len(payload.getvalue()) - 76 - 2 * len(extra_name)
    with ZipFile(payload, "a", compression=ZIP_STORED) as archive:
        archive.writestr(extra_name, b"x" * padding)
    content = payload.getvalue()
    assert len(content) == MAX_FILE_BYTES
    for _ in range(5):
        upload(owner, headers, base, content, "fictional.docx")
    refused = owner.post(
        base + "/documents", files={"file": ("fictional.txt", b"x")}, headers=headers
    )
    assert refused.status_code == 422 and refused.json()["code"] == "batch_too_large"
    state = owner.get(base).json()
    assert len(state["documents"]) == 5 and state["uploaded_bytes"] == 40 * 1024 * 1024


def test_batch_freezes_preset_columns_and_custom_rule_versions(intake_site):
    owner, _, engine, workspace, actor = intake_site
    with Session(engine) as session, session.begin():
        session.get(Membership, (workspace, actor)).role = "administrator"
    headers = _login(owner, "intake-owner@example.invalid")
    rule_base = f"/api/v1/workspaces/{workspace}/rules"
    rule = owner.post(rule_base, json=RULE, headers=headers).json()
    preset_base = f"/api/v1/workspaces/{workspace}/presets"
    preset_body = {
        "name": "Fictional preset",
        "categories": ["email"],
        "phone_region": "GB",
        "column_rules": [
            {
                "column": 0,
                "header": "Private Header",
                "mode": "keep",
                "keep_reason": "intended_disclosure",
            },
        ],
    }
    preset = owner.post(preset_base, json=preset_body, headers=headers).json()
    created = owner.post(
        "/api/v1/batches",
        json={"workspace_id": str(workspace), "preset_id": preset["id"]},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    base = f"/api/v1/batches/{created.json()['id']}"
    assert (
        owner.put(
            preset_base + "/" + preset["id"],
            json={**preset_body, "expected_version": 1, "phone_region": "PH", "column_rules": []},
            headers=headers,
        ).status_code
        == 200
    )
    assert (
        owner.put(
            rule_base + "/" + rule["id"],
            json={**RULE, "expected_version": 1, "expression": "TICKET-######"},
            headers=headers,
        ).status_code
        == 200
    )
    version = upload(
        owner,
        headers,
        base,
        b"Private Header,Reference\nada@example.test,CASE-123456\n",
        "fictional.csv",
    )
    document_base = f"/api/v1/documents/{version['document_id']}"
    source = owner.get(document_base + "/source").json()
    assert source["preset_version"] == 1 and source["phone_region"] == "GB"
    assert source["csv"]["rules"][0]["header"] == "Private Header"
    assert owner.get(document_base + "/rules").json()["rules"][0]["version"] == 1
    with Session(engine) as session:
        batch = session.get(Batch, UUID(created.json()["id"]))
        assert (
            "Private Header" not in str(batch.settings)
            and b"Private Header" not in batch.column_rules_ciphertext
        )


def test_confirmed_batch_delete_removes_all_owned_content_and_preserves_unrelated(intake_site):
    owner, headers, base = batch_client(intake_site)
    _, _, engine, _, _ = intake_site
    versions = [upload(owner, headers, base) for _ in range(2)]
    unrelated = owner.post(
        "/api/v1/batches",
        json={"workspace_id": owner.get(base).json()["workspace_id"]},
        headers=headers,
    )
    unrelated_base = f"/api/v1/batches/{unrelated.json()['id']}"
    survivor = upload(owner, headers, unrelated_base)
    assert (
        owner.request("DELETE", base, json={"confirmed": False}, headers=headers).status_code == 422
    )
    assert owner.get(base).status_code == 200
    assert (
        owner.request("DELETE", base, json={"confirmed": True}, headers=headers).status_code == 204
    )
    assert owner.get(base).status_code == 404
    for version in versions:
        assert owner.get(f"/api/v1/documents/{version['document_id']}/source").status_code == 410
    with Session(engine) as session:
        batch = session.get(Batch, UUID(base.rsplit("/", 1)[1]))
        assert batch.name_ciphertext is None and batch.column_rules_ciphertext is None
        for version in versions:
            document = session.get(Document, UUID(version["document_id"]))
            assert document.current_revision_id is None and document.title_ciphertext is None
            assert (
                session.scalar(
                    select(func.count(ScanJob.id)).where(ScanJob.document_id == document.id)
                )
                == 0
            )
        assert session.get(Document, UUID(survivor["document_id"])).current_revision_id is not None
    from app.cleanup.service import purge_unavailable_content

    purge_unavailable_content(engine, now=datetime.now(UTC))
    with Session(engine) as session:
        assert session.get(Batch, UUID(base.rsplit("/", 1)[1])) is None
