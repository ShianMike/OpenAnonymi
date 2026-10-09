"""Content-free shared attempt budgets and transactional review history."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AttemptEvent(Base):
    __tablename__ = "attempt_events"
    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_hmac: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        Index("ix_attempt_subject_window", "scope", "subject_hmac", "attempted_at"),
        CheckConstraint("octet_length(subject_hmac) = 32", name="attempt_subject_digest_length"),
    )


class ReviewUndoEntry(Base):
    __tablename__ = "review_undo_entries"
    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    after_version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    payload_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint("document_id", "actor_id", "sequence", name="uq_review_undo_sequence"),
        Index("ix_review_undo_actor_sequence", "document_id", "actor_id", "sequence"),
        CheckConstraint("sequence > 0 AND after_version >= 0", name="valid_review_undo_version"),
        CheckConstraint(
            "payload_bytes > 0 AND payload_bytes <= 524288", name="bounded_review_undo_payload"
        ),
    )
