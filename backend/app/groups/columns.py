"""One explicit column decision with exact IDs, independent labels and durable undo."""

from datetime import UTC

from sqlalchemy.orm import Session

from app.accounts.access import owned_document
from app.contracts import DecisionAction, FindingCategory, SourceSpan
from app.db.crypto import ProtectedValue
from app.db.labels import allocate_group_locked
from app.db.models import Decision, SourceRevision
from app.db.repository import VersionConflict
from app.db.source_structures import load_csv
from app.groups.service import (
    ReviewValidationError,
    _require_nonoverlap,
    _rows,
    _snapshot,
    _touch_review,
    _version,
)
from app.groups.undo_store import capture, remember
from app.intake.csv_review import logical_finding_values
from app.intake.csv_structure import cell_value
from app.transformations.secrets import ensure_secret
from app.transformations.styles import StyleUnavailable, validate_style
from app.workspace.activity import record_event


def decide_column(
    engine,
    *,
    document_id,
    actor_id,
    column,
    expected,
    affected_ids,
    action,
    keep_reason,
    style,
    style_option,
    same_text_same_entity,
    keys,
    now,
):
    if action == DecisionAction.KEEP and keep_reason not in ("false_match", "intended_disclosure"):
        raise ReviewValidationError("keep_reason_required", "Choose a Keep reason.")
    if action != DecisionAction.KEEP and keep_reason is not None:
        raise ReviewValidationError("unexpected_keep_reason", "Only Keep uses a reason.")
    if same_text_same_entity and action != DecisionAction.LABEL:
        raise ReviewValidationError(
            "column_grouping_requires_label", "Identical-cell grouping applies to Label."
        )
    with Session(engine) as session, session.begin():
        document = owned_document(session, document_id, actor_id, now, lock=True)
        version = _version(document)
        if expected != version:
            raise VersionConflict(version)
        if document.csv_delimiter is None:
            raise ReviewValidationError(
                "csv_required", "Column decisions apply to imported CSV documents."
            )
        revision = session.get(SourceRevision, version.source_revision_id)
        source = keys.decrypt_text(
            ProtectedValue(revision.source_ciphertext, revision.source_key_id)
        )
        layout = load_csv(
            session, revision.id, keys, source, document.csv_delimiter, document.csv_has_header
        )
        if not 0 <= column < layout["columns"]:
            raise ReviewValidationError("column_not_found", "Column not found.")
        cells = [record[column] for record in layout["records"][int(layout["has_header"]) :]]
        all_rows = _rows(session, version)
        rows, row_cells = [], {}
        index = 0
        for row in all_rows:
            while index < len(cells) and cells[index]["end"] <= row.start_offset:
                index += 1
            if (
                index < len(cells)
                and cells[index]["start"]
                <= row.start_offset
                < row.end_offset
                <= cells[index]["end"]
            ):
                rows.append(row)
                row_cells[row.id] = cells[index]
        if affected_ids != {row.id for row in rows}:
            raise ReviewValidationError(
                "affected_occurrences_changed", "Review the affected column findings again."
            )
        if not rows:
            raise ReviewValidationError(
                "no_column_findings", "This column has no current findings to decide."
            )
        values = logical_finding_values(
            source, layout, [(row.id, row.start_offset, row.end_offset) for row in rows]
        )
        for row in rows:
            _require_nonoverlap(
                session,
                version,
                SourceSpan(start=row.start_offset, end=row.end_offset),
                exclude_id=row.id,
            )
        try:
            for row in rows:
                validate_style(action.value, style, style_option, row.category)
            secret = (
                ensure_secret(session, document.id, keys, now)
                if style in ("stand_in", "date_shift")
                else None
            )
            for row in rows:
                validate_style(
                    action.value,
                    style,
                    style_option,
                    row.category,
                    value=values[row.id],
                    date_format=row.date_format,
                    region=document.phone_region,
                    offset=secret.offset if secret else None,
                    created=document.created_at.astimezone(UTC).date(),
                )
        except StyleUnavailable as exc:
            raise ReviewValidationError(exc.code, str(exc)) from None
        before = capture(session, rows)
        if action == DecisionAction.LABEL:
            grouped = {}
            for row in rows:
                key = (
                    (row.category, cell_value(source, row_cells[row.id]), values[row.id])
                    if same_text_same_entity
                    else row.id
                )
                if key not in grouped:
                    grouped[key] = allocate_group_locked(
                        session, document=document, category=FindingCategory(row.category), now=now
                    ).id
                row.group_id = grouped[key]
        _touch_review(document, now)
        for row in rows:
            decision = session.get(Decision, row.id)
            if decision is None:
                decision = Decision(finding_id=row.id)
                session.add(decision)
            decision.action, decision.keep_reason = action.value, keep_reason
            decision.style, decision.style_option = style, style_option
            decision.decided_by, decision.decided_at = actor_id, now
            decision.decision_version = document.decision_version
        session.flush()
        remember(
            session,
            actor_id=actor_id,
            before=version,
            after=_version(document),
            payload=before,
            now=now,
        )
        record_event(
            session,
            workspace_id=document.workspace_id,
            actor_id=actor_id,
            document_id=document.id,
            event_code="review_decision_saved",
            now=now,
        )
        return _snapshot(session, _version(document), actor_id, now)
