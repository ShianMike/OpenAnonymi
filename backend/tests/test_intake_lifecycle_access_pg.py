"""Real intake transactions preserve owned storage on late access loss."""

from contextlib import contextmanager
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, Document, Membership, SourceRevision, Workspace
from app.db.source_structures import SourceStructure
from tests.import_fixtures import docx_sample
from tests.intake_support import _draft_body, _login
from tests.test_content_read_access_pg import change_actor
from tests.test_source_csv_mutation_access_pg import storage_fingerprint

OPERATIONS = ("paste", "file-docx", "file-csv")
PHASES = ("authorized", "built")


def mutation_case(site, operation):
    owner, _, engine, workspace, actor = site
    return {
        "client": owner,
        "engine": engine,
        "workspace": workspace,
        "actor": actor,
        "operation": operation,
        "headers": _login(owner, "intake-owner@example.invalid"),
    }


def perform(case):
    client, operation, headers = case["client"], case["operation"], case["headers"]
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
    """Include encrypted bytes, layouts, versions, deletion and audit state."""
    engine, workspace = case["engine"], case["workspace"]
    with Session(engine) as session:
        document_ids = list(
            session.scalars(select(Document.id).where(Document.workspace_id == workspace))
        )
        revision_ids = select(SourceRevision.id).where(SourceRevision.document_id.in_(document_ids))
        models = (
            (Document, Document.workspace_id == workspace),
            (SourceRevision, SourceRevision.document_id.in_(document_ids)),
            (SourceStructure, SourceStructure.revision_id.in_(revision_ids)),
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
    from app.db import repository

    hook = "active_workspace" if phase == "authorized" else "record_event"
    original, fired = getattr(repository, hook), []

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        ready = hook != "record_event" or kwargs.get("event_code") == "document_created"
        if ready and not fired:
            fired.append(True)
            change()
        return result

    monkeypatch.setattr(repository, hook, changed)
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
def test_late_intake_access_loss_rolls_back_all_owned_storage(
    intake_site, monkeypatch, operation, phase, change
):
    case = mutation_case(intake_site, operation)
    before = lifecycle_fingerprint(case)
    fired = after_operation(monkeypatch, case, phase, lambda: change_actor(case, change))
    assert_denied(perform(case), 401)
    assert fired and lifecycle_fingerprint(case) == before


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("phase", PHASES)
def test_late_resource_membership_loss_denies_even_with_a_valid_other_workspace(
    intake_site, monkeypatch, operation, phase
):
    case = mutation_case(intake_site, operation)
    with another_active_workspace(case):
        before = lifecycle_fingerprint(case)
        fired = after_operation(monkeypatch, case, phase, lambda: change_actor(case, "membership"))
        assert_denied(perform(case), 404)
        assert fired and lifecycle_fingerprint(case) == before
        assert case["client"].get("/api/v1/auth/session").status_code == 200


@pytest.mark.parametrize("operation", OPERATIONS)
def test_current_authorized_intake_mutations_still_work(intake_site, operation):
    case = mutation_case(intake_site, operation)
    before = lifecycle_fingerprint(case)
    response = perform(case)
    assert response.status_code == 201
    assert lifecycle_fingerprint(case) != before
    with Session(case["engine"]) as session:
        document = session.get(Document, UUID(response.json()["version"]["document_id"]))
        assert document.current_revision_id is not None
