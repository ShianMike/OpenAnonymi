"""Global clock health, abandoned runs and workspace-only counts require an admin."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.maintenance import MaintenanceRun
from app.db.models import Document, Membership, Workspace
from app.maintenance.schedule import CLEANUP_OVERDUE_AFTER
from app.maintenance.service import load_cleanup_health, run_cleanup
from tests.intake_support import _draft_body, _login
from tests.test_maintenance_pg import expired_documents


def administrator(site):
    with Session(site[2]) as session, session.begin():
        session.get(Membership, (site[3], site[4])).role = "administrator"


def health(site, now):
    return load_cleanup_health(site[2], workspace_id=site[3], actor_id=site[4], now=now)


def test_never_recent_exact_threshold_and_overdue(maintenance_site):
    administrator(maintenance_site)
    now = datetime.now(UTC)
    initial = health(maintenance_site, now)
    assert initial.overdue and initial.last_success_at is None and initial.last_failure_at is None
    run_cleanup(maintenance_site[2], trigger="cli", clock=lambda: now)
    recent = health(maintenance_site, now)
    assert not recent.overdue and recent.last_success_at == now
    assert not health(maintenance_site, now + CLEANUP_OVERDUE_AFTER).overdue
    assert health(maintenance_site, now + CLEANUP_OVERDUE_AFTER + timedelta(microseconds=1)).overdue


def test_abandoned_counts_as_failure_before_next_pass(maintenance_site):
    administrator(maintenance_site)
    now = datetime.now(UTC)
    with Session(maintenance_site[2]) as session, session.begin():
        session.add(
            MaintenanceRun(
                id=uuid4(), trigger="startup", started_at=now - timedelta(hours=2), status="running"
            )
        )
    result = health(maintenance_site, now)
    assert result.last_failure_at == now - timedelta(hours=1)
    assert result.overdue


def test_route_is_admin_only_and_does_not_reveal_other_workspaces(maintenance_site):
    owner, other, _, workspace, _ = maintenance_site
    _login(owner, "intake-owner@example.invalid")
    _login(other, "intake-other@example.invalid")
    path = f"/api/v1/workspaces/{workspace}/cleanup-health"
    assert owner.get(path).status_code == 404
    administrator(maintenance_site)
    expired_documents(maintenance_site, count=2)
    result = owner.get(path)
    assert result.status_code == 200 and result.json()["documents_awaiting_purge"] == 2
    assert set(result.json()) == {
        "last_success_at",
        "last_failure_at",
        "overdue",
        "documents_awaiting_purge",
        "checked_at",
    }
    assert "MAINTENANCE_SENTINEL" not in result.text
    assert other.get(path).status_code == 404
    assert owner.get(f"/api/v1/workspaces/{uuid4()}/cleanup-health").status_code == 404
    run_cleanup(maintenance_site[2], trigger="cli")
    assert owner.get(path).json()["documents_awaiting_purge"] == 0


def test_awaiting_count_is_scoped_even_for_a_multi_workspace_admin(maintenance_site):
    owner, _, engine, _workspace, actor = maintenance_site
    administrator(maintenance_site)
    expired_documents(maintenance_site, count=2)
    other_workspace = uuid4()
    try:
        with Session(engine) as session, session.begin():
            session.add(Workspace(id=other_workspace, name="Another synthetic workspace"))
            session.flush()
            session.add(
                Membership(workspace_id=other_workspace, user_id=actor, role="administrator")
            )
        headers = _login(owner, "intake-owner@example.invalid")
        saved = owner.post("/api/v1/documents", headers=headers, json=_draft_body(other_workspace))
        assert saved.status_code == 201
        now = datetime.now(UTC)
        with Session(engine) as session, session.begin():
            row = session.query(Document).filter(Document.workspace_id == other_workspace).one()
            row.created_at = now - timedelta(days=2)
            row.expires_at = now - timedelta(days=1)
        assert health(maintenance_site, now).documents_awaiting_purge == 2
        assert (
            load_cleanup_health(
                engine, workspace_id=other_workspace, actor_id=actor, now=now
            ).documents_awaiting_purge
            == 1
        )
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(Document).where(Document.workspace_id == other_workspace))
            session.execute(delete(Membership).where(Membership.workspace_id == other_workspace))
            session.execute(delete(Workspace).where(Workspace.id == other_workspace))
