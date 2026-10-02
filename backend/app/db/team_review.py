"""Explicit grants, version-bound approvals and protected finding discussion."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models import timestamp_column, uuid_column


class ReviewHandoff(Base):
    __tablename__ = "review_handoffs"
    document_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    reviewer_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    require_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    updated_at: Mapped[datetime] = timestamp_column()
    __table_args__ = (CheckConstraint("generation > 0", name="positive_handoff_generation"),)


class ReviewApproval(Base):
    __tablename__ = "review_approvals"
    id: Mapped[UUID] = uuid_column(primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    source_revision_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("source_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    decision_version: Mapped[int] = mapped_column(Integer, nullable=False)
    settings_version: Mapped[int] = mapped_column(Integer, nullable=False)
    approved_by: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    approved_at: Mapped[datetime] = timestamp_column()
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "generation",
            "source_revision_id",
            "decision_version",
            "settings_version",
            name="uq_review_approval_version",
        ),
        CheckConstraint(
            "generation > 0 AND decision_version >= 0 AND settings_version > 0",
            name="valid_approval_version",
        ),
    )


class FindingComment(Base):
    __tablename__ = "finding_comments"
    id: Mapped[UUID] = uuid_column(primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    finding_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("findings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    text_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    text_key_id: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = timestamp_column()
