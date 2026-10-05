"""Current CSV syntax and column choices under the document's review lock."""

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.access import owned_document
from app.db.column_rules import load_rules, store_rules
from app.db.crypto import KeyRing, ProtectedContentError, ProtectedValue
from app.db.models import Finding, SourceRevision
from app.db.repository import VersionConflict, _version
from app.db.source_structures import load_csv
from app.detection.service import invalidate_scan_settings
from app.intake.column_rules import bind_rules, match_preset
from app.intake.csv_structure import CsvError, cell_value, parse_csv, span_cell


def csv_info(session, document, source: str, keys: KeyRing) -> dict:
    layout = load_csv(
        session,
        document.current_revision_id,
        keys,
        source,
        document.csv_delimiter,
        document.csv_has_header,
    )
    rules = load_rules(session, document, keys)
    if any(rule["column"] >= layout["columns"] for rule in rules):
        raise ProtectedContentError("Protected column settings are unavailable.")
    return {
        "delimiter": layout["delimiter"],
        "has_header": layout["has_header"],
        "columns": layout["columns"],
        "data_rows": len(layout["records"]) - int(layout["has_header"]),
        "headers": [cell_value(source, cell) for cell in layout["records"][0]]
        if layout["has_header"]
        else [],
        "rules": rules,
        "cells": layout["records"],
    }


def change_csv_settings(
    engine,
    *,
    document_id,
    actor_id,
    expected_settings_version: int,
    delimiter: str | None,
    has_header: bool | None,
    rules: list[dict] | None,
    keys: KeyRing,
    now: datetime,
    reauthorize: Callable[[], object] | None = None,
):
    def authorize(session):
        if reauthorize is not None:
            reauthorize()
            owned_document(session, document_id, actor_id, datetime.now(UTC))

    with Session(engine) as session, session.begin():
        document = owned_document(session, document_id, actor_id, now, lock=True)
        authorize(session)
        if document.settings_version != expected_settings_version:
            raise VersionConflict(_version(document))
        if document.csv_delimiter is None:
            raise CsvError("csv_required", "These settings apply to an imported CSV document.")
        revision = session.get(SourceRevision, document.current_revision_id)
        source = keys.decrypt_text(
            ProtectedValue(revision.source_ciphertext, revision.source_key_id)
        )
        old = csv_info(session, document, source, keys)
        selected_delimiter = delimiter if delimiter is not None else document.csv_delimiter
        selected_header = has_header if has_header is not None else document.csv_has_header
        layout = parse_csv(
            source, selected_delimiter, "true" if selected_header else "false", remove_bom=False
        ).layout
        syntax_changed = (
            old["delimiter"] != selected_delimiter or old["has_header"] != selected_header
        )
        if rules is not None:
            selected_rules = bind_rules(rules, source, layout)
        elif syntax_changed:
            selected_rules = match_preset(old["rules"], source, layout)
        else:
            selected_rules = old["rules"]
        if not syntax_changed and selected_rules == old["rules"]:
            authorize(session)
            return {"version": _version(document), **old}
        document.csv_delimiter = selected_delimiter
        document.csv_has_header = selected_header
        invalidate_scan_settings(session, document, actor_id, now, copy_columns=False)
        store_rules(session, document, selected_rules, source, layout, keys)
        if syntax_changed:
            # Manual spans that no longer represent whole cell content boundaries
            # remain in history but cannot enter the new current review.
            for finding in session.scalars(
                select(Finding).where(
                    Finding.document_id == document.id,
                    Finding.source_revision_id == revision.id,
                    Finding.origin == "manual",
                    Finding.removed_at.is_(None),
                )
            ):
                try:
                    span_cell(layout, source, finding.start_offset, finding.end_offset)
                except CsvError:
                    finding.removed_at = now
        session.flush()
        result = {"version": _version(document), **csv_info(session, document, source, keys)}
        authorize(session)
        return result
