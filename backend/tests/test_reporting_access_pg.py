"""Actual reporting and document-management work rechecks late access loss."""
import inspect
from datetime import UTC, datetime, timedelta
from time import sleep
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.document_preferences import DocumentPreference
from app.db.models import Document, Membership, User, Workspace
from app.db.models import Session as StoredSession
from app.db.team_review import ReviewHandoff
from tests.intake_support import _login
from tests.reporting_access_support import (
    READS,
    WRITES,
    after_json,
    make_case,
    perform,
    state,
    watch_prepared,
)

JSON = tuple(dict.fromkeys((*READS, *WRITES)))


def lose_access(case, change):
    now = datetime.now(UTC)
    with Session(case["engine"]) as session, session.begin():
        if change in ("membership", "role"):
            row = session.get(Membership, (case["workspace"], case["actor"]))
            if change == "role":
                row.role = "member"
            else:
                row.revoked_at = now
        elif change == "disabled":
            session.get(User, case["actor"]).disabled_at = now
        else:
            row = session.get(StoredSession, case["current_session"])
            if change == "revoked":
                row.revoked_at = now
            else:
                row.created_at, row.expires_at = now - timedelta(days=1), now - timedelta(seconds=1)


def denied(response, status=401):
    assert response.status_code == status and response.headers["cache-control"] == "no-store"
    assert set(response.json()) == {"code", "message", "details"} and not response.json()["details"]
    assert "Synthetic optional title" not in response.text and "intake-owner@example.invalid" not in response.text


@pytest.mark.parametrize("operation", WRITES)
@pytest.mark.parametrize("change", ("revoked", "expired", "membership"))
def test_prepared_document_management_rolls_back_after_session_loss(intake_site, operation, change):
    case = make_case(intake_site, operation)
    before = state(case)
    fired, remove = watch_prepared(case, lambda: lose_access(case, change))
    try:
        denied(perform(case))
    finally:
        remove()
    assert fired and state(case) == before


@pytest.mark.parametrize("operation", JSON)
@pytest.mark.parametrize("change", ("revoked", "expired", "disabled", "membership"))
def test_serialized_reporting_and_flags_deny_ended_access(intake_site, monkeypatch, operation, change):
    case = make_case(intake_site, operation)
    before = state(case)
    fired = after_json(monkeypatch, case, lambda: lose_access(case, change))
    denied(perform(case))
    assert fired and (state(case) != before) == (operation in WRITES)


@pytest.mark.parametrize("operation", ("overview", "activity", "admin-activity"))
def test_admin_metadata_does_not_escape_after_serialized_role_loss(intake_site, monkeypatch, operation):
    case = make_case(intake_site, operation)
    fired = after_json(monkeypatch, case, lambda: lose_access(case, "role"))
    denied(perform(case), 404)
    assert fired


@pytest.mark.parametrize("operation", JSON)
def test_requested_workspace_loss_with_another_active_membership_denies_metadata(intake_site, monkeypatch, operation):
    case = make_case(intake_site, operation)
    other_workspace = uuid4()
    with Session(case["engine"]) as session, session.begin():
        session.add(Workspace(id=other_workspace, name="Second synthetic scope"))
        session.flush()
        session.add(Membership(workspace_id=other_workspace, user_id=case["actor"], role="member"))
    try:
        fired = after_json(monkeypatch, case, lambda: lose_access(case, "membership"))
        denied(perform(case), 404)
        assert fired and case["client"].get("/api/v1/auth/session").status_code == 200
    finally:
        with Session(case["engine"]) as session, session.begin():
            session.execute(delete(Membership).where(Membership.workspace_id == other_workspace))
            session.execute(delete(Workspace).where(Workspace.id == other_workspace))


