"""Real intake/batch transactions preserve owned storage on late access loss."""

import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.batches.contracts import BatchView, CreateBatchRequest
from app.contracts import DocumentStatus
from app.db.batches import Batch, ScanJob
from app.db.crypto import KeyRing
from app.db.models import AuditEvent, Document, Membership, SourceRevision, Workspace
from app.db.source_structures import SourceStructure
from tests.batch_support import batch_client, upload
from tests.import_fixtures import docx_sample
from tests.intake_support import _draft_body, _login
from tests.test_content_read_access_pg import change_actor
from tests.test_source_csv_mutation_access_pg import storage_fingerprint

OPERATIONS = (
    "batch-create",
    "batch-upload",
    "batch-retry",
    "batch-delete",
    "paste",
    "file-docx",
    "file-csv",
)
PHASES = ("authorized", "built")


def mutation_case(site, operation):
    owner, _, engine, workspace, actor = site
    case = {
        "client": owner,
        "engine": engine,
        "workspace": workspace,
        "actor": actor,
        "operation": operation,
    }
    if operation in ("batch-upload", "batch-retry", "batch-delete"):
        owner, headers, base = batch_client(site)
        case.update(headers=headers, base=base, batch_id=UUID(base.rsplit("/", 1)[1]))
        if operation != "batch-upload":
            version = upload(
                owner,
                headers,
                base,
                b"Contact,Note\nnora@example.test,Fictional\n",
                "fictional.csv",
            )
            case["document_id"] = UUID(version["document_id"])
            if operation == "batch-retry":
                with Session(engine) as session, session.begin():
                    document = session.get(Document, case["document_id"])
                    document.status = DocumentStatus.FAILED
                    job = session.scalar(select(ScanJob).where(ScanJob.document_id == document.id))
                    job.status, job.attempts, job.last_error_code = "failed", 3, "scan_failed"
    else:
        case["headers"] = _login(owner, "intake-owner@example.invalid")
    return case


def perform(case):
    client, operation, headers = case["client"], case["operation"], case["headers"]
    if operation == "batch-create":
        return client.post(
            "/api/v1/batches",
            headers=headers,
            json={
                "workspace_id": str(case["workspace"]),
                "name": "Fictional protected batch",
                "categories": ["email"],
                "phone_region": "GB",
            },
        )
    if operation == "batch-upload":
        return client.post(
            case["base"] + "/documents",
            headers=headers,
            files={"file": ("fictional.csv", b"Contact,Note\nnora@example.test,Fictional\n")},
        )
    if operation == "batch-retry":
        return client.post(
            case["base"] + "/documents/" + str(case["document_id"]) + "/retry", headers=headers
        )
    if operation == "batch-delete":
        return client.request("DELETE", case["base"], headers=headers, json={"confirmed": True})
    if operation == "paste":
        return client.post(
            "/api/v1/documents",
            headers=headers,
            json=_draft_body(case["workspace"], source="Fictional nora@example.test"),
        )
    filename, content = (
        ("fictional.docx", docx_sample())
        if operation == "file-docx"
        else ("fictional.csv", b"Contact,Note\nnora@example.test,Fictional\n")
    )
    return client.post(
        "/api/v1/documents/from-file",
        headers=headers,
        data={"workspace_id": str(case["workspace"]), "categories": "email"},
        files={"file": (filename, content)},
    )


def lifecycle_fingerprint(case):
    """Include bytes, queue leases, layouts, versions, deletion and audit state."""
    engine, workspace = case["engine"], case["workspace"]
    with Session(engine) as session:
        document_ids = list(
            session.scalars(select(Document.id).where(Document.workspace_id == workspace))
        )
        revision_ids = select(SourceRevision.id).where(SourceRevision.document_id.in_(document_ids))
        models = (
            (Batch, Batch.workspace_id == workspace),
            (Document, Document.workspace_id == workspace),
            (SourceRevision, SourceRevision.document_id.in_(document_ids)),
            (SourceStructure, SourceStructure.revision_id.in_(revision_ids)),
            (ScanJob, ScanJob.document_id.in_(document_ids)),
            (AuditEvent, AuditEvent.workspace_id == workspace),
        )
        rows = [
            sorted(
                [
                    tuple(getattr(row, column.name) for column in model.__table__.columns)
                    for row in session.scalars(select(model).where(condition))
                ],
                key=repr,
            )
            for model, condition in models
        ]
    return rows, {doc: storage_fingerprint(engine, doc) for doc in document_ids}


def after_operation(monkeypatch, case, phase, change):
    from app.batches import service
    from app.db import repository

    operation = case["operation"]
    if phase == "authorized":
        module, hook = (
            (repository, "active_workspace")
            if not operation.startswith("batch-")
            else (
                service,
                "active_workspace"
                if operation == "batch-create"
                else "owned_document"
                if operation == "batch-retry"
                else "owned_batch",
            )
        )
    else:
        module, hook = (
            (repository, "record_event")
            if not operation.startswith("batch-")
            else (
                service,
                "create_document_in_transaction"
                if operation == "batch-upload"
                else "flush"
                if operation == "batch-retry"
                else "record_event",
            )
        )
        if operation == "batch-retry":
            module = Session
    original, fired = getattr(module, hook), []

    def changed(*args, **kwargs):
        ready = True
        if operation == "batch-retry" and phase == "built":
            ready = any(
                isinstance(row, ScanJob)
                and row.document_id == case["document_id"]
                and row.status == "queued"
                for row in args[0].dirty
            )
        if hook == "record_event":
            ready = kwargs.get("event_code") == (
                "batch_created"
                if operation == "batch-create"
                else "batch_deleted"
                if operation == "batch-delete"
                else "document_created"
            )
        result = original(*args, **kwargs)
        if ready and not fired:
            fired.append(True)
            change()
        return result

    monkeypatch.setattr(module, hook, changed)
    return fired


