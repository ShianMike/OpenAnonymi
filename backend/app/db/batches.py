"""Owned encrypted batch snapshots and content-free durable scan leases."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db.base import Base
from app.db.models import timestamp_column, uuid_column


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[UUID] = uuid_column(primary_key=True)
    workspace_id: Mapped[UUID] = uuid_column()
    owner_id: Mapped[UUID] = uuid_column()
    name_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    name_key_id: Mapped[str | None] = mapped_column(String(80))
    column_rules_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    column_rules_key_id: Mapped[str | None] = mapped_column(String(80))
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False)
    uploaded_bytes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = timestamp_column()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "owner_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            ondelete="RESTRICT",
            name="fk_batches_owner_membership",
        ),
        UniqueConstraint("id", "workspace_id", "owner_id", name="uq_batches_owner_workspace"),
        CheckConstraint("uploaded_bytes BETWEEN 0 AND 41943040", name="bounded_batch_bytes"),
        CheckConstraint(
            "jsonb_typeof(settings)='object' AND octet_length(settings::text)<=131072",
            name="bounded_batch_settings",
        ),
        CheckConstraint(
            "(name_ciphertext IS NULL AND name_key_id IS NULL) OR (name_ciphertext IS NOT NULL AND name_key_id IS NOT NULL)",
            name="batch_name_encryption_pair",
        ),
        CheckConstraint(
            "(column_rules_ciphertext IS NULL AND column_rules_key_id IS NULL) OR (column_rules_ciphertext IS NOT NULL AND column_rules_key_id IS NOT NULL)",
            name="batch_columns_encryption_pair",
        ),
        CheckConstraint(
            "deleted_at IS NULL OR deleted_at>=created_at", name="batch_delete_after_creation"
        ),
        Index("ix_batches_owner_created", "owner_id", "created_at"),
    )


class ScanJob(Base):
    __tablename__ = "scan_jobs"

    id: Mapped[UUID] = uuid_column(primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    batch_id: Mapped[UUID | None] = mapped_column(ForeignKey("batches.id", ondelete="CASCADE"))
    source_revision_id: Mapped[UUID] = uuid_column()
    settings_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    available_at: Mapped[datetime] = timestamp_column()
    lease_owner: Mapped[UUID | None] = uuid_column(nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = timestamp_column()

    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "source_revision_id"],
            ["source_revisions.document_id", "source_revisions.id"],
            ondelete="CASCADE",
            name="fk_scan_jobs_revision",
        ),
        ForeignKeyConstraint(
            ["document_id", "batch_id"],
            ["documents.id", "documents.batch_id"],
            ondelete="CASCADE",
            name="fk_scan_jobs_document_batch",
        ),
        UniqueConstraint(
            "document_id", "source_revision_id", "settings_version", name="uq_scan_jobs_input"
        ),
        CheckConstraint(
            "settings_version>=1 AND attempts>=0", name="valid_scan_job_version_attempts"
        ),
        CheckConstraint(
            "status IN ('queued','leased','done','failed','skipped')", name="valid_scan_job_status"
        ),
        CheckConstraint(
            "(status='leased' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL) OR (status<>'leased' AND lease_owner IS NULL AND lease_expires_at IS NULL)",
            name="scan_job_lease_pair",
        ),
        Index("ix_scan_jobs_claim", "status", "available_at", "created_at"),
    )


@event.listens_for(Session, "before_flush")
def immutable_batch_snapshot(session, _context, _instances):
    for row in session.dirty:
        if not isinstance(row, Batch) or not session.is_modified(row):
            continue
        if any(
            inspect(row).attrs[name].history.has_changes()
            for name in ("id", "settings", "workspace_id", "owner_id", "created_at")
        ):
            raise ValueError("Batch snapshot is immutable.")
        changed = any(
            inspect(row).attrs[name].history.has_changes()
            for name in (
                "name_ciphertext",
                "name_key_id",
                "column_rules_ciphertext",
                "column_rules_key_id",
            )
        )
        deleting = (
            row.deleted_at is not None
            and row.name_ciphertext is None
            and row.name_key_id is None
            and row.column_rules_ciphertext is None
            and row.column_rules_key_id is None
        )
        if changed and not deleting and not session.info.get("allow_source_key_rotation"):
            raise ValueError("Batch protected snapshot is immutable.")
