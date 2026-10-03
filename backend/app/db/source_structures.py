"""Encrypted, revision-owned layout maps with no plaintext content columns."""

import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    event,
    inspect,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db.base import Base
from app.db.crypto import KeyRing, ProtectedContentError, ProtectedValue
from app.intake.structure import InvalidLayout, leaves, validate_layout


class SourceStructure(Base):
    __tablename__ = "source_structures"
    revision_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("source_revisions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    layout_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_id: Mapped[str] = mapped_column(String(80), nullable=False)
    block_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        CheckConstraint("kind IN ('docx','csv')", name="valid_kind"),
        CheckConstraint("block_count BETWEEN 1 AND 20000", name="bounded_block_count"),
    )


def store_word(session, revision_id, layout, source, keys: KeyRing, now):
    if layout is None:
        return
    validate_layout(layout, len(source), source)
    protected = keys.encrypt_text(json.dumps(layout, separators=(",", ":")))
    session.add(
        SourceStructure(
            revision_id=revision_id,
            kind="docx",
            layout_ciphertext=protected.ciphertext,
            key_id=protected.key_id,
            block_count=sum(1 for _ in leaves(layout)),
            created_at=now,
        )
    )


def load_word(session, revision_id, keys: KeyRing, length, source=None):
    row = session.get(SourceStructure, revision_id)
    if row is None:
        return None
    if row.kind != "docx":
        raise ProtectedContentError("Protected layout is unavailable.")
    try:
        layout = json.loads(keys.decrypt_text(ProtectedValue(row.layout_ciphertext, row.key_id)))
        validate_layout(layout, length, source)
        if sum(1 for _ in leaves(layout)) != row.block_count:
            raise InvalidLayout("Invalid protected layout.")
        return layout
    except (InvalidLayout, TypeError, ValueError, KeyError):
        raise ProtectedContentError("Protected layout is unavailable.") from None


@event.listens_for(Session, "before_flush")
def prevent_layout_edits(session, _context, _instances):
    for row in session.dirty:
        if not isinstance(row, SourceStructure) or not session.is_modified(row):
            continue
        if not session.info.get("allow_source_key_rotation") or any(
            inspect(row).attrs[field].history.has_changes()
            for field in ("revision_id", "kind", "block_count", "created_at")
        ):
            raise InvalidLayout("Source layouts are immutable.")
