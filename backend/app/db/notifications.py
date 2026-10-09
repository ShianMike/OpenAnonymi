"""Notification intent and delivery metadata contain no user-entered text."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models import timestamp_column, uuid_column

EVENT_CODES = (
    "review_assigned",
    "review_unassigned",
    "approval_requested",
    "review_approved",
    "approval_invalidated",
    "comment_added",
)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[UUID] = uuid_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    recipient_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    event_code: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = timestamp_column()
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="not_requested"
    )
    email_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_requested: Mapped[bool] = mapped_column(nullable=False, server_default="false")

    __table_args__ = (
        CheckConstraint(
            "event_code IN ('review_assigned','review_unassigned','approval_requested','review_approved','approval_invalidated','comment_added')",
            name="valid_notification_event",
        ),
        CheckConstraint(
            "email_status IN ('not_requested','sent','failed','skipped_limit')",
            name="valid_notification_delivery",
        ),
        CheckConstraint(
            "email_status='not_requested' OR email_attempted_at IS NOT NULL",
            name="notification_delivery_attempt",
        ),
        CheckConstraint(
            "read_at IS NULL OR read_at >= created_at", name="notification_read_after_created"
        ),
        Index("ix_notifications_recipient_order", "recipient_id", "created_at", "id"),
        Index("ix_notifications_document", "document_id"),
        Index("ix_notifications_delivery", "email_requested", "email_attempted_at", "created_at"),
    )
