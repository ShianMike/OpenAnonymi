"""Encrypted rule versions and document-bound immutable rule references."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    String,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models import timestamp_column, uuid_column


class WorkspaceRule(Base):
    __tablename__ = "workspace_rules"

    id: Mapped[UUID] = uuid_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = timestamp_column()
    __table_args__ = (CheckConstraint("version >= 1", name="valid_workspace_rule_version"),)


class RuleVersion(Base):
    __tablename__ = "rule_versions"

    rule_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("workspace_rules.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    payload_key_id: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = timestamp_column()


class DocumentRuleSnapshot(Base):
    __tablename__ = "document_rule_snapshots"

    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    settings_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["rule_id", "rule_version"],
            ["rule_versions.rule_id", "rule_versions.version"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("settings_version >= 1", name="valid_rule_snapshot_settings_version"),
    )
