"""Real owner renewal, preservation, conflicts and late authorization on PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.limits import AttemptLimiter
from app.db.durable import ReviewUndoEntry
from app.db.models import (
    AuditEvent,
    Decision,
    Document,
    ExportEvent,
    Finding,
    Membership,
    ReviewCompletion,
    SourceRevision,
    User,
    Workspace,
)
from app.db.models import Session as StoredSession
from app.factory import create_app
from tests.intake_support import _draft_body, _login
from tests.styles_support import decide, draft


def setup(site):
    owner, other, engine, workspace, actor = site
    headers = _login(owner, "intake-owner@example.invalid")
    response = owner.post("/api/v1/documents", json=_draft_body(workspace), headers=headers)
    assert response.status_code == 201
    base = "/api/v1/documents/" + response.json()["version"]["document_id"]
    view = owner.get(base + "/retention")
    assert view.status_code == 200
    return owner, other, engine, workspace, actor, headers, base, view.json()


def renew(owner, headers, base, view, **extra):
    return owner.patch(
        base + "/retention",
        json={"expected_expires_at": view["expires_at"], "days_from_now": 7, **extra},
        headers=headers,
    )


def retained_rows(engine, document_id):
    with Session(engine) as session:
        doc = session.get(Document, document_id)
        result = {
            "document": {
                column.name: getattr(doc, column.name)
                for column in Document.__table__.columns
                if column.name not in ("expires_at", "updated_at")
            }
        }
        for model in (SourceRevision, Finding, ReviewCompletion, ExportEvent, ReviewUndoEntry):
            result[model.__tablename__] = list(
                session.execute(
                    select(model.__table__)
                    .where(model.document_id == document_id)
                    .order_by(model.id)
                ).mappings()
            )
        result["decisions"] = list(
            session.execute(
                select(Decision.__table__)
                .where(
                    Decision.finding_id.in_(
                        select(Finding.id).where(Finding.document_id == document_id)
                    )
                )
                .order_by(Decision.finding_id)
            ).mappings()
        )
        return result


def test_renew_preserves_encrypted_source_decisions_confirmation_undo_and_actual_export(
    intake_site,
):
    owner, _, engine, workspace, actor = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    base, state = draft(
        owner, headers, workspace, "😀 Nora nora@example.test", [("nora@example.test", "email")]
    )
    changed = decide(
        owner, headers, base, state, state["findings"][0], "redact", "partial_mask", "email_domain"
    )
    assert changed.status_code == 200
    version = changed.json()["version"]
    assert (
        owner.post(
            base + "/complete",
            json={"expected": version, "confirmed_preview": True},
            headers=headers,
        ).status_code
        == 200
    )
    body = {"expected": version, "event_id": str(uuid4())}
    first = owner.post(base + "/exports/txt", json=body, headers=headers)
    assert first.status_code == 200
    view = owner.get(base + "/retention").json()
    id_ = UUID(version["document_id"])
    before = retained_rows(engine, id_)
    assert b"nora@example.test" not in before["source_revisions"][0]["source_ciphertext"]
    response = renew(owner, headers, base, view)
    assert response.status_code == 200 and response.json()["maximum_days"] == 7
    result = response.json()
    assert datetime.fromisoformat(result["expires_at"]) - datetime.fromisoformat(
        result["current_time"]
    ) == timedelta(days=7)
    assert result["expires_at"] > view["expires_at"]
    assert retained_rows(engine, id_) == before
    assert owner.get(base + "/source").json()["version"] == version
    second = owner.post(base + "/exports/txt", json=body, headers=headers)
    assert second.status_code == 200 and second.content == first.content
    with Session(engine) as session:
        events = session.scalars(
            select(AuditEvent).where(
                AuditEvent.document_id == id_, AuditEvent.event_code == "document_retention_renewed"
            )
        ).all()
        assert len(events) == 1 and events[0].actor_id == actor
        assert events[0].decision_changes == [] and events[0].decision_version is None


@pytest.mark.parametrize(
    "administrator,granted", [(False, False), (True, False), (False, True), (True, True)]
)
def test_only_owner_can_read_and_renew_even_when_admin_or_assigned_reviewer(
    intake_site, administrator, granted
):
    owner, other, engine, workspace, _actor, headers, base, view = setup(intake_site)
    other_headers = _login(other, "intake-other@example.invalid")
    other_id = UUID(other.get("/api/v1/auth/session").json()["user_id"])
    if administrator:
        with Session(engine) as session, session.begin():
            session.get(Membership, (workspace, other_id)).role = "administrator"
    if granted:
        version = owner.get(base + "/source").json()["version"]
        response = owner.put(
            base + "/handoff",
            json={"expected": version, "reviewer_id": str(other_id), "require_approval": False},
            headers=headers,
        )
        assert response.status_code == 200
        assert other.get(base + "/source").status_code == 200
    assert other.get(base + "/retention").status_code == 404
    assert renew(other, other_headers, base, view).status_code == 404
    assert other.get(f"/api/v1/documents/{uuid4()}/retention").status_code == 404
    assert owner.get(base + "/retention").json()["expires_at"] == view["expires_at"]


def test_compare_and_swap_conflict_policy_change_and_no_shortening(intake_site):
    owner, _, engine, workspace, _actor, headers, base, view = setup(intake_site)
    assert (
        renew(owner, headers, base, view, days_from_now=1).json()["code"]
        == "retention_not_extended"
    )
    with Session(engine) as session, session.begin():
        session.get(Workspace, workspace).content_retention_days = 4
    blocked = renew(owner, headers, base, view)
    assert blocked.status_code == 422 and blocked.json()["code"] == "retention_policy"
    result = renew(owner, headers, base, view, days_from_now=4)
    assert result.status_code == 200 and result.json()["maximum_days"] == 4
    stale = renew(owner, headers, base, view, days_from_now=4)
    assert stale.status_code == 409 and stale.json()["code"] == "retention_changed"
    assert datetime.fromisoformat(
        owner.get(base + "/retention").json()["expires_at"]
    ) == datetime.fromisoformat(result.json()["expires_at"])


def test_concurrent_renewals_commit_once(intake_site):
    owner, _, engine, _workspace, _actor, headers, base, view = setup(intake_site)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: renew(owner, headers, base, view), range(2)))
    assert sorted(response.status_code for response in responses) == [200, 409]
    with Session(engine) as session:
        assert (
            len(
                session.scalars(
                    select(AuditEvent).where(
                        AuditEvent.document_id == UUID(base.rsplit("/", 1)[1]),
                        AuditEvent.event_code == "document_retention_renewed",
                    )
                ).all()
            )
            == 1
        )


@pytest.mark.parametrize("state", ["expired", "deleted"])
def test_expired_or_deleted_content_cannot_be_restored(intake_site, state):
    owner, _, engine, _workspace, _actor, headers, base, view = setup(intake_site)
    if state == "deleted":
        assert owner.delete(base, headers=headers).status_code == 200
    else:
        with Session(engine) as session, session.begin():
            document = session.get(Document, UUID(base.rsplit("/", 1)[1]))
            document.created_at = datetime.now(UTC) - timedelta(days=1)
            document.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert owner.get(base + "/retention").status_code == 410
    assert renew(owner, headers, base, view).status_code == 410


@pytest.mark.parametrize(
    "extra",
    [
        {"days_from_now": 0},
        {"days_from_now": 31},
        {"days_from_now": True},
        {"days_from_now": 1.5},
        {"expected_expires_at": "2026-10-03T12:00:00"},
        {"title": "PRIVATE INPUT CANARY"},
    ],
)
def test_strict_request_validation_and_no_private_echo(intake_site, extra):
    owner, _, _, _, _, headers, base, view = setup(intake_site)
    response = renew(owner, headers, base, view, **extra)
    assert response.status_code == 422 and "PRIVATE INPUT CANARY" not in response.text


def test_exact_origin_and_csrf_are_required(intake_site):
    owner, _, _, _, _, headers, base, view = setup(intake_site)
    for bad_headers in (
        {},
        {"Origin": headers["Origin"]},
        {**headers, "Origin": "https://attacker.invalid"},
        {**headers, "X-CSRF-Token": "wrong"},
    ):
        assert renew(owner, bad_headers, base, view).status_code == 403


@pytest.mark.parametrize("change", ["membership", "session", "disabled"])
@pytest.mark.parametrize("operation", ["read", "renew"])
def test_late_access_revocation_refuses_response_and_rolls_back(
    intake_site, monkeypatch, change, operation
):
    from app.workspace import retention_api

    owner, _, engine, workspace, actor, headers, base, view = setup(intake_site)

    def revoke():
        with Session(engine) as session, session.begin():
            if change == "membership":
                session.get(Membership, (workspace, actor)).revoked_at = datetime.now(UTC)
            elif change == "disabled":
                session.get(User, actor).disabled_at = datetime.now(UTC)
            else:
                for row in session.scalars(
                    select(StoredSession).where(StoredSession.user_id == actor)
                ):
                    row.revoked_at = datetime.now(UTC)

    if operation == "read":
        original = retention_api.retention_view

        def read_then_revoke(*args, **kwargs):
            value = original(*args, **kwargs)
            revoke()
            return value

        monkeypatch.setattr(retention_api, "retention_view", read_then_revoke)
        response = owner.get(base + "/retention")
    else:
        original = retention_api.renew_retention

        def revoke_before_commit(*args, **kwargs):
            authorize = kwargs["authorize"]

            def fresh():
                revoke()
                authorize()

            return original(*args, **{**kwargs, "authorize": fresh})

        monkeypatch.setattr(retention_api, "renew_retention", revoke_before_commit)
        response = renew(owner, headers, base, view)
    assert response.status_code == 401
    with Session(engine) as session:
        document = session.get(Document, UUID(base.rsplit("/", 1)[1]))
        assert document.expires_at == datetime.fromisoformat(view["expires_at"])
        assert not session.scalars(
            select(AuditEvent).where(
                AuditEvent.document_id == document.id,
                AuditEvent.event_code == "document_retention_renewed",
            )
        ).all()


def test_expiry_while_waiting_for_authorization_is_not_revived(intake_site, monkeypatch):
    from app.workspace import retention, retention_api

    owner, _, engine, _, _, headers, base, view = setup(intake_site)
    clock = [datetime.now(UTC)]

    class Clock:
        @staticmethod
        def now(zone):
            return clock[0]

    monkeypatch.setattr(retention, "datetime", Clock)
    original = retention_api.renew_retention

    def expire_before_commit(*args, **kwargs):
        authorize = kwargs["authorize"]

        def fresh():
            authorize()
            clock[0] = datetime.fromisoformat(view["expires_at"]) + timedelta(seconds=1)

        return original(*args, **{**kwargs, "authorize": fresh})

    monkeypatch.setattr(retention_api, "renew_retention", expire_before_commit)
    assert renew(owner, headers, base, view).status_code == 410
    with Session(engine) as session:
        assert session.get(
            Document, UUID(base.rsplit("/", 1)[1])
        ).expires_at == datetime.fromisoformat(view["expires_at"])


def test_persistent_rate_limit_survives_independent_application(intake_site):
    owner, _, engine, _, actor, headers, base, view = setup(intake_site)
    limiter = AttemptLimiter(
        engine,
        owner.app.state.settings,
        scope="retention_renewal",
        maximum=30,
        window_seconds=60,
        network_scope=False,
    )
    assert all(limiter.take(str(actor)) for _ in range(30))
    with TestClient(create_app(owner.app.state.settings, engine=engine)) as restarted:
        restarted.cookies.update(owner.cookies)
        assert renew(restarted, headers, base, view).status_code == 429
