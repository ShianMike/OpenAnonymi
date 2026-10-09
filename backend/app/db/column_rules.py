"""Encrypted immutable column-rule snapshots tied to document settings versions."""

import json
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Integer, LargeBinary, String, event, inspect
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db.base import Base
from app.db.crypto import KeyRing, ProtectedContentError, ProtectedValue
from app.intake.column_rules import bind_rules, validate_rules
from app.intake.csv_structure import CsvError


class DocumentColumnRules(Base):
    __tablename__ = "document_column_rules"
    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    settings_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    rules_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_id: Mapped[str] = mapped_column(String(80), nullable=False)
    csv_delimiter: Mapped[str] = mapped_column(String(1), nullable=False)
    csv_has_header: Mapped[bool] = mapped_column(nullable=False)
    __table_args__ = (
        CheckConstraint("settings_version >= 1", name="positive_column_settings_version"),
        CheckConstraint("csv_delimiter IN (',',';',E'\\t','|')", name="valid_column_delimiter"),
    )


def store_rules(session, document, rules, source, layout, keys: KeyRing):
    result = bind_rules(rules, source, layout)
    protected = keys.encrypt_text(json.dumps(result, separators=(",", ":")))
    session.add(
        DocumentColumnRules(
            document_id=document.id,
            settings_version=document.settings_version,
            rules_ciphertext=protected.ciphertext,
            key_id=protected.key_id,
            csv_delimiter=layout["delimiter"],
            csv_has_header=layout["has_header"],
        )
    )


def load_rules(session, document, keys: KeyRing) -> list[dict]:
    row = session.get(DocumentColumnRules, (document.id, document.settings_version))
    if (
        row is None
        or row.csv_delimiter != document.csv_delimiter
        or row.csv_has_header != document.csv_has_header
    ):
        raise ProtectedContentError("Protected column settings are unavailable.")
    try:
        return validate_rules(
            json.loads(keys.decrypt_text(ProtectedValue(row.rules_ciphertext, row.key_id)))
        )
    except (CsvError, TypeError, ValueError, KeyError):
        raise ProtectedContentError("Protected column settings are unavailable.") from None


def copy_rules(session, document, previous_settings):
    if document.csv_delimiter is None:
        return
    old = session.get(DocumentColumnRules, (document.id, previous_settings))
    if old is None:
        raise ProtectedContentError("Protected column settings are unavailable.")
    session.add(
        DocumentColumnRules(
            document_id=document.id,
            settings_version=document.settings_version,
            rules_ciphertext=old.rules_ciphertext,
            key_id=old.key_id,
            csv_delimiter=old.csv_delimiter,
            csv_has_header=old.csv_has_header,
        )
    )


def load_preset_rules(preset, keys: KeyRing | None) -> list[dict]:
    if preset.column_rules_ciphertext is None and preset.column_rules_key_id is None:
        return []
    if keys is None or preset.column_rules_ciphertext is None or preset.column_rules_key_id is None:
        raise ProtectedContentError("Protected preset column settings are unavailable.")
    try:
        return validate_rules(
            json.loads(
                keys.decrypt_text(
                    ProtectedValue(preset.column_rules_ciphertext, preset.column_rules_key_id)
                )
            )
        )
    except (CsvError, TypeError, ValueError, KeyError):
        raise ProtectedContentError("Protected preset column settings are unavailable.") from None


@event.listens_for(Session, "before_flush")
def immutable_column_rules(session, _context, _instances):
    for row in session.dirty:
        if not isinstance(row, DocumentColumnRules) or not session.is_modified(row):
            continue
        if not session.info.get("allow_source_key_rotation") or any(
            inspect(row).attrs[name].history.has_changes()
            for name in ("document_id", "settings_version", "csv_delimiter", "csv_has_header")
        ):
            raise CsvError("csv_column_rules_invalid", "Column rule snapshots are immutable.")
