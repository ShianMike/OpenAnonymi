"""Real team/confirmation/scan boundaries deny lost access without partial content writes."""

import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AuditEvent,
    Document,
    Finding,
    Membership,
    ScanRun,
    SourceRevision,
    User,
    Workspace,
)
from app.db.team_review import ReviewHandoff
from app.team_review.comments import CommentView
from app.team_review.service import HandoffView, TeammateView
from tests.intake_support import _draft_body, _login
from tests.team_access_support import (
    OPERATIONS,
    after_team,
    team_case,
    team_fingerprint,
    team_perform,
)
from tests.test_content_read_access_pg import change_actor
from tests.test_intake_lifecycle_access_pg import another_active_workspace, assert_denied


def scan_content_fingerprint(case):
    """The authorized scan claim may persist; denied result content must not."""
    with Session(case["engine"]) as session:
        document = session.get(Document, case["document_id"])
        rows = [
            sorted(
                [
                    tuple(getattr(row, column.name) for column in model.__table__.columns)
                    for row in session.scalars(
                        select(model).where(model.document_id == document.id)
                    )
                ],
                key=repr,
            )
            for model in (Finding, SourceRevision, AuditEvent)
        ]
        return (
            document.current_revision_id,
            document.decision_version,
            document.settings_version,
            rows,
        )


def fingerprint(case):
    return scan_content_fingerprint(case) if case["operation"] == "scan" else team_fingerprint(case)


def assert_storage(case, before):
    assert fingerprint(case) == before
    if case["operation"] == "scan":
        with Session(case["engine"]) as session:
            run = session.scalar(
                select(ScanRun).where(
                    ScanRun.document_id == case["document_id"],
                    ScanRun.settings_version == case["body"]["expected"]["settings_version"],
                )
            )
            assert run and run.status == "superseded" and run.finished_at is not None
            assert run.match_count is None


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("change", ("revoked", "expired", "disabled", "membership"))
def test_team_confirmation_and_scan_rollback_after_real_late_access_loss(
    intake_site,
    monkeypatch,
    operation,
    change,
):
    case = team_case(intake_site, operation)
    before = fingerprint(case)
    fired = after_team(monkeypatch, case, lambda: change_actor(case, change))
    assert_denied(team_perform(case), 401)
    assert fired
    assert_storage(case, before)


@pytest.mark.parametrize("operation", OPERATIONS)
def test_team_operations_recheck_after_actual_document_lock(intake_site, monkeypatch, operation):
    from app.detection import service as detection
    from app.reviews import service as reviews
    from app.team_review import comments, service

    case = team_case(intake_site, operation)
    before = fingerprint(case)
    module = (
        service
        if ("handoff" in operation or "approval" in operation)
        else comments
        if "comment" in operation
        else reviews
        if "confirm" in operation
        else detection
    )
    hook = (
        "owned_document"
        if (
            "handoff" in operation
            or "confirm" in operation
            or "scan" in operation
            or operation == "noop-settings"
        )
        else "review_document"
    )
    original, fired = getattr(module, hook), []

    def locked(*args, **kwargs):
        result = original(*args, **kwargs)
        if not fired:
            fired.append(True)
            change_actor(case, "revoked")
        return result

    monkeypatch.setattr(module, hook, locked)
    assert_denied(team_perform(case), 401)
    assert fired and fingerprint(case) == before
    if operation == "scan":
        with Session(case["engine"]) as session:
            assert (
                session.scalar(
                    select(ScanRun.id).where(
                        ScanRun.document_id == case["document_id"],
                        ScanRun.settings_version == case["body"]["expected"]["settings_version"],
                    )
                )
                is None
            )


