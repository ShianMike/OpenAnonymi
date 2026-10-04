"""Version changes notify once for the exact approval/request being invalidated."""

from datetime import UTC, datetime

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from app.db.models import Document, ReviewCompletion
from app.db.notifications import Notification
from app.db.team_review import ReviewApproval, ReviewHandoff
from app.notifications.service import notify


def invalidate_approval(session, document, actor_id, now, *, previous=None):
    handled = session.info.setdefault("notified_invalidations", set())
    if document.id in handled:
        return
    handoff = session.get(ReviewHandoff, document.id)
    if handoff is None or handoff.reviewer_id is None:
        return
    fields = ("current_revision_id", "decision_version", "settings_version")
    previous = previous or tuple(getattr(document, field) for field in fields)
    revision, decisions, settings = previous
    if revision is None:
        return
    approved = session.scalar(
        select(ReviewApproval.id)
        .where(
            ReviewApproval.document_id == document.id,
            ReviewApproval.generation == handoff.generation,
            ReviewApproval.approved_by == handoff.reviewer_id,
            ReviewApproval.source_revision_id == revision,
            ReviewApproval.decision_version == decisions,
            ReviewApproval.settings_version == settings,
        )
        .limit(1)
    )
    completion = session.scalar(
        select(ReviewCompletion).where(
            ReviewCompletion.document_id == document.id,
            ReviewCompletion.source_revision_id == revision,
            ReviewCompletion.decision_version == decisions,
            ReviewCompletion.settings_version == settings,
        )
    )
    requested = completion is not None and session.scalar(
        select(Notification.id)
        .where(
            Notification.document_id == document.id,
            Notification.recipient_id == handoff.reviewer_id,
            Notification.event_code == "approval_requested",
            Notification.created_at >= completion.confirmed_at,
        )
        .limit(1)
    )
    if approved or requested:
        notify(session, document, handoff.reviewer_id, actor_id, "approval_invalidated", now)
        handled.add(document.id)


@event.listens_for(Session, "before_flush")
def notify_version_invalidation(session, _context, _instances):
    for document in list(session.dirty):
        if not isinstance(document, Document) or document.deleted_at is not None:
            continue
        state = inspect(document)
        fields = ("current_revision_id", "decision_version", "settings_version")
        if not any(state.attrs[field].history.has_changes() for field in fields):
            continue
        previous = tuple(
            state.attrs[field].history.deleted[0]
            if state.attrs[field].history.deleted
            else getattr(document, field)
            for field in fields
        )
        actor = session.info.get("document_actors", {}).get(document.id)
        invalidate_approval(
            session, document, actor, document.updated_at or datetime.now(UTC), previous=previous
        )


@event.listens_for(Session, "after_transaction_end")
def clear_transaction_flags(session, transaction):
    if transaction.parent is None:
        session.info.pop("notified_invalidations", None)
        session.info.pop("document_actors", None)
        session.info.pop("notification_pending", None)
