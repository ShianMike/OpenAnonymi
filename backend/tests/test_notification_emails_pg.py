"""Private templates and durable delivery admission, including process wakeup."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event, Lock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.accounts.limits import AttemptLimiter
from app.db.durable import AttemptEvent
from app.db.models import Document, Membership, User
from app.db.notifications import EVENT_CODES, Notification
from app.factory import create_app
from app.notifications.emails import SUBJECT, deliver_next, notification_body
from app.notifications.service import notify
from tests.test_notifications_pg import (
    COMMENT,
    SOURCE,
    TITLE,
    WORKSPACE,
    assign,
    start_review,
    stored,
)


class CapturingMailer:
    def __init__(self, case, *, fail=False):
        self.case, self.fail = case, fail
        self.messages = []
        self.called, self.lock = Event(), Lock()

    def send_notification(self, recipient, code):
        # A separate database connection must see the committed attempt before
        # transport starts. No source, title, name or comment reaches transport.
        with Session(self.case["engine"]) as session:
            assert session.scalar(
                select(Notification.id).where(
                    Notification.recipient_id == self.case["reviewer_id"],
                    Notification.email_status == "failed",
                    Notification.email_attempted_at.is_not(None),
                )
            )
        with self.lock:
            self.messages.append((recipient, SUBJECT, notification_body(code)))
        self.called.set()
        if self.fail:
            raise OSError("PRIVATE_TRANSPORT_DETAIL " + TITLE)


@pytest.fixture
def email_case(intake_site):
    case = start_review(intake_site)
    case["settings"] = case["owner"].app.state.settings
    yield case
    limiter = AttemptLimiter(case["engine"], case["settings"], scope="notification_email")
    with Session(case["engine"]) as session, session.begin():
        session.execute(
            delete(AttemptEvent).where(
                AttemptEvent.scope == "notification_email",
                AttemptEvent.subject_hmac == limiter._digest(str(case["reviewer_id"])),
            )
        )


def enable(case):
    with Session(case["engine"]) as session, session.begin():
        session.get(User, case["reviewer_id"]).notification_emails = "immediate"


def queue(case, count=1, *, now=None):
    now = now or datetime.now(UTC)
    with Session(case["engine"]) as session, session.begin():
        document = session.get(Document, UUID(case["version"]["document_id"]))
        for index in range(count):
            notify(
                session,
                document,
                case["reviewer_id"],
                case["owner_id"],
                EVENT_CODES[index % len(EVENT_CODES)],
                now,
            )


@pytest.mark.parametrize("code", EVENT_CODES)
def test_all_fixed_templates_contain_only_the_allowlisted_message(code):
    body = notification_body(code)
    assert SUBJECT == "OpenAnonymi notification"
    assert "a workspace you belong to" in body
    assert body.endswith("Sign in to OpenAnonymi to see it.")
    assert all(sentinel not in body for sentinel in (TITLE, SOURCE, COMMENT, WORKSPACE))
    assert "http" not in body and "@" not in body and "<" not in body
    with pytest.raises(ValueError):
        notification_body(TITLE)


def test_email_preference_is_closed_csrf_bound_and_off_without_configured_delivery(email_case):
    case = email_case
    reviewer, headers = case["reviewer"], case["rh"]
    path = "/api/v1/auth/preferences"
    assert reviewer.get(path).json() == {
        "notification_emails": "off",
        "notification_emails_available": False,
    }
    body = {"notification_emails": "immediate"}
    assert reviewer.put(path, json=body).status_code == 403
    assert reviewer.put(path, json=body, headers=headers).status_code == 503
    assert (
        reviewer.put(path, json={"notification_emails": "digest"}, headers=headers).status_code
        == 422
    )
    assert (
        reviewer.put(
            path, json={**body, "user_id": str(case["owner_id"])}, headers=headers
        ).status_code
        == 422
    )
    assert (
        reviewer.put(path, json={"notification_emails": "off"}, headers=headers).status_code == 200
    )
    reviewer.app.state.recovery_mailer = CapturingMailer(case)
    assert reviewer.put(path, json=body, headers=headers).status_code == 200
    assert reviewer.get(path).json() == {
        "notification_emails": "immediate",
        "notification_emails_available": True,
    }
    assert case["owner"].get(path).json()["notification_emails"] == "off"


def test_off_history_is_not_emailed_when_preference_is_enabled_later(email_case):
    case = email_case
    assign(case)
    enable(case)
    assign(case, None)
    mailer = CapturingMailer(case)
    assert deliver_next(case["engine"], case["settings"], mailer)
    assert not deliver_next(case["engine"], case["settings"], mailer)
    rows = {row.event_code: row for row in stored(case)}
    assert rows["review_assigned"].email_status == "not_requested"
    assert rows["review_assigned"].email_attempted_at is None
    assert rows["review_unassigned"].email_status == "sent"
    assert len(mailer.messages) == 1


def test_delivery_failure_is_content_free_once_only_and_cannot_undo_assignment(email_case, caplog):
    case = email_case
    enable(case)
    assign(case)
    mailer = CapturingMailer(case, fail=True)
    assert deliver_next(case["engine"], case["settings"], mailer)
    assert not deliver_next(case["engine"], case["settings"], mailer)
    assert stored(case)[0].email_status == "failed"
    assert len(mailer.messages) == 1
    assert case["reviewer"].get(case["base"] + "/source").status_code == 200
    assert case["owner"].get(case["base"] + "/handoff").json()["reviewer_id"] == str(
        case["reviewer_id"]
    )
    assert (
        "review_assigned" in caplog.text
        and TITLE not in caplog.text
        and "PRIVATE_TRANSPORT_DETAIL" not in caplog.text
    )


def test_persistent_hourly_budget_is_shared_across_concurrent_workers_and_restarts(email_case):
    case = email_case
    enable(case)
    now = datetime.now(UTC)
    queue(case, 12, now=now)
    mailer = CapturingMailer(case)

    def drain():
        # Each call creates a new limiter, as a restarted worker would.
        while deliver_next(case["engine"], case["settings"], mailer, now=now):
            pass

    with ThreadPoolExecutor(max_workers=4) as workers:
        futures = [workers.submit(drain) for _ in range(4)]
        for future in futures:
            future.result(timeout=10)
    rows = stored(case)
    assert [row.email_status for row in rows].count("sent") == 10
    assert [row.email_status for row in rows].count("skipped_limit") == 2
    assert all(row.email_attempted_at == now for row in rows)
    assert len(mailer.messages) == 10
    limiter = AttemptLimiter(case["engine"], case["settings"], scope="notification_email")
    with Session(case["engine"]) as session:
        attempts = session.scalars(
            select(AttemptEvent).where(
                AttemptEvent.scope == "notification_email",
                AttemptEvent.subject_hmac == limiter._digest(str(case["reviewer_id"])),
            )
        ).all()
        assert len(attempts) == 10
        assert all(
            len(row.subject_hmac) == 32
            and str(case["reviewer_id"]).encode() not in row.subject_hmac
            for row in attempts
        )
    later = now + timedelta(hours=1, seconds=1)
    queue(case, now=later)
    assert deliver_next(case["engine"], case["settings"], mailer, now=later)
    assert len(mailer.messages) == 11


@pytest.mark.parametrize("ineligible", ["off", "revoked", "disabled"])
def test_delivery_rechecks_recipient_preference_and_membership(email_case, ineligible):
    case = email_case
    enable(case)
    queue(case)
    with Session(case["engine"]) as session, session.begin():
        if ineligible == "off":
            session.get(User, case["reviewer_id"]).notification_emails = "off"
        elif ineligible == "revoked":
            session.get(
                Membership, (case["workspace"], case["reviewer_id"])
            ).revoked_at = datetime.now(UTC)
        else:
            session.get(User, case["reviewer_id"]).disabled_at = datetime.now(UTC)
    mailer = CapturingMailer(case)
    assert deliver_next(case["engine"], case["settings"], mailer)
    row = stored(case)[0]
    assert (
        not row.email_requested
        and row.email_status == "not_requested"
        and row.email_attempted_at is None
    )
    assert mailer.messages == []


def test_startup_drains_committed_intent_and_later_commit_wakes_the_idle_worker(email_case):
    case = email_case
    enable(case)
    queue(case)
    mailer = CapturingMailer(case)
    development = case["settings"].model_copy(update={"environment": "development"})
    with TestClient(create_app(development, engine=case["engine"], recovery_mailer=mailer)):
        assert mailer.called.wait(5), "Startup did not recover pending intent."
        mailer.called.clear()
        # Actual assignment transaction on the other app instance commits through
        # the same engine, exercising the production after_commit wake listener.
        assign(case)
        assert mailer.called.wait(5), "Committed assignment did not wake the idle worker."
    assert len(mailer.messages) == 2
    assert all(row.email_status == "sent" for row in stored(case))
