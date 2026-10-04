import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from uuid import UUID, uuid4, uuid5
from zipfile import ZipFile

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.accounts.access import DocumentNotFound
from app.batches.outputs import BatchOutputRejected, archive_chunks, build_zip
from app.db.crypto import KeyRing
from app.db.models import Document, ExportEvent, Membership
from tests.batch_support import batch_client, review_and_confirm, upload
from tests.docx_fixtures import read_word
from tests.import_fixtures import docx_sample, pdf_sample
from tests.intake_support import _login


@pytest.mark.parametrize("mode", ["original", "txt"])
def test_zip_parity_neutral_names_manifest_and_idempotent_per_document_events(intake_site, mode):
    owner, headers, base = batch_client(intake_site)
    _, _, engine, _, _ = intake_site
    inputs = [
        ("private.txt", b"Fictional nora@example.test"),
        ("private.csv", b'Email,Note\r\nnora@example.test,"=2+2"\r\n'),
        ("private.docx", docx_sample()),
        ("private.pdf", pdf_sample()),
    ]
    confirmed = []
    for filename, content in inputs:
        version = upload(owner, headers, base, content, filename)
        document_base, state, canonical = review_and_confirm(owner, headers, version)
        confirmed.append((document_base, state, canonical))
    unreviewed = upload(owner, headers, base, b"Unreviewed fictional nora@example.test")
    eligible = owner.get(base + "/outputs/eligibility").json()
    assert eligible["included_count"] == 4 and eligible["total_count"] == 5
    assert eligible["excluded"] == [
        {"document_id": unreviewed["document_id"], "reason": "not_confirmed"}
    ]
    request_id = uuid4()
    body = {"request_id": str(request_id), "mode": mode}
    for _ in range(2):
        response = owner.post(base + "/outputs", json=body, headers=headers)
        assert response.status_code == 200, response.text if response.status_code != 200 else ""
        assert response.headers["content-type"] == "application/zip"
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "private" not in response.headers["content-disposition"]
        with ZipFile(io.BytesIO(response.content)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            assert len(manifest["included"]) == 4 and manifest["excluded"] == eligible["excluded"]
            assert len(archive.namelist()) == 5
            assert b"nora@" not in archive.read("manifest.json") and b"private" not in archive.read(
                "manifest.json"
            )
            for index, ((document_base, state, canonical), item) in enumerate(
                zip(confirmed, manifest["included"], strict=True), start=1
            ):
                format = "txt" if mode == "txt" else ["txt", "csv", "docx", "txt"][index - 1]
                document_id = state["version"]["document_id"]
                assert item["file"] == f"reviewed-{index:02d}-{document_id}.{format}"
                assert item["format"] == format and item["confirmed_at"]
                assert item["decision_version"] == state["version"]["decision_version"]
                payload = archive.read(item["file"])
                direct = owner.post(
                    document_base + "/exports/" + format,
                    json={
                        "expected": state["version"],
                        "event_id": str(uuid4()),
                    },
                    headers=headers,
                )
                assert direct.status_code == 200
                if format == "docx":
                    assert read_word(payload)[0] == read_word(direct.content)[0] == canonical
                elif format == "csv":
                    assert payload == direct.content and payload.startswith(b"\xef\xbb\xbf")
                    rows = list(csv.reader(io.StringIO(payload.decode("utf-8-sig"))))
                    assert rows[1][1] == "'=2+2" and "nora@" not in rows[1][0]
                else:
                    assert payload.decode() == canonical and payload == direct.content
        with Session(engine) as session:
            ids = [uuid5(request_id, state["version"]["document_id"]) for _, state, _ in confirmed]
            assert (
                session.scalar(select(func.count(ExportEvent.id)).where(ExportEvent.id.in_(ids)))
                == 4
            )
    state = owner.get(base).json()
    assert state["counts"] == {"exported": 4, "queued": 1}


def test_zip_excludes_stale_expired_deleted_failed_and_unconfirmed_documents(intake_site):
    owner, headers, base = batch_client(intake_site)
    _, _, engine, _, _ = intake_site
    included = upload(owner, headers, base)
    review_and_confirm(owner, headers, included)
    stale = upload(owner, headers, base)
    document_base, state, _ = review_and_confirm(owner, headers, stale)
    assert (
        owner.put(
            document_base + "/source",
            json={"expected": state["version"], "source": "Revised fictional"},
            headers=headers,
        ).status_code
        == 200
    )
    expired, deleted, failed, unconfirmed = [upload(owner, headers, base) for _ in range(4)]
    with Session(engine) as session, session.begin():
        document = session.get(Document, UUID(expired["document_id"]))
        document.created_at = datetime.now(UTC) - timedelta(days=2)
        document.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.get(Document, UUID(failed["document_id"])).status = "failed"
    assert (
        owner.delete(f"/api/v1/documents/{deleted['document_id']}", headers=headers).status_code
        == 200
    )
    eligible = owner.get(base + "/outputs/eligibility").json()
    reasons = {row["document_id"]: row["reason"] for row in eligible["excluded"]}
    assert reasons == {
        stale["document_id"]: "stale_confirmation",
        expired["document_id"]: "expired",
        deleted["document_id"]: "deleted",
        failed["document_id"]: "scan_failed",
        unconfirmed["document_id"]: "not_confirmed",
    }
    response = owner.post(base + "/outputs", json={"request_id": str(uuid4())}, headers=headers)
    assert response.status_code == 200
    with ZipFile(io.BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert [row["document_id"] for row in manifest["included"]] == [included["document_id"]]
        assert {row["document_id"]: row["reason"] for row in manifest["excluded"]} == reasons


def test_zip_approval_is_version_and_active_reviewer_bound_and_owner_only(intake_site):
    owner, headers, base = batch_client(intake_site)
    _, reviewer, engine, workspace, _ = intake_site
    reviewer_headers = _login(reviewer, "intake-other@example.invalid")
    reviewer_id = reviewer.get("/api/v1/auth/session").json()["user_id"]
    version = upload(owner, headers, base)
    document_base = f"/api/v1/documents/{version['document_id']}"
    assigned = owner.put(
        document_base + "/handoff",
        json={
            "expected": version,
            "reviewer_id": reviewer_id,
            "require_approval": True,
        },
        headers=headers,
    )
    assert assigned.status_code == 200
    version = owner.get(document_base + "/source").json()["version"]
    _, state, _ = review_and_confirm(owner, headers, version)
    assert owner.get(base).json()["documents"][0]["state"] == "awaiting_approval"
    assert (
        owner.get(base + "/outputs/eligibility").json()["excluded"][0]["reason"]
        == "approval_required"
    )
    body = {"request_id": str(uuid4())}
    assert owner.post(base + "/outputs", json=body, headers=headers).status_code == 409
    assert reviewer.get(document_base + "/source").status_code == 200
    assert reviewer.get(base).status_code == 404
    assert reviewer.get(base + "/outputs/eligibility").status_code == 404
    assert reviewer.post(base + "/outputs", json=body, headers=reviewer_headers).status_code == 404
    assert (
        owner.post(
            base + "/outputs", json=body, headers={"Origin": "http://localhost:5173"}
        ).status_code
        == 403
    )
    assert (
        reviewer.post(
            document_base + "/approval",
            json={"expected": state["version"], "confirmed_preview": True},
            headers=reviewer_headers,
        ).status_code
        == 200
    )
    assert owner.get(base).json()["documents"][0]["state"] == "approved"
    assert owner.post(base + "/outputs", json=body, headers=headers).status_code == 200
    with Session(engine) as session, session.begin():
        session.get(Membership, (workspace, UUID(reviewer_id))).revoked_at = datetime.now(UTC)
    assert (
        owner.post(
            base + "/outputs", json={"request_id": str(uuid4())}, headers=headers
        ).status_code
        == 409
    )
    with Session(engine) as session, session.begin():
        session.get(Membership, (workspace, UUID(reviewer_id))).revoked_at = None
    edit = owner.put(
        document_base + "/source",
        json={"expected": state["version"], "source": "New fictional version"},
        headers=headers,
    )
    assert edit.status_code == 200
    _, changed, _ = review_and_confirm(owner, headers, edit.json()["version"])
    assert changed["version"] != state["version"]
    assert (
        owner.post(
            base + "/outputs", json={"request_id": str(uuid4())}, headers=headers
        ).status_code
        == 409
    )


def test_nothing_eligible_bounded_output_and_stream_close(intake_site):
    owner, headers, base = batch_client(intake_site)
    _, _, engine, _, actor = intake_site
    empty = owner.post(base + "/outputs", json={"request_id": str(uuid4())}, headers=headers)
    assert empty.status_code == 409 and empty.json()["code"] == "no_reviewed_outputs"
    version = upload(owner, headers, base, b"Fictional nora@example.test " * 100)
    review_and_confirm(owner, headers, version)
    batch_id = UUID(base.rsplit("/", 1)[1])
    keys = KeyRing.from_settings(owner.app.state.settings)
    event = uuid4()
    with pytest.raises(BatchOutputRejected, match="limit") as exc:
        build_zip(engine, batch_id, actor, event, "txt", keys, maximum_bytes=100)
    assert exc.value.code == "outputs_too_large"
    with Session(engine) as session:
        assert session.get(ExportEvent, uuid5(event, version["document_id"])) is None
    spool = build_zip(engine, batch_id, actor, uuid4(), "txt", keys)
    chunks = archive_chunks(spool)
    assert next(chunks).startswith(b"PK")
    chunks.close()
    assert spool.closed


def test_docx_mode_retry_cannot_reuse_txt_export_events(intake_site):
    owner, headers, base = batch_client(intake_site)
    version = upload(owner, headers, base, docx_sample(), "fixture.docx")
    review_and_confirm(owner, headers, version)
    body = {"request_id": str(uuid4()), "mode": "txt"}
    assert owner.post(base + "/outputs", json=body, headers=headers).status_code == 200
    conflict = owner.post(base + "/outputs", json={**body, "mode": "original"}, headers=headers)
    assert conflict.status_code == 409 and conflict.json()["code"] == "output_request_conflict"


def test_document_changed_after_eligibility_is_excluded_under_export_lock(intake_site):
    owner, headers, base = batch_client(intake_site)
    _, _, engine, _, actor = intake_site
    versions = [upload(owner, headers, base) for _ in range(2)]
    for version in versions:
        review_and_confirm(owner, headers, version)
    request_id = uuid4()
    reached = Event()

    def observe(_connection, _cursor, statement, _parameters, _context, _many):
        if "FOR UPDATE" in statement and "documents" in statement:
            reached.set()

    with Session(engine) as blocker:
        transaction = blocker.begin()
        document = blocker.scalar(
            select(Document)
            .where(Document.id == UUID(versions[0]["document_id"]))
            .with_for_update()
        )
        event.listen(engine, "before_cursor_execute", observe)
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(
                    build_zip,
                    engine,
                    UUID(base.rsplit("/", 1)[1]),
                    actor,
                    request_id,
                    "txt",
                    KeyRing.from_settings(owner.app.state.settings),
                )
                try:
                    assert reached.wait(10), "Real export did not reach the locked document."
                    # A simultaneous review edit invalidates the candidate read before
                    # this lock; no query or output-generation function is replaced.
                    document.decision_version += 1
                    document.status = "needs_review"
                    transaction.commit()
                finally:
                    if transaction.is_active:
                        transaction.rollback()
                spool = pending.result(timeout=10)
                try:
                    with ZipFile(spool) as archive:
                        manifest = json.loads(archive.read("manifest.json"))
                finally:
                    spool.close()
        finally:
            transaction.close()
            event.remove(engine, "before_cursor_execute", observe)
    assert [row["document_id"] for row in manifest["included"]] == [versions[1]["document_id"]]
    assert manifest["excluded"] == [
        {"document_id": versions[0]["document_id"], "reason": "stale_confirmation"}
    ]
    with Session(engine) as session:
        assert session.get(ExportEvent, uuid5(request_id, versions[0]["document_id"])) is None


def test_owner_revocation_during_generation_stops_entire_zip(intake_site):
    owner, headers, base = batch_client(intake_site)
    _, _, engine, workspace, actor = intake_site
    version = upload(owner, headers, base)
    review_and_confirm(owner, headers, version)
    revoked = Event()

    def revoke_after_event(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("INSERT INTO export_events") and not revoked.is_set():
            revoked.set()
            with Session(engine) as independent, independent.begin():
                independent.get(Membership, (workspace, actor)).revoked_at = datetime.now(UTC)

    event.listen(engine, "after_cursor_execute", revoke_after_event)
    try:
        with pytest.raises(DocumentNotFound):
            build_zip(
                engine,
                UUID(base.rsplit("/", 1)[1]),
                actor,
                uuid4(),
                "txt",
                KeyRing.from_settings(owner.app.state.settings),
            )
    finally:
        event.remove(engine, "after_cursor_execute", revoke_after_event)
    assert revoked.is_set()
