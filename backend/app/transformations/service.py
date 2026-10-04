"""Owner-scoped, version-bound preview of the current saved review."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import ContentUnavailable, review_document
from app.contracts import DecisionAction, VersionRef
from app.db.crypto import KeyRing, ProtectedValue
from app.db.models import Document, SourceRevision
from app.groups.service import FindingsSnapshot, _snapshot, _version
from app.transformations.engine import (
    PreviewStatus,
    SpanMapping,
    TransformFinding,
    transform_text,
)
from app.transformations.plan import build_plan, style_capabilities
from app.transformations.styles import StyleUnavailable


@dataclass(frozen=True)
class PreviewSnapshot:
    version: VersionRef
    status: PreviewStatus
    text: str | None
    mappings: tuple[SpanMapping, ...]
    unresolved_ids: tuple[UUID, ...]
    overlaps: tuple[tuple[UUID, UUID], ...]
    fictional_ids: tuple[UUID, ...] = ()
    stand_in_fallback_ids: tuple[UUID, ...] = ()
    style_capabilities: dict | None = None
    csv_cells: tuple[tuple[str, ...], ...] | None = field(default=None, repr=False)


def load_preview(
    engine: Engine,
    *,
    document_id: UUID,
    actor_id: UUID,
    keys: KeyRing,
    now: datetime,
) -> PreviewSnapshot:
    with Session(engine) as session, session.begin():
        document = review_document(session, document_id, actor_id, now, lock=True)
        return build_current_preview(session, document=document, keys=keys)


def build_current_preview(
    session: Session,
    *,
    document: Document,
    keys: KeyRing,
    source: str | None = None,
    findings: FindingsSnapshot | None = None,
) -> PreviewSnapshot:
    """Use inside the caller's authorized document transaction and row lock."""
    version = _version(document)
    revision = session.get(SourceRevision, version.source_revision_id)
    if revision is None or revision.document_id != document.id:
        raise ContentUnavailable("The current source revision is unavailable.")
    if source is None:
        source = keys.decrypt_text(
            ProtectedValue(revision.source_ciphertext, revision.source_key_id)
        )
    findings = findings if findings is not None else _snapshot(session, version)
    csv_layout, logical_values, collision_source = None, None, None
    if document.csv_delimiter is not None:
        from app.db.column_rules import load_rules
        from app.db.source_structures import load_csv
        from app.intake.csv_review import logical_finding_values, logical_source
        from app.intake.csv_structure import CsvError
        from app.transformations.engine import InvalidTransformation

        csv_layout = load_csv(
            session, revision.id, keys, source, document.csv_delimiter, document.csv_has_header
        )
        load_rules(session, document, keys)
        try:
            logical_values = logical_finding_values(
                source,
                csv_layout,
                [
                    (finding.id, finding.span.start, finding.span.end)
                    for finding in findings.findings
                ],
            )
        except CsvError:
            raise InvalidTransformation("CSV findings cannot be applied to this version.") from None
        collision_source = logical_source(source, csv_layout)
    unresolved_ids = tuple(finding.id for finding in findings.findings if finding.action is None)
    capabilities = style_capabilities(
        document, source, findings.findings, logical_values=logical_values
    )
    if findings.overlaps:
        return PreviewSnapshot(
            version,
            "conflict",
            None,
            (),
            unresolved_ids,
            findings.overlaps,
            style_capabilities=capabilities,
        )
    try:
        plan = build_plan(
            session,
            document,
            source,
            findings.findings,
            keys,
            logical_values=logical_values,
            collision_source=collision_source,
        )
    except StyleUnavailable:
        from app.transformations.engine import InvalidTransformation

        raise InvalidTransformation("The current replacement style is unavailable.") from None
    transformed = transform_text(
        source,
        [
            TransformFinding(
                finding_id=finding.id,
                span=finding.span,
                action=DecisionAction(finding.action) if finding.action else None,
                label=finding.label,
            )
            for finding in findings.findings
        ],
        plan,
    )
    csv_cells = None
    if csv_layout is not None:
        from app.intake.csv_review import reviewed_cells

        csv_cells = reviewed_cells(source, csv_layout, transformed.text, transformed.mappings)
    return PreviewSnapshot(
        version=version,
        status="complete" if transformed.complete else "incomplete",
        text=transformed.text,
        mappings=transformed.mappings,
        unresolved_ids=transformed.unresolved_ids,
        overlaps=(),
        fictional_ids=plan.fictional_ids,
        stand_in_fallback_ids=plan.fallback_ids,
        style_capabilities=capabilities,
        csv_cells=csv_cells,
    )