@contextmanager
def another_active_workspace(case):
    workspace = uuid4()
    with Session(case["engine"]) as session, session.begin():
        session.add(
            Workspace(id=workspace, name="Fictional other workspace", content_retention_days=7)
        )
        session.flush()
        session.add(Membership(workspace_id=workspace, user_id=case["actor"], role="member"))
    try:
        yield
    finally:
        with Session(case["engine"]) as session, session.begin():
            session.execute(delete(Membership).where(Membership.workspace_id == workspace))
            session.execute(delete(Workspace).where(Workspace.id == workspace))


def assert_denied(response, status):
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"].startswith("application/json")
    assert all(
        value not in response.text
        for value in ("Fictional", "nora@example.test", "Contact", "Synthetic optional title")
    )


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("phase", PHASES)
@pytest.mark.parametrize("change", ("revoked", "expired", "disabled", "membership"))
def test_late_intake_or_batch_access_loss_rolls_back_all_owned_storage(
    intake_site,
    monkeypatch,
    operation,
    phase,
    change,
):
    case = mutation_case(intake_site, operation)
    before = lifecycle_fingerprint(case)
    fired = after_operation(monkeypatch, case, phase, lambda: change_actor(case, change))
    assert_denied(perform(case), 401)
    assert fired and lifecycle_fingerprint(case) == before


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("phase", PHASES)
def test_late_resource_membership_loss_denies_even_with_a_valid_other_workspace(
    intake_site,
    monkeypatch,
    operation,
    phase,
):
    case = mutation_case(intake_site, operation)
    with another_active_workspace(case):
        before = lifecycle_fingerprint(case)
        fired = after_operation(monkeypatch, case, phase, lambda: change_actor(case, "membership"))
        assert_denied(perform(case), 404)
        assert fired and lifecycle_fingerprint(case) == before
        assert case["client"].get("/api/v1/auth/session").status_code == 200


@pytest.mark.parametrize("operation", OPERATIONS)
def test_current_authorized_intake_and_batch_mutations_still_work(intake_site, operation):
    case = mutation_case(intake_site, operation)
    before = lifecycle_fingerprint(case)
    response = perform(case)
    assert response.status_code == (204 if operation in ("batch-retry", "batch-delete") else 201)
    assert lifecycle_fingerprint(case) != before
    with Session(case["engine"]) as session:
        if operation == "batch-create":
            assert session.get(Batch, UUID(response.json()["id"])).name_ciphertext is not None
        elif operation == "batch-delete":
            batch = session.get(Batch, case["batch_id"])
            assert batch.deleted_at is not None and batch.name_ciphertext is None
            assert session.get(Document, case["document_id"]).deleted_at is not None
            assert (
                session.scalar(
                    select(SourceRevision.id).where(
                        SourceRevision.document_id == case["document_id"]
                    )
                )
                is None
            )
        elif operation == "batch-retry":
            job = session.scalar(select(ScanJob).where(ScanJob.document_id == case["document_id"]))
            assert job.status == "queued" and job.attempts == 0 and job.last_error_code is None
        else:
            document = session.get(Document, UUID(response.json()["version"]["document_id"]))
            assert document.current_revision_id is not None
            if operation == "batch-upload":
                assert session.scalar(select(ScanJob.id).where(ScanJob.document_id == document.id))


@pytest.mark.parametrize("operation", ("batch-upload", "batch-retry"))
@pytest.mark.parametrize("phase", PHASES)
def test_batch_intake_or_retry_obeys_actual_wall_clock_expiry(
    intake_site, monkeypatch, operation, phase
):
    if operation == "batch-upload":
        from app.batches.service import create_batch

        case = mutation_case(intake_site, "batch-create")
        # Insert an actually old immutable snapshot through the real service.
        # Both ORM and database immutability guards remain enabled.
        batch_id = create_batch(
            case["engine"],
            case["actor"],
            CreateBatchRequest(
                workspace_id=case["workspace"],
                name="Fictional expiring batch",
                categories=["email"],
                retention_days=7,
            ),
            KeyRing.from_settings(case["client"].app.state.settings),
            datetime.now(UTC) - timedelta(days=7) + timedelta(seconds=2),
        )
        case.update(operation=operation, batch_id=batch_id, base=f"/api/v1/batches/{batch_id}")
    else:
        case = mutation_case(intake_site, operation)
        with Session(case["engine"]) as session, session.begin():
            session.get(Document, case["document_id"]).expires_at = datetime.now(UTC) + timedelta(
                seconds=2
            )
    before = lifecycle_fingerprint(case)
    fired = after_operation(monkeypatch, case, phase, lambda: time.sleep(2.2))
    assert_denied(perform(case), 410)
    assert fired and lifecycle_fingerprint(case) == before


@pytest.mark.parametrize("phase", ("assembled", "serialized"))
@pytest.mark.parametrize("change", ("revoked", "expired", "disabled"))
def test_committed_batch_creation_cannot_release_a_later_denied_private_title(
    intake_site,
    monkeypatch,
    phase,
    change,
):
    from app.batches import api

    case = mutation_case(intake_site, "batch-create")
    module, hook = (api, "load_batch") if phase == "assembled" else (BatchView, "model_dump_json")
    original, fired = getattr(module, hook), []

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        if not fired:
            fired.append(True)
            change_actor(case, change)
        return result

    monkeypatch.setattr(module, hook, changed)
    assert_denied(perform(case), 401)
    assert fired
    with Session(case["engine"]) as session:
        # This transaction was authorized at commit. Only the later private response is denied.
        assert session.scalar(select(Batch.id).where(Batch.workspace_id == case["workspace"]))
