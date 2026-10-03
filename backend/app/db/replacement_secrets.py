"""One encrypted replacement seed/date offset per document; never an API field."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models import timestamp_column


class DocumentReplacementSecret(Base):
    __tablename__ = "document_replacement_secrets"

    document_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    secret_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_id: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = timestamp_column()
