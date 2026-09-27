"""Persistence model. Content-bearing columns are ciphertext or key references only."""

from datetime import datetime
from uuid import UUID, uuid4

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
    func,
    inspect,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import Session as OrmSession

from app.db.base import Base


def uuid_column(primary_key: bool = False, nullable: bool = False):
    return mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=primary_key,
        default=uuid4 if primary_key else None,
        nullable=nullable,
    )


def timestamp_column():
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = uuid_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = timestamp_column()
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[UUID] = uuid_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = timestamp_column()
    content_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="7")
    activity_retention_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="90"
    )
    settings_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    __table_args__ = (
        CheckConstraint("content_retention_days > 0", name="positive_content_retention"),
        CheckConstraint("activity_retention_days > 0", name="positive_activity_retention"),
        CheckConstraint("settings_version > 0", name="positive_workspace_settings_version"),
    )


class Membership(Base):
    __tablename__ = "memberships"

    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = timestamp_column()
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint("role IN ('member', 'administrator')", name="valid_role"),)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID] = uuid_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    csrf_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = timestamp_column()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_sessions_user_expiry", "user_id", "expires_at"),)


class RecoveryToken(Base):
    __tablename__ = "recovery_tokens"

    id: Mapped[UUID] = uuid_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    created_at: Mapped[datetime] = timestamp_column()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[UUID] = uuid_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    owner_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    title_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    title_key_id: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="draft")
    current_revision_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    decision_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    settings_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    category_settings: Mapped[str] = mapped_column(
        String(300), nullable=False, server_default="email,phone"
    )
    phone_region: Mapped[str] = mapped_column(String(2), nullable=False, server_default="US")
    created_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = timestamp_column()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "owner_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            name="fk_documents_owner_membership",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["id", "current_revision_id"],
            ["source_revisions.document_id", "source_revisions.id"],
            name="fk_documents_current_revision",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            "status IN ('draft', 'scanning', 'needs_review', 'ready', 'exported', "
            "'failed', 'expired', 'deleted')",
            name="valid_status",
        ),
        CheckConstraint("decision_version >= 0", name="nonnegative_decision_version"),
        CheckConstraint("settings_version >= 1", name="positive_settings_version"),
        CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
        CheckConstraint(
            "(title_ciphertext IS NULL AND title_key_id IS NULL) OR "
            "(title_ciphertext IS NOT NULL AND title_key_id IS NOT NULL)",
            name="title_encryption_pair",
        ),
        Index("ix_documents_owner_created", "owner_id", "created_at"),
        Index("ix_documents_expiry", "expires_at"),
    )


class SourceRevision(Base):
    __tablename__ = "source_revisions"

    id: Mapped[UUID] = uuid_column(primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    source_key_id: Mapped[str] = mapped_column(String(80), nullable=False)
    utf8_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    code_points: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = timestamp_column()

    __table_args__ = (
        UniqueConstraint("document_id", "id", name="uq_source_revisions_document_id"),
        UniqueConstraint("document_id", "revision_number", name="uq_source_revisions_number"),
        CheckConstraint("revision_number > 0", name="positive_revision_number"),
        CheckConstraint("utf8_bytes > 0 AND utf8_bytes <= 1048576", name="valid_source_bytes"),
        CheckConstraint("code_points > 0 AND code_points <= 100000", name="valid_source_points"),
    )


class EntityGroup(Base):
    __tablename__ = "entity_groups"

    id: Mapped[UUID] = uuid_column(primary_key=True)
    document_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    source_revision_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    label: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = timestamp_column()

    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "source_revision_id"],
            ["source_revisions.document_id", "source_revisions.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("document_id", "id", name="uq_entity_groups_document_id"),
        UniqueConstraint(
            "document_id", "source_revision_id", "id", name="uq_entity_groups_revision_id"
        ),
        UniqueConstraint("document_id", "label", name="uq_entity_groups_document_label"),
        CheckConstraint(
            "category IN ('person', 'organization', 'address', 'identifier', 'custom', 'email', 'phone')",
            name="valid_category",
        ),
    )


