"""Real stored cohorts, deduplicated output history and fresh access checks."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, event, select, update
from sqlalchemy.orm import Session

from app.db.crypto import KeyRing
from app.db.models import (
    Document,
    ExportEvent,
    Finding,
    Membership,
    ReviewCompletion,
    User,
    Workspace,
)
from app.db.models import Session as StoredSession
from app.db.team_review import ReviewHandoff
from app.workspace.documents import load_overview
from tests.intake_support import _draft_body, _login


@pytest.fixture
def additional_workspace(intake_site):
    _, _, engine, workspace_id, owner_id = intake_site
    extra_id = uuid4()
    with Session(engine) as session, session.begin():
        session.add(Workspace(id=extra_id, name="Other owned workspace"))
        session.flush()
        session.add(Membership(workspace_id=extra_id, user_id=owner_id, role="member"))
    try:
        yield extra_id
    finally:
        with Session(engine) as session, session.begin():
            session.execute(
                update(Document)
                .where(Document.workspace_id == extra_id)
                .values(workspace_id=workspace_id)
            )
            session.execute(delete(Membership).where(Membership.workspace_id == extra_id))
            session.execute(delete(Workspace).where(Workspace.id == extra_id))


def create(client, headers, workspace_id):
    response = client.post(
        "/api/v1/documents",
        json=_draft_body(
            workspace_id, source="Fictional private source canary", title="PRIVATE TITLE"
        ),
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["version"]


def completion(session, document, actor, when, decision_version=0):
    item = ReviewCompletion(
        id=uuid4(),
        document_id=document.id,
        source_revision_id=document.current_revision_id,
        decision_version=decision_version,
        settings_version=1,
        confirmed_by=actor,
        confirmed_at=when,
    )
    session.add(item)
    session.flush()
    return item


def output(session, document, actor, confirmed, kind, when):
    session.add(
        ExportEvent(
            document_id=document.id,
            actor_id=actor,
            completion_id=confirmed.id,
            format=kind,
            occurred_at=when,
        )
    )


def test_actual_owner_cohort_counts_first_confirmation_and_distinct_outputs(
    intake_site, monkeypatch
):
    owner, other, engine, workspace_id, owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    other_headers = _login(other, "intake-other@example.invalid")
    versions = [create(owner, headers, workspace_id) for _ in range(4)]
    foreign = create(other, other_headers, workspace_id)
    now = datetime.now(UTC)
    start = now - timedelta(hours=2)
    with Session(engine) as session, session.begin():
        session.get(Membership, (workspace_id, owner_id)).role = "administrator"
        for version in versions:
            document = session.get(Document, UUID(version["document_id"]))
            document.created_at = start
        first, second, report_only, pending = [
            session.get(Document, UUID(version["document_id"])) for version in versions
        ]
        confirmed = completion(session, first, owner_id, start + timedelta(minutes=10))
        completion(session, first, owner_id, start + timedelta(minutes=90), decision_version=1)
        for kind in ("txt", "txt", "pdf", "report"):
            output(session, first, owner_id, confirmed, kind, start + timedelta(minutes=100))
        second_confirmed = completion(session, second, owner_id, start + timedelta(minutes=30))
        output(session, second, owner_id, second_confirmed, "copy", start + timedelta(minutes=100))
        report_confirmed = completion(session, report_only, owner_id, start + timedelta(minutes=20))
        output(
            session,
            report_only,
            owner_id,
            report_confirmed,
            "report",
            start + timedelta(minutes=100),
        )
        for category, offset in (("email", 0), ("email", 4), ("phone", 8)):
            session.add(
                Finding(
                    document_id=first.id,
                    source_revision_id=first.current_revision_id,
                    category=category,
                    origin="manual",
                    start_offset=offset,
                    end_offset=offset + 3,
                )
            )
        session.add(
            Finding(
                document_id=pending.id,
                source_revision_id=pending.current_revision_id,
                category="secret",
                origin="manual",
                start_offset=0,
                end_offset=3,
                removed_at=now,
            )
        )
        foreign_doc = session.get(Document, UUID(foreign["document_id"]))
        session.add(
            Finding(
                document_id=foreign_doc.id,
                source_revision_id=foreign_doc.current_revision_id,
                category="national_id",
                origin="manual",
                start_offset=0,
                end_offset=3,
            )
        )
        session.add(ReviewHandoff(document_id=foreign_doc.id, reviewer_id=owner_id, generation=1))
    monkeypatch.setattr(
        KeyRing, "decrypt_text", lambda *args: pytest.fail("Overview decrypted content")
    )
    response = owner.get(f"/api/v1/workspaces/{workspace_id}/overview")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    value = response.json()
    assert value["own_total"] == 4 and value["workspace_total"] == 5
    analytics = value["analytics"]
    assert analytics["cohort_documents"] == 4
    assert analytics["confirmed_documents"] == 3
    assert analytics["average_time_to_confirm_seconds"] == 1200
    assert analytics["exported_documents"] == 2 and analytics["export_rate"] == 0.5
    assert analytics["findings_total"] == 3
    assert analytics["categories"] == [
        {"category": "email", "count": 2},
        {"category": "phone", "count": 1},
    ]
    assert "PRIVATE TITLE" not in response.text and "Fictional private source" not in response.text
    assert foreign["document_id"] not in response.text


def test_cohort_window_expiry_deletion_other_workspace_and_empty_denominators(
    intake_site, additional_workspace
):
    owner, _, engine, workspace_id, owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    versions = [create(owner, headers, workspace_id) for _ in range(7)]
    now = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        docs = [session.get(Document, UUID(v["document_id"])) for v in versions]
        docs[0].created_at = now - timedelta(days=30)  # inclusive boundary
        docs[1].created_at = now - timedelta(days=30, microseconds=1)
        docs[2].created_at = now + timedelta(seconds=1)
        docs[3].created_at = now - timedelta(days=2)
        docs[3].expires_at = now  # exclusive expiry boundary
        docs[4].deleted_at = now
        docs[5].status = "expired"
        docs[6].workspace_id = additional_workspace
        for doc in docs:
            session.add(
                Finding(
                    document_id=doc.id,
                    source_revision_id=doc.current_revision_id,
                    category="email",
                    origin="manual",
                    start_offset=0,
                    end_offset=3,
                )
            )
    record = load_overview(engine, workspace_id=workspace_id, actor_id=owner_id, now=now)
    assert record.analytics.cohort_documents == 1
    assert record.analytics.findings_total == 1
    assert record.analytics.confirmed_documents == 0
    assert record.analytics.average_time_to_confirm_seconds is None
    assert record.analytics.export_rate == 0
    record = load_overview(
        engine, workspace_id=workspace_id, actor_id=owner_id, now=now + timedelta(days=40)
    )
    assert record.analytics.cohort_documents == 0
    assert record.analytics.export_rate is None
    assert record.analytics.average_time_to_confirm_seconds is None
    assert record.analytics.categories == []


def test_current_revision_removed_findings_future_and_invalid_history_are_excluded(intake_site):
    owner, _, engine, workspace_id, owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    version = create(owner, headers, workspace_id)
    added = owner.post(
        f"/api/v1/documents/{version['document_id']}/findings",
        headers=headers,
        json={
            "expected": version,
            "span": {"start": 0, "end": 9},
            "category": "email",
        },
    )
    assert added.status_code == 200
    revised = owner.put(
        f"/api/v1/documents/{version['document_id']}/source",
        headers=headers,
        json={
            "expected": added.json()["version"],
            "source": "New fictional private source",
        },
    )
    assert revised.status_code == 200
    now = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        doc = session.get(Document, UUID(version["document_id"]))
        old = completion(session, doc, owner_id, doc.created_at - timedelta(seconds=1))
        future = completion(session, doc, owner_id, now + timedelta(hours=1), decision_version=1)
        output(session, doc, owner_id, old, "txt", doc.created_at - timedelta(seconds=1))
        output(session, doc, owner_id, future, "pdf", now + timedelta(hours=1))
    record = load_overview(engine, workspace_id=workspace_id, actor_id=owner_id, now=now)
    assert record.analytics.findings_total == 0
    assert record.analytics.confirmed_documents == 0
    assert record.analytics.exported_documents == 0
    assert record.analytics.average_time_to_confirm_seconds is None


@pytest.mark.parametrize("change", ["membership", "disabled_user", "role", "session"])
def test_overview_refreshes_access_role_and_session_after_aggregating(
    intake_site, monkeypatch, change
):
    from app.workspace import documents

    owner, other, engine, workspace_id, owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    create(owner, headers, workspace_id)
    other_headers = _login(other, "intake-other@example.invalid")
    create(other, other_headers, workspace_id)
    with Session(engine) as session, session.begin():
        session.get(Membership, (workspace_id, owner_id)).role = "administrator"
    original = documents.load_analytics

    def aggregate_then_change(*args, **kwargs):
        value = original(*args, **kwargs)
        with Session(engine) as session, session.begin():
            if change == "membership":
                session.get(Membership, (workspace_id, owner_id)).revoked_at = datetime.now(UTC)
            elif change == "disabled_user":
                session.get(User, owner_id).disabled_at = datetime.now(UTC)
            elif change == "role":
                session.get(Membership, (workspace_id, owner_id)).role = "member"
            else:
                for stored in session.scalars(
                    select(StoredSession).where(StoredSession.user_id == owner_id)
                ):
                    stored.revoked_at = datetime.now(UTC)
        return value

    monkeypatch.setattr(documents, "load_analytics", aggregate_then_change)
    response = owner.get(f"/api/v1/workspaces/{workspace_id}/overview")
    if change == "role":
        assert response.status_code == 200 and response.json()["workspace_total"] is None
        assert response.json()["analytics"]["cohort_documents"] == 1
    else:
        assert response.status_code == (401 if change == "session" else 404)
        assert "analytics" not in response.text


def test_overview_rejects_missing_membership_and_session(intake_site):
    owner, _, _, workspace_id, _ = intake_site
    path = f"/api/v1/workspaces/{workspace_id}/overview"
    assert owner.get(path).status_code == 401
    _login(owner, "intake-owner@example.invalid")
    assert owner.get(f"/api/v1/workspaces/{uuid4()}/overview").status_code == 404


@pytest.mark.parametrize("kind", ["copy", "txt", "docx", "csv", "pdf", "report"])
def test_reviewed_output_formats_and_report_only_denominator(intake_site, kind):
    owner, _, engine, workspace_id, owner_id = intake_site
    version = create(owner, _login(owner, "intake-owner@example.invalid"), workspace_id)
    now = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        doc = session.get(Document, UUID(version["document_id"]))
        confirmed = completion(session, doc, owner_id, now)
        output(session, doc, owner_id, confirmed, kind, now)
    analytics = load_overview(
        engine, workspace_id=workspace_id, actor_id=owner_id, now=now
    ).analytics
    assert analytics.cohort_documents == 1 and analytics.confirmed_documents == 1
    assert analytics.exported_documents == int(kind != "report")
    assert analytics.export_rate == int(kind != "report")


@pytest.mark.parametrize("count", [1, 501])
def test_overview_uses_constant_aggregate_queries_without_loading_content(intake_site, count):
    owner, _, engine, workspace_id, owner_id = intake_site
    now = datetime.now(UTC)
    protected = KeyRing.from_settings(owner.app.state.settings).encrypt_text(
        "Encrypted title canary"
    )
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                Document(
                    workspace_id=workspace_id,
                    owner_id=owner_id,
                    title_ciphertext=protected.ciphertext,
                    title_key_id=protected.key_id,
                    created_at=now - timedelta(seconds=1),
                    expires_at=now + timedelta(days=1),
                )
                for _ in range(count)
            ]
        )
    statements = []

    def record(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    event.listen(engine, "before_cursor_execute", record)
    try:
        result = load_overview(engine, workspace_id=workspace_id, actor_id=owner_id, now=now)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert result.own_total == result.analytics.cohort_documents == count
    assert len(statements) == 9
    assert all("title_ciphertext" not in sql and "text_ciphertext" not in sql for sql in statements)