@pytest.mark.parametrize("change", ("expiry", "policy"))
@pytest.mark.parametrize("operation", ("retention-read", "retention-renew"))
def test_serialized_retention_requires_current_expiry_and_policy(intake_site, monkeypatch, operation, change):
    case = make_case(intake_site, operation)
    def changed():
        with Session(case["engine"]) as session, session.begin():
            if change == "expiry":
                session.get(Document, case["document"]).expires_at += timedelta(days=1)
            else:
                session.get(Workspace, case["workspace"]).content_retention_days = 1
    fired = after_json(monkeypatch, case, changed)
    denied(perform(case), 409)
    assert fired


@pytest.mark.parametrize("operation", ("preference", "bulk-preference"))
@pytest.mark.parametrize("change", ("deleted", "replaced"))
def test_serialized_flags_require_exact_current_preference(intake_site, monkeypatch, operation, change):
    case = make_case(intake_site, operation)
    def changed():
        with Session(case["engine"]) as session, session.begin():
            row = session.get(DocumentPreference, (case["actor"], case["document"]))
            if change == "deleted":
                session.delete(row)
            else:
                row.favorite, row.pinned = False, True
    fired = after_json(monkeypatch, case, changed)
    denied(perform(case), 409)
    assert fired


def test_unchanged_false_preference_checks_after_actual_view_preparation(intake_site, monkeypatch):
    from app.workspace.organize import DocumentPreferenceView
    case = make_case(intake_site, "preference")
    case["body"] = {"favorite":False}
    before = state(case)
    original, fired = DocumentPreferenceView.__init__, []
    def prepared(self, *args, **kwargs):
        original(self, *args, **kwargs)
        if not fired:
            fired.append(True)
            lose_access(case, "revoked")
    monkeypatch.setattr(DocumentPreferenceView, "__init__", prepared)
    denied(perform(case))
    assert fired and state(case) == before


def test_real_original_expiry_during_renewal_prevents_revival(intake_site):
    case = make_case(intake_site, "retention-renew")
    with Session(case["engine"]) as session, session.begin():
        row = session.get(Document, case["document"])
        now = datetime.now(UTC)
        row.created_at, row.expires_at = now - timedelta(days=1), now + timedelta(seconds=1)
        case["body"]["expected_expires_at"] = row.expires_at.isoformat()
    before = state(case)
    fired, remove = watch_prepared(case, lambda: sleep(2))
    try:
        denied(perform(case), 410)
    finally:
        remove()
    assert fired and state(case) == before


@pytest.mark.parametrize("operation", ("preference", "bulk-preference"))
def test_prepared_reviewer_flags_roll_back_after_actual_handoff_loss(intake_site, operation):
    case = make_case(intake_site, operation)
    other = intake_site[1]
    case["client"], case["headers"] = other, _login(other, "intake-other@example.invalid")
    with Session(case["engine"]) as session, session.begin():
        actor = session.scalar(select(User.id).where(User.email == "intake-other@example.invalid"))
        session.add(ReviewHandoff(document_id=case["document"], reviewer_id=actor, generation=1))
    before = state(case)
    def remove_handoff():
        with Session(case["engine"]) as session, session.begin():
            session.execute(delete(ReviewHandoff).where(ReviewHandoff.document_id == case["document"]))
    fired, remove = watch_prepared(case, remove_handoff)
    try:
        response = perform(case)
    finally:
        remove()
    if operation == "preference":
        denied(response, 404)
    else:
        assert response.status_code == 200 and response.json()["outcomes"][0]["outcome"] == "not_found"
    assert fired and state(case) == before


@pytest.mark.parametrize("operation", ("admin-activity", "admin-csv"))
def test_session_ending_during_final_admin_scope_queries_denies_metadata(intake_site, monkeypatch, operation):
    from app.workspace import admin_activity
    case = make_case(intake_site, "admin-activity")
    if operation == "admin-csv":
        case["path"] += "/csv"
    original, fired = admin_activity.require_administrator, []
    def authorized(*args, **kwargs):
        result = original(*args, **kwargs)
        if not fired and inspect.currentframe().f_back.f_code.co_name == "require_current_admin":
            fired.append(True)
            lose_access(case, "revoked")
        return result
    monkeypatch.setattr(admin_activity, "require_administrator", authorized)
    denied(perform(case))
    assert fired