@pytest.mark.parametrize("operation", OPERATIONS)
def test_team_content_expiry_uses_current_wall_clock(intake_site, monkeypatch, operation):
    case = team_case(intake_site, operation)
    # Leave time for the real storage fingerprint and HTTP authorization on a busy
    # runner, then cross the same persisted deadline at the late operation hook.
    expires_at = datetime.now(UTC) + timedelta(seconds=5)
    with Session(case["engine"]) as session, session.begin():
        session.get(Document, case["document_id"]).expires_at = expires_at
    before = fingerprint(case)

    def cross_deadline():
        time.sleep(max(0, (expires_at - datetime.now(UTC)).total_seconds()) + 0.1)

    fired = after_team(monkeypatch, case, cross_deadline)
    assert_denied(team_perform(case), 410)
    assert fired
    assert_storage(case, before)


@pytest.mark.parametrize(
    "operation", ("handoff", "approval", "comment", "confirm", "scan-settings", "scan")
)
def test_resource_membership_loss_with_another_workspace_remains_a_404(
    intake_site,
    monkeypatch,
    operation,
):
    case = team_case(intake_site, operation)
    with another_active_workspace(case):
        before = fingerprint(case)
        fired = after_team(monkeypatch, case, lambda: change_actor(case, "membership"))
        assert_denied(team_perform(case), 404)
        assert fired
        assert_storage(case, before)
        assert case["client"].get("/api/v1/auth/session").status_code == 200


@pytest.mark.parametrize("operation", OPERATIONS)
def test_current_authorized_team_confirmation_and_scan_still_work(intake_site, operation):
    case = team_case(intake_site, operation)
    response = team_perform(case)
    assert response.status_code == (
        204 if operation == "delete-comment" else 201 if "comment" in operation else 200
    )
    if "comment" in operation and operation != "delete-comment":
        assert response.json()["text"] == "Fictional private discussion Café 東京"
    assert case["client"].get("/api/v1/auth/session").status_code == 200


def read_case(site, route):
    case = team_case(site, "noop-comment")
    if route == "comments":
        case.update(path=case["base"] + case["suffix"], model=CommentView, hook="load_comments")
    elif route == "handoff":
        case.update(path=case["base"] + "/handoff", model=HandoffView, hook="load_handoff")
    else:
        case.update(
            client=case["owner"],
            actor=case["owner_id"],
            path=case["base"] + "/teammates",
            model=TeammateView,
            hook="list_teammates",
        )
    assert case["client"].get(case["path"]).status_code == 200
    return case


def after_view(monkeypatch, case, phase, change):
    from app.team_review import api

    module, hook = (
        (case["model"], "model_dump_json") if phase == "serialized" else (api, case["hook"])
    )
    original, fired = getattr(module, hook), []

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        if not fired:
            fired.append(True)
            change()
        return result

    monkeypatch.setattr(module, hook, changed)
    return fired


@pytest.mark.parametrize("route", ("comments", "handoff", "teammates"))
@pytest.mark.parametrize("phase", ("assembled", "serialized"))
@pytest.mark.parametrize("change", ("revoked", "expired", "disabled"))
def test_private_team_read_denies_ended_session_after_real_assembly_or_json(
    intake_site,
    monkeypatch,
    route,
    phase,
    change,
):
    case = read_case(intake_site, route)
    fired = after_view(monkeypatch, case, phase, lambda: change_actor(case, change))
    assert_denied(case["client"].get(case["path"]), 401)
    assert fired


@pytest.mark.parametrize("route", ("comments", "handoff", "teammates"))
def test_team_read_denies_actual_content_expiry_during_serialization(
    intake_site, monkeypatch, route
):
    case = read_case(intake_site, route)
    with Session(case["engine"]) as session, session.begin():
        document = session.get(Document, case["document_id"])
        document.expires_at = datetime.now(UTC) + timedelta(seconds=1)
    fired = after_view(monkeypatch, case, "serialized", lambda: time.sleep(1.2))
    assert_denied(case["client"].get(case["path"]), 410)
    assert fired


@pytest.mark.parametrize("route", ("comments", "handoff"))
def test_removing_reviewer_grant_after_json_denies_private_discussion(
    intake_site, monkeypatch, route
):
    case = read_case(intake_site, route)

    def revoke_grant():
        with Session(case["engine"]) as session, session.begin():
            session.get(ReviewHandoff, case["document_id"]).reviewer_id = None

    fired = after_view(monkeypatch, case, "serialized", revoke_grant)
    assert_denied(case["client"].get(case["path"]), 404)
    assert fired and case["client"].get("/api/v1/auth/session").status_code == 200


