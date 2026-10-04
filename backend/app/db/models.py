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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
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
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    second_factor_reenroll_required: Mapped[bool] = mapped_column(
        nullable=False, server_default="false"
    )
    notification_emails: Mapped[str] = mapped_column(String(9), nullable=False, server_default="off")

    __table_args__ = (
        CheckConstraint("notification_emails IN ('off', 'immediate')", name="valid_notification_emails"),
    )


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
    require_second_factor: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    approval_policy: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default="owner_choice"
    )

    __table_args__ = (
        CheckConstraint("content_retention_days > 0", name="positive_content_retention"),
        CheckConstraint("activity_retention_days > 0", name="positive_activity_retention"),
        CheckConstraint("settings_version > 0", name="positive_workspace_settings_version"),
        CheckConstraint("approval_policy IN ('owner_choice', 'always')", name="valid_approval_policy"),
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
    last_seen_at: Mapped[datetime] = timestamp_column()
    device_label: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default="Unknown browser · Unknown system"
    )
    auth_method: Mapped[str] = mapped_column(String(24), nullable=False, server_default="password")

    __table_args__ = (
        Index("ix_sessions_user_expiry", "user_id", "expires_at"),
        CheckConstraint(
            "auth_method IN ('password', 'password_totp', 'password_backup_code', 'enrollment')",
            name="session_auth_method",
        ),
    )


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
    language: Mapped[str] = mapped_column(String(2), nullable=False, server_default="en")
    preset_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    preset_version: Mapped[int | None] = mapped_column(Integer)
    preferred_action: Mapped[str] = mapped_column(String(8), nullable=False, server_default="label")
    category_defaults: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    csv_delimiter: Mapped[str | None] = mapped_column(String(1))
    csv_has_header: Mapped[bool | None] = mapped_column()
    batch_id: Mapped[UUID | None] = uuid_column(nullable=True)
    batch_position: Mapped[int | None] = mapped_column(Integer)
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
        CheckConstraint(
            "(preset_id IS NULL AND preset_version IS NULL) OR "
            "(preset_id IS NOT NULL AND preset_version >= 1)",
            name="valid_document_preset_snapshot",
        ),
        CheckConstraint("preferred_action IN ('label', 'redact')", name="valid_preferred_action"),
        CheckConstraint(
            "jsonb_typeof(category_defaults)='object' AND octet_length(category_defaults::text)<=8192",
            name="bounded_category_defaults",
        ),
        CheckConstraint("expires_at > created_at", name="expiry_after_creation"),
        CheckConstraint(
            "(csv_delimiter IS NULL AND csv_has_header IS NULL) OR "
            "(csv_delimiter IS NOT NULL AND csv_has_header IS NOT NULL "
            "AND csv_delimiter IN (',',';',E'\\t','|'))",
            name="csv_settings_pair",
        ),
        CheckConstraint(
            "(title_ciphertext IS NULL AND title_key_id IS NULL) OR "
            "(title_ciphertext IS NOT NULL AND title_key_id IS NOT NULL)",
            name="title_encryption_pair",
        ),
        Index("ix_documents_owner_created", "owner_id", "created_at"),
        Index("ix_documents_expiry", "expires_at"),
        ForeignKeyConstraint(
            ["batch_id", "workspace_id", "owner_id"],
            ["batches.id", "batches.workspace_id", "batches.owner_id"],
            ondelete="RESTRICT",
            name="fk_documents_batch_owner",
        ),
        UniqueConstraint("batch_id", "batch_position", name="uq_documents_batch_position"),
        UniqueConstraint("id", "batch_id", name="uq_documents_id_batch"),
        CheckConstraint(
            "(batch_id IS NULL AND batch_position IS NULL) OR (batch_id IS NOT NULL AND batch_position IS NOT NULL AND batch_position BETWEEN 1 AND 20)",
            name="document_batch_pair",
        ),
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
            "category IN ('person', 'organization', 'address', 'identifier', 'custom', 'email', 'phone', 'location', 'date', 'url', 'secret', 'national_id')",
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


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id: Mapped[UUID] = uuid_column(primary_key=True)
    document_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    source_revision_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    settings_version: Mapped[int] = mapped_column(Integer, nullable=False)
    detector_version: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    match_count: Mapped[int | None] = mapped_column(Integer)
    dropped_suggestions: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    failure_code: Mapped[str | None] = mapped_column(String(40))
    started_at: Mapped[datetime] = timestamp_column()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "source_revision_id"],
            ["source_revisions.document_id", "source_revisions.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "document_id", "source_revision_id", "settings_version", name="uq_scan_runs_input"
        ),
        UniqueConstraint(
            "document_id", "source_revision_id", "id", name="uq_scan_runs_revision_id"
        ),
        CheckConstraint("settings_version > 0", name="positive_scan_settings_version"),
        CheckConstraint("attempt_count > 0", name="positive_scan_attempt_count"),
        CheckConstraint("dropped_suggestions >= 0", name="nonnegative_dropped_suggestions"),
        CheckConstraint(
            "match_count IS NULL OR match_count >= 0", name="nonnegative_scan_match_count"
        ),
        CheckConstraint(
            "status IN ('scanning', 'completed', 'failed', 'superseded')",
            name="valid_scan_status",
        ),
    )


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
    date_format: Mapped[str | None] = mapped_column(String(80))
    reason: Mapped[str | None] = mapped_column(String(200))
    scan_run_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
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
        ForeignKeyConstraint(
            ["document_id", "source_revision_id", "scan_run_id"],
            ["scan_runs.document_id", "scan_runs.source_revision_id", "scan_runs.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("document_id", "id", name="uq_findings_document_id"),
        CheckConstraint("start_offset >= 0 AND end_offset > start_offset", name="valid_span"),
        CheckConstraint("origin IN ('manual', 'automatic')", name="valid_origin"),
        CheckConstraint(
            "(origin = 'manual' AND scan_run_id IS NULL) OR "
            "(origin = 'automatic' AND scan_run_id IS NOT NULL AND rule_id IS NOT NULL "
            "AND rule_version IS NOT NULL AND reason IS NOT NULL)",
            name="automatic_finding_metadata",
        ),
        CheckConstraint(
            "category IN ('person', 'organization', 'address', 'identifier', 'custom', 'email', 'phone', 'location', 'date', 'url', 'secret', 'national_id')",
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
    style: Mapped[str] = mapped_column(String(16), nullable=False, server_default="token")
    style_option: Mapped[str | None] = mapped_column(String(24))
    keep_reason: Mapped[str | None] = mapped_column(String(32))
    decided_by: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    decision_version: Mapped[int] = mapped_column(Integer, nullable=False)
    decided_at: Mapped[datetime] = timestamp_column()

    __table_args__ = (
        CheckConstraint("action IN ('label', 'redact', 'keep')", name="valid_action"),
        CheckConstraint(
            "(action='label' AND style IN ('token','stand_in','date_shift')) OR (action='redact' AND style IN ('token','partial_mask','generalize')) OR (action='keep' AND style='token')",
            name="valid_action_style",
        ),
        CheckConstraint(
            "(style IN ('token','stand_in','date_shift') AND style_option IS NULL) OR (style='partial_mask' AND style_option IS NOT NULL AND style_option IN ('full','last4','first_letters','email_domain','email_first','url_host','secret_prefix')) OR (style='generalize' AND style_option IS NOT NULL AND style_option IN ('month_year','year','age_band'))",
            name="valid_style_option",
        ),
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
        CheckConstraint("format IN ('copy','txt','docx','csv')", name="valid_format"),
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
    preferred_action: Mapped[str] = mapped_column(String(8), nullable=False, server_default="label")
    category_defaults: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    column_rules_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    column_rules_key_id: Mapped[str | None] = mapped_column(String(80))
    is_default: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    created_at: Mapped[datetime] = timestamp_column()

    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_presets_workspace_name"),
        Index(
            "uq_presets_workspace_default",
            "workspace_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint(
            "(column_rules_ciphertext IS NULL AND column_rules_key_id IS NULL) OR "
            "(column_rules_ciphertext IS NOT NULL AND column_rules_key_id IS NOT NULL)",
            name="column_rules_encryption_pair",
        ),
        CheckConstraint(
            "jsonb_typeof(category_defaults)='object' AND octet_length(category_defaults::text)<=8192",
            name="bounded_category_defaults",
        ),
        CheckConstraint("preferred_action IN ('label', 'redact')", name="valid_preferred_action"),
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
