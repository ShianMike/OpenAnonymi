"""Personal flags only; access to a document is checked separately on every use."""

from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DocumentPreference(Base):
    __tablename__ = "document_preferences"

    actor_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    document_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    __table_args__ = (CheckConstraint("favorite OR pinned", name="nonempty_document_preference"),)