class LabelCounter(Base):
    __tablename__ = "label_counters"

    document_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    category: Mapped[str] = mapped_column(String(24), primary_key=True)
    next_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    __table_args__ = (CheckConstraint("next_number > 0", name="positive_next_label_number"),)


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[UUID] = uuid_column(primary_key=True)
    document_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    source_revision_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    group_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    rule_id: Mapped[str | None] = mapped_column(String(80))
    rule_version: Mapped[str | None] = mapped_column(String(30))
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = timestamp_column()
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "source_revision_id"],
            ["source_revisions.document_id", "source_revisions.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["document_id", "source_revision_id", "group_id"],
            ["entity_groups.document_id", "entity_groups.source_revision_id", "entity_groups.id"],
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint("document_id", "id", name="uq_findings_document_id"),
        CheckConstraint("start_offset >= 0 AND end_offset > start_offset", name="valid_span"),
        CheckConstraint("origin IN ('manual', 'automatic')", name="valid_origin"),
        CheckConstraint(
            "category IN ('person', 'organization', 'address', 'identifier', 'custom', 'email', 'phone')",
            name="valid_category",
        ),
        Index("ix_findings_revision", "source_revision_id", "start_offset"),
    )


class Decision(Base):
    __tablename__ = "decisions"

    finding_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("findings.id", ondelete="CASCADE"),
        primary_key=True,
    )
    action: Mapped[str] = mapped_column(String(12), nullable=False)
    keep_reason: Mapped[str | None] = mapped_column(String(32))
    decided_by: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    decision_version: Mapped[int] = mapped_column(Integer, nullable=False)
    decided_at: Mapped[datetime] = timestamp_column()

    __table_args__ = (
        CheckConstraint("action IN ('label', 'redact', 'keep')", name="valid_action"),
        CheckConstraint(
            "(action = 'keep' AND keep_reason IS NOT NULL) OR "
            "(action <> 'keep' AND keep_reason IS NULL)",
            name="keep_requires_reason",
        ),
        CheckConstraint("decision_version > 0", name="positive_decision_version"),
    )


class ReviewCompletion(Base):
    __tablename__ = "review_completions"

    id: Mapped[UUID] = uuid_column(primary_key=True)
    document_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    source_revision_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    decision_version: Mapped[int] = mapped_column(Integer, nullable=False)
    settings_version: Mapped[int] = mapped_column(Integer, nullable=False)
    confirmed_by: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    confirmed_at: Mapped[datetime] = timestamp_column()

    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "source_revision_id"],
            ["source_revisions.document_id", "source_revisions.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("document_id", "id", name="uq_review_completions_document_id"),
        UniqueConstraint(
            "document_id",
            "source_revision_id",
            "decision_version",
            "settings_version",
            name="uq_review_completion_version",
        ),
        CheckConstraint("decision_version >= 0", name="nonnegative_decision_version"),
        CheckConstraint("settings_version >= 1", name="positive_settings_version"),
    )


class ExportEvent(Base):
    __tablename__ = "export_events"

    id: Mapped[UUID] = uuid_column(primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    completion_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    actor_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    format: Mapped[str] = mapped_column(String(12), nullable=False)
    occurred_at: Mapped[datetime] = timestamp_column()

    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "completion_id"],
            ["review_completions.document_id", "review_completions.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("format IN ('copy', 'txt')", name="valid_format"),
    )


class Preset(Base):
    __tablename__ = "presets"

    id: Mapped[UUID] = uuid_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    categories: Mapped[str] = mapped_column(String(300), nullable=False)
    phone_region: Mapped[str] = mapped_column(String(2), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    is_default: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    created_at: Mapped[datetime] = timestamp_column()

    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_presets_workspace_name"),
        CheckConstraint("version > 0", name="positive_version"),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[UUID] = uuid_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    document_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    event_code: Mapped[str] = mapped_column(String(40), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    occurred_at: Mapped[datetime] = timestamp_column()

    __table_args__ = (Index("ix_audit_events_workspace_time", "workspace_id", "occurred_at"),)


class ImmutableSourceRevision(RuntimeError):
    """Source revisions may only be inserted or re-encrypted by maintenance."""


@event.listens_for(OrmSession, "before_flush")
def prevent_source_revision_edits(session: OrmSession, _flush_context, _instances) -> None:
    for object_ in session.dirty:
        if not isinstance(object_, SourceRevision) or not session.is_modified(object_):
            continue
        if not session.info.get("allow_source_key_rotation"):
            raise ImmutableSourceRevision("Source revisions are immutable.")
        state = inspect(object_)
        for field in (
            "id",
            "document_id",
            "revision_number",
            "utf8_bytes",
            "code_points",
            "created_at",
        ):
            if state.attrs[field].history.has_changes():
                raise ImmutableSourceRevision(
                    "Key rotation cannot change source revision metadata."
                )
