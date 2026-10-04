"""Fixed content-free templates and durable, once-only post-commit admission."""

import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.accounts.limits import AttemptLimiter
from app.db.models import Membership, User
from app.db.notifications import Notification

LOGGER = logging.getLogger("app.notifications")
SUBJECT = "OpenAnonymi notification"
SENTENCES = {
    "review_assigned": "A review was assigned to you in a workspace you belong to.",
    "review_unassigned": "Your assignment to a review was removed in a workspace you belong to.",
    "approval_requested": "Your approval was requested for a review in a workspace you belong to.",
    "review_approved": "A reviewer approved your review in a workspace you belong to.",
    "approval_invalidated": "A review changed and needs a fresh approval in a workspace you belong to.",
    "comment_added": "A comment was added to a review in a workspace you belong to.",
}


def notification_body(code: str) -> str:
    if code not in SENTENCES:
        raise ValueError("Unsupported notification template.")
    return SENTENCES[code] + " Sign in to OpenAnonymi to see it."


def deliver_next(engine, settings, mailer, *, now=None, limiter=None) -> bool:
    if mailer is None:
        return False
    now = now or datetime.now(UTC)
    limiter = limiter or AttemptLimiter(
        engine,
        settings,
        scope="notification_email",
        maximum=10,
        window_seconds=3600,
        network_scope=False,
    )
    with Session(engine) as session, session.begin():
        row = session.scalar(
            select(Notification)
            .where(
                Notification.email_requested.is_(True),
                Notification.email_attempted_at.is_(None),
                Notification.created_at > now - timedelta(days=30),
            )
            .order_by(Notification.created_at, Notification.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if row is None:
            return False
        user = session.get(User, row.recipient_id)
        membership = session.get(Membership, (row.workspace_id, row.recipient_id))
        if (
            user is None
            or user.disabled_at is not None
            or user.notification_emails != "immediate"
            or membership is None
            or membership.revoked_at is not None
        ):
            row.email_requested = False
            return True
        row.email_attempted_at = now
        if not limiter.take(str(user.id), now=now, session=session):
            row.email_status = "skipped_limit"
            return True
        # Commit the attempt before SMTP. A crash cannot resend this email or
        # consume an uncommitted budget; its outcome stays failed if uncertain.
        row.email_status = "failed"
        envelope = (row.id, user.email, row.event_code)
    notification_id, recipient, code = envelope
    status = "sent"
    try:
        mailer.send_notification(recipient, code)
    except Exception:  # noqa: BLE001 -- SMTP diagnostics may contain account data
        status = "failed"
        LOGGER.warning("Notification delivery failed (%s).", code)
    with Session(engine) as session, session.begin():
        session.execute(
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.email_attempted_at == now,
            )
            .values(email_status=status)
        )
    return True


class NotificationWorker:
    def __init__(self, engine, settings, mailer):
        self.engine, self.settings, self.mailer = engine, settings, mailer
        self.limiter = AttemptLimiter(
            engine,
            settings,
            scope="notification_email",
            maximum=10,
            window_seconds=3600,
            network_scope=False,
        )
        self._event = asyncio.Event()
        self._loop = None

    def wake(self):
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._event.set)

    async def run(self):
        self._loop = asyncio.get_running_loop()
        while True:
            self._event.clear()
            try:
                if await asyncio.to_thread(
                    deliver_next, self.engine, self.settings, self.mailer, limiter=self.limiter
                ):
                    continue
                delay = 60
            except Exception:  # noqa: BLE001 -- do not emit database or delivery parameters
                LOGGER.warning(
                    "Notification queue is temporarily unavailable; delivery will retry."
                )
                delay = 5
            with suppress(TimeoutError):
                await asyncio.wait_for(self._event.wait(), timeout=delay)
