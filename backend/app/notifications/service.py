"""All stored events are content-free; title decryption requires current access."""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select, tuple_, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import ContentUnavailable, DocumentNotFound, review_document
from app.db.crypto import KeyRing, ProtectedValue
from app.db.models import Document, Membership, User
from app.db.notifications import EVENT_CODES, Notification
from app.notifications.contracts import NotificationPage, NotificationPreferences, NotificationView


class NotificationNotFound(LookupError):
    pass


class NotificationPreferenceUnavailable(ValueError):
    pass


def notify(
    session: Session,
    document: Document,
    recipient_id: UUID | None,
    actor_id: UUID | None,
    event_code: str,
    now: datetime,
    *,
    require_active=True,
):
    if event_code not in EVENT_CODES:
        raise ValueError("Unsupported notification event.")
    if recipient_id is None:
        return
    membership = session.get(Membership, (document.workspace_id, recipient_id))
    recipient = session.get(User, recipient_id)
    if (
        membership is None
        or recipient is None
        or (
            require_active
            and (membership.revoked_at is not None or recipient.disabled_at is not None)
        )
    ):
        return
    session.add(
        Notification(
            id=uuid4(),
            workspace_id=document.workspace_id,
            recipient_id=recipient_id,
            document_id=document.id,
            actor_id=actor_id,
            event_code=event_code,
            created_at=now,
            email_requested=recipient.notification_emails == "immediate",
        )
    )
    session.info["notification_pending"] = True


def visible_query(actor_id: UUID, now: datetime):
    return (
        select(Notification)
        .join(
            Membership,
            (Membership.workspace_id == Notification.workspace_id)
            & (Membership.user_id == Notification.recipient_id),
        )
        .join(User, User.id == Notification.recipient_id)
        .where(
            Notification.recipient_id == actor_id,
            Membership.revoked_at.is_(None),
            User.disabled_at.is_(None),
            Notification.created_at > now - timedelta(days=30),
        )
    )


def _owned_notification(session, notification_id, actor_id, now):
    row = session.scalar(visible_query(actor_id, now).where(Notification.id == notification_id))
    if row is None:
        raise NotificationNotFound("Notification not found.")
    return row


def list_notifications(
    engine: Engine,
    actor_id: UUID,
    keys: KeyRing,
    now: datetime,
    cursor: UUID | None = None,
    limit: int = 50,
):
    if not 1 <= limit <= 50:
        raise ValueError("Choose a notification page size from 1 to 50.")
    with Session(engine) as session, session.begin():
        query = visible_query(actor_id, now)
        if cursor:
            last = _owned_notification(session, cursor, actor_id, now)
            query = query.where(
                tuple_(Notification.created_at, Notification.id) < tuple_(last.created_at, last.id)
            )
        rows = session.scalars(
            query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit + 1)
        ).all()
        content, result = {None: (False, None)}, []
        # Match the document lock order used by membership revocation and batch
        # deletion, even when the notification page is ordered by creation time.
        for document_id in sorted({row.document_id for row in rows[:limit] if row.document_id}):
            available, title = False, None
            try:
                document = review_document(session, document_id, actor_id, now, lock=True)
            except (DocumentNotFound, ContentUnavailable):
                pass
            else:
                available = True
                if document.title_ciphertext is not None:
                    title = keys.decrypt_text(
                        ProtectedValue(document.title_ciphertext, document.title_key_id)
                    )
            content[document_id] = (available, title)
        for row in rows[:limit]:
            available, title = content[row.document_id]
            result.append(
                NotificationView(
                    id=row.id,
                    workspace_id=row.workspace_id,
                    document_id=row.document_id,
                    actor_id=row.actor_id,
                    event_code=row.event_code,
                    created_at=row.created_at,
                    read_at=row.read_at,
                    document_available=available,
                    title=title,
                )
            )
        return NotificationPage(
            items=result, next_cursor=rows[limit - 1].id if len(rows) > limit else None
        )


def unread_count(engine: Engine, actor_id: UUID, now: datetime):
    with Session(engine) as session:
        return (
            session.scalar(
                select(func.count()).select_from(
                    visible_query(actor_id, now).where(Notification.read_at.is_(None)).subquery()
                )
            )
            or 0
        )


def mark_read(engine: Engine, notification_id: UUID, actor_id: UUID, now: datetime):
    with Session(engine) as session, session.begin():
        row = _owned_notification(session, notification_id, actor_id, now)
        session.execute(
            update(Notification)
            .where(Notification.id == row.id, Notification.read_at.is_(None))
            .values(read_at=max(now, row.created_at))
        )


def mark_all_read(engine: Engine, actor_id: UUID, now: datetime):
    with Session(engine) as session, session.begin():
        ids = (
            visible_query(actor_id, now)
            .with_only_columns(Notification.id)
            .where(Notification.read_at.is_(None))
        )
        result = session.execute(
            update(Notification)
            .where(Notification.id.in_(ids))
            .values(read_at=func.greatest(now, Notification.created_at))
        )
        return result.rowcount


def preferences(engine: Engine, actor_id: UUID, available: bool):
    with Session(engine) as session:
        user = session.get(User, actor_id)
        if user is None or user.disabled_at is not None:
            raise NotificationNotFound("Account not found.")
        return NotificationPreferences(
            notification_emails=user.notification_emails, notification_emails_available=available
        )


def update_preferences(engine: Engine, actor_id: UUID, requested: str, available: bool):
    if requested not in {"off", "immediate"}:
        raise ValueError("Choose a supported notification preference.")
    if requested == "immediate" and not available:
        raise NotificationPreferenceUnavailable("Notification email is not configured.")
    with Session(engine) as session, session.begin():
        user = session.scalar(
            select(User)
            .where(User.id == actor_id, User.disabled_at.is_(None))
            .with_for_update(key_share=True)
        )
        if user is None:
            raise NotificationNotFound("Account not found.")
        user.notification_emails = requested
    return NotificationPreferences(
        notification_emails=requested, notification_emails_available=available
    )
