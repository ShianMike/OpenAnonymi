"""Single-use email proof. Names are encrypted and codes are digests only."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models import timestamp_column, uuid_column


class PendingRegistration(Base):
    __tablename__ = "pending_registrations"
    id: Mapped[UUID] = uuid_column(primary_key=True)
    canonical_email: Mapped[str] = mapped_column(String(320), nullable=False)
    code_digest: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    workspace_name_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_id: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = timestamp_column()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        Index("ix_pending_registration_address_expiry", "canonical_email", "expires_at"),
        CheckConstraint("octet_length(code_digest) = 32", name="registration_digest_length"),
        CheckConstraint("expires_at > created_at", name="registration_expiry"),
    )


class EmailVerification(Base):
    __tablename__ = "email_verifications"
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    code_digest: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = timestamp_column()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        CheckConstraint("octet_length(code_digest) = 32", name="email_proof_digest_length"),
        CheckConstraint("failed_attempts BETWEEN 0 AND 5", name="email_proof_failures"),
        CheckConstraint("expires_at > created_at", name="email_proof_expiry"),
    )