@pytest.mark.parametrize("route", ("comments", "handoff", "teammates"))
def test_serialized_team_body_is_withheld_when_its_actual_rows_change(
    intake_site, monkeypatch, route
):
    case = read_case(intake_site, route)

    def change_rows():
        with Session(case["engine"]) as session, session.begin():
            if route == "comments":
                from app.db.team_review import FindingComment

                session.delete(session.get(FindingComment, UUID(case["body"]["id"])))
            elif route == "handoff":
                session.get(Workspace, case["workspace"]).approval_policy = "always"
            else:
                session.get(
                    Membership, (case["workspace"], case["reviewer_id"])
                ).revoked_at = datetime.now(UTC)

    fired = after_view(monkeypatch, case, "serialized", change_rows)
    response = case["client"].get(case["path"])
    assert_denied(response, 409)
    assert '"team_changed"' in response.text
    assert fired and case["client"].get("/api/v1/auth/session").status_code == 200


def test_handoff_cannot_commit_a_reviewer_disabled_during_actual_view_assembly(
    intake_site, monkeypatch
):
    case = team_case(intake_site, "handoff")
    before = team_fingerprint(case)

    def disable_recipient():
        with Session(case["engine"]) as session, session.begin():
            session.get(User, case["reviewer_id"]).disabled_at = datetime.now(UTC)

    fired = after_team(monkeypatch, case, disable_recipient)
    assert_denied(team_perform(case), 404)
    assert fired and team_fingerprint(case) == before
    assert case["client"].get("/api/v1/auth/session").status_code == 200


@pytest.mark.parametrize("operation", ("handoff", "approval", "comment", "noop-comment"))
@pytest.mark.parametrize("change", ("revoked", "expired"))
def test_committed_team_mutation_denies_its_later_private_response(
    intake_site, monkeypatch, operation, change
):
    case = team_case(intake_site, operation)
    model = CommentView if "comment" in operation else HandoffView
    case["model"] = model
    fired = after_view(monkeypatch, case, "serialized", lambda: change_actor(case, change))
    assert_denied(team_perform(case), 401)
    assert fired
    with Session(case["engine"]) as session:
        if "comment" in operation:
            from app.db.team_review import FindingComment

            assert session.get(FindingComment, UUID(case["body"]["id"])) is not None
        elif operation == "handoff":
            assert (
                session.get(ReviewHandoff, case["document_id"]).reviewer_id == case["reviewer_id"]
            )
        else:
            from app.db.team_review import ReviewApproval

            assert session.scalar(
                select(ReviewApproval.id).where(ReviewApproval.document_id == case["document_id"])
            )


def test_real_detector_limit_after_revocation_cannot_commit_failed_results(
    intake_site, monkeypatch
):
    from app.detection import service

    owner, _, engine, workspace, actor = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    created = owner.post(
        "/api/v1/documents",
        headers=headers,
        json=_draft_body(
            workspace, source="Fictional " + " nora@example.test" * 1001, categories=["email"]
        ),
    )
    assert created.status_code == 201
    version = created.json()["version"]
    case = {
        "engine": engine,
        "actor": actor,
        "workspace": workspace,
        "document_id": UUID(version["document_id"]),
        "operation": "scan",
        "body": {"expected": version},
    }
    before = scan_content_fingerprint(case)
    original, fired = service.detect_suggestions, []

    def actual_limit(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        finally:
            fired.append(True)
            change_actor(case, "revoked")

    monkeypatch.setattr(service, "detect_suggestions", actual_limit)
    response = owner.post(
        "/api/v1/documents/" + str(case["document_id"]) + "/scan",
        headers=headers,
        json={"expected": version},
    )
    assert_denied(response, 401)
    assert fired
    assert_storage(case, before)
