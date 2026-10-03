"""Encrypted authenticator secrets and content-free challenge/backup digests."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models import timestamp_column, uuid_column


class UserSecondFactor(Base):
    __tablename__ = "user_second_factors"

    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(8), nullable=False)
    secret_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_id: Mapped[str] = mapped_column(String(80), nullable=False)
    last_used_step: Mapped[int | None] = mapped_column(Integer)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_limit_notice_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = timestamp_column()

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'active')", name="second_factor_status"),
        CheckConstraint("failed_attempts BETWEEN 0 AND 100", name="second_factor_failures"),
        CheckConstraint("last_used_step IS NULL OR last_used_step >= 0", name="second_factor_step"),
    )


class UserBackupCode(Base):
    __tablename__ = "user_backup_codes"

    id: Mapped[UUID] = uuid_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    code_digest: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = timestamp_column()

    __table_args__ = (
        CheckConstraint("octet_length(code_digest) = 32", name="backup_code_digest_length"),
        Index("ix_backup_codes_user", "user_id"),
    )


class AuthChallenge(Base):
    __tablename__ = "auth_challenges"

    id: Mapped[UUID] = uuid_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_digest: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = timestamp_column()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("kind IN ('second_factor', 'enrollment')", name="auth_challenge_kind"),
        CheckConstraint("failed_attempts BETWEEN 0 AND 5", name="auth_challenge_failures"),
        CheckConstraint("octet_length(token_digest) = 32", name="auth_challenge_digest_length"),
        CheckConstraint("expires_at > created_at", name="auth_challenge_expiry"),
        Index("ix_auth_challenges_user_expiry", "user_id", "expires_at"),
    )
