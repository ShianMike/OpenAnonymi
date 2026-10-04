"""Locked occurrence/group decisions and encrypted replacement style admission."""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.contracts import DecisionAction, VersionRef
from app.db.crypto import ContentKeyUnavailable, KeyRing, ProtectedValue
from app.db.models import Decision, EntityGroup, SourceRevision
from app.groups.service import (
    FindingsSnapshot,
    ReviewValidationError,
    _current_locked,
    _group_for_finding,
    _overlap_pairs,
    _require_current_review_access,
    _rows,
    _snapshot,
    _touch_review,
    _version,
)
from app.groups.undo_store import capture, remember
from app.intake.csv_structure import CsvError
from app.transformations.secrets import ensure_secret
from app.transformations.styles import StyleUnavailable, validate_style
from app.workspace.activity import record_event


def decide_findings(
    engine: Engine,
    *,
    document_id: UUID,
    actor_id: UUID,
    finding_id: UUID,
    expected: VersionRef,
    action: DecisionAction,
    keep_reason: str | None,
    affected_ids: set[UUID],
    group_scope: bool,
    now: datetime,
    style: str = "token",
    style_option: str | None = None,
    keys: KeyRing | None = None,
    reauthorize: Callable[[], object] | None = None,
) -> FindingsSnapshot:
    if action == DecisionAction.KEEP:
        if keep_reason not in {"false_match", "intended_disclosure"}:
            raise ReviewValidationError("keep_reason_required", "Choose a Keep reason.")
    elif keep_reason is not None:
        raise ReviewValidationError("unexpected_keep_reason", "Only Keep uses a reason.")
    with Session(engine) as session, session.begin():
        document, version = _current_locked(session, document_id, actor_id, expected, now)
        _require_current_review_access(session, document_id, actor_id, reauthorize)
        active = _rows(session, version)
        finding = next((row for row in active if row.id == finding_id), None)
        if finding is None:
            from app.groups.service import FindingNotFound

            raise FindingNotFound("Finding not found.")
        if group_scope:
            if finding.group_id is None:
                raise ReviewValidationError("not_grouped", "This occurrence is not in a group.")
            rows = [row for row in active if row.group_id == finding.group_id]
        else:
            rows = [finding]
        if affected_ids != {row.id for row in rows}:
            raise ReviewValidationError(
                "affected_occurrences_changed", "Review the affected occurrences again."
            )
        if any(
            left in affected_ids or right in affected_ids for left, right in _overlap_pairs(active)
        ):
            raise ReviewValidationError(
                "overlapping_finding",
                "This range overlaps another finding. Correct or remove that finding first.",
            )
        try:
            for row in rows:
                validate_style(action.value, style, style_option, row.category)
            if style != "token":
                if keys is None:
                    raise ContentKeyUnavailable("Content encryption is unavailable.")
                revision = session.get(SourceRevision, version.source_revision_id)
                source = keys.decrypt_text(
                    ProtectedValue(revision.source_ciphertext, revision.source_key_id)
                )
                values = {row.id: source[row.start_offset : row.end_offset] for row in rows}
                if document.csv_delimiter is not None:
                    from app.db.source_structures import load_csv
                    from app.intake.csv_review import logical_finding_values

                    layout = load_csv(
                        session,
                        revision.id,
                        keys,
                        source,
                        document.csv_delimiter,
                        document.csv_has_header,
                    )
                    values = logical_finding_values(
                        source, layout, [(row.id, row.start_offset, row.end_offset) for row in rows]
                    )
                secret = (
                    ensure_secret(session, document.id, keys, now)
                    if style in {"stand_in", "date_shift"}
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
        except StyleUnavailable as error:
            raise ReviewValidationError(error.code, str(error)) from None
        except CsvError as error:
            raise ReviewValidationError(error.code, str(error)) from None
        before = capture(session, rows)
        if action == DecisionAction.LABEL:
            groups = {
                group.id: group
                for group in session.scalars(
                    select(EntityGroup).where(
                        EntityGroup.id.in_({row.group_id for row in rows if row.group_id})
                    )
                )
            }
            for row in rows:
                if row.group_id not in groups:
                    group = _group_for_finding(session, document, row, now)
                    groups[group.id] = group
        decisions = {
            decision.finding_id: decision
            for decision in session.scalars(
                select(Decision).where(Decision.finding_id.in_([row.id for row in rows]))
            )
        }
        _touch_review(document, now)
        for row in rows:
            decision = decisions.get(row.id)
            if decision is None:
                decision = Decision(finding_id=row.id)
                session.add(decision)
            decision.action = action.value
            decision.style, decision.style_option = style, style_option
            decision.keep_reason = keep_reason
            decision.decided_by = actor_id
            decision.decision_version = document.decision_version
            decision.decided_at = now
        session.flush()
        remember(
            session,
            actor_id=actor_id,
            before=version,
            after=_version(document),
            payload=before,
            now=now,
        )
        snapshot = _snapshot(session, _version(document), actor_id, now)
        record_event(
            session,
            workspace_id=document.workspace_id,
            actor_id=actor_id,
            document_id=document.id,
            event_code="review_decision_saved",
            now=now,
            decision_before=before,
            decision_version=document.decision_version,
        )
        _require_current_review_access(session, document_id, actor_id, reauthorize)
    return snapshot
