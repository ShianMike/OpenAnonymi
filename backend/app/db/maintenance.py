"""Global cleanup health contains counts and fixed codes only."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MaintenanceRun(Base):
    __tablename__ = "maintenance_runs"
    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    trigger: Mapped[str] = mapped_column(String(8), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(8), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(24))
    documents_purged: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    expired_rows_removed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    activity_removed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    __table_args__ = (
        CheckConstraint(
            "trigger IN ('startup','periodic','cli','endpoint')", name="maintenance_trigger"
        ),
        CheckConstraint("status IN ('running','ok','failed')", name="maintenance_status"),
        CheckConstraint(
            "failure_code IS NULL OR failure_code IN ('abandoned','cleanup_failed')",
            name="maintenance_failure_code",
        ),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at", name="maintenance_clock"
        ),
        CheckConstraint(
            "documents_purged >= 0 AND expired_rows_removed >= 0 AND activity_removed >= 0",
            name="maintenance_counts",
        ),
        Index("ix_maintenance_started", "started_at", "id"),
    )
