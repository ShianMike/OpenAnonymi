"""Owner-scoped findings for one current immutable source revision."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import ContentUnavailable, review_document
from app.contracts import DecisionAction, DocumentStatus, FindingCategory, SourceSpan, VersionRef
from app.db.crypto import KeyRing, ProtectedValue
from app.db.labels import allocate_group_locked
from app.db.models import Decision, Document, EntityGroup, Finding, ScanRun, SourceRevision
from app.db.repository import VersionConflict
from app.detection.dates import format_for_span
from app.groups.undo_store import UndoUnavailable, available, capture, remember, replay
from app.lifecycle import require_transition
from app.workspace.activity import record_event


class FindingNotFound(LookupError):
    pass


class ReviewValidationError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class FindingItem:
    id: UUID
    span: SourceSpan
    category: FindingCategory
    origin: str
    rule_id: str | None
    rule_version: str | None
    reason: str | None
    group_id: UUID | None
    label: str | None
    action: str | None
    keep_reason: str | None


@dataclass(frozen=True)
class FindingsSnapshot:
    version: VersionRef
    findings: tuple[FindingItem, ...]
    overlaps: tuple[tuple[UUID, UUID], ...]
    undo_available: int


@dataclass(frozen=True)
class ExactMatches:
    version: VersionRef
    spans: tuple[SourceSpan, ...]
    truncated: bool


def _version(document: Document) -> VersionRef:
    if document.current_revision_id is None:
        raise ContentUnavailable("The document has no saved source revision.")
    return VersionRef(
        document_id=document.id,
        source_revision_id=document.current_revision_id,
        decision_version=document.decision_version,
        settings_version=document.settings_version,
    )


def _rows(session: Session, version: VersionRef) -> list[Finding]:
    current_run_id = session.scalar(
        select(ScanRun.id).where(
            ScanRun.document_id == version.document_id,
            ScanRun.source_revision_id == version.source_revision_id,
            ScanRun.settings_version == version.settings_version,
            ScanRun.status == "completed",
        )
    )
    return session.scalars(
        select(Finding)
        .where(
            Finding.document_id == version.document_id,
            Finding.source_revision_id == version.source_revision_id,
            Finding.removed_at.is_(None),
            or_(Finding.origin == "manual", Finding.scan_run_id == current_run_id)
            if current_run_id is not None
            else Finding.origin == "manual",
        )
        .order_by(Finding.start_offset, Finding.end_offset, Finding.id)
    ).all()


def _snapshot(
    session: Session, version: VersionRef, actor_id: UUID | None = None, now: datetime | None = None
) -> FindingsSnapshot:
    rows = _rows(session, version)
    groups = {
        group.id: group
        for group in session.scalars(
            select(EntityGroup).where(
                EntityGroup.document_id == version.document_id,
                EntityGroup.source_revision_id == version.source_revision_id,
            )
        ).all()
    }
    decisions = (
        {
            decision.finding_id: decision
            for decision in session.scalars(
                select(Decision).where(Decision.finding_id.in_([row.id for row in rows]))
            ).all()
        }
        if rows
        else {}
    )
    return FindingsSnapshot(
        version=version,
        undo_available=available(session, version, actor_id, now)
        if actor_id is not None and now is not None
        else 0,
        findings=tuple(
            FindingItem(
                id=row.id,
                span=SourceSpan(start=row.start_offset, end=row.end_offset),
                category=FindingCategory(row.category),
                origin=row.origin,
                rule_id=row.rule_id,
                rule_version=row.rule_version,
                reason=row.reason,
                group_id=row.group_id,
                label=groups[row.group_id].label if row.group_id in groups else None,
                action=decisions[row.id].action if row.id in decisions else None,
                keep_reason=decisions[row.id].keep_reason if row.id in decisions else None,
            )
            for row in rows
        ),
        overlaps=tuple(
            (left.id, right.id)
            for index, left in enumerate(rows)
            for right in rows[index + 1 :]
            if right.start_offset < left.end_offset and left.start_offset < right.end_offset
        ),
    )


def load_findings(
    engine: Engine, *, document_id: UUID, actor_id: UUID, now: datetime
) -> FindingsSnapshot:
    with Session(engine) as session:
        document = review_document(session, document_id, actor_id, now)
        return _snapshot(session, _version(document), actor_id, now)


def _current_locked(
    session: Session, document_id: UUID, actor_id: UUID, expected: VersionRef, now: datetime
) -> tuple[Document, VersionRef]:
    document = review_document(session, document_id, actor_id, now, lock=True)
    version = _version(document)
    if expected != version:
        raise VersionConflict(version)
    return document, version


def _validated_selection(
    session: Session, version: VersionRef, span: SourceSpan, keys: KeyRing
) -> str:
    revision = session.get(SourceRevision, version.source_revision_id)
    if (
        revision is None
        or revision.document_id != version.document_id
        or span.end > revision.code_points
    ):
        raise ReviewValidationError(
            "invalid_span", "The selected range is outside the current text."
        )
    source = keys.decrypt_text(ProtectedValue(revision.source_ciphertext, revision.source_key_id))
    if not source[span.start : span.end].strip():
        raise ReviewValidationError("invalid_span", "Select visible text to mark.")
    return source


def _active_finding(session: Session, version: VersionRef, finding_id: UUID) -> Finding:
    finding = next((row for row in _rows(session, version) if row.id == finding_id), None)
    if finding is None:
        raise FindingNotFound("Finding not found.")
    return finding


def exact_matches(
    engine: Engine,
    *,
    document_id: UUID,
    finding_id: UUID,
    actor_id: UUID,
    keys: KeyRing,
    now: datetime,
) -> ExactMatches:
    """Offer offsets only; the owner explicitly chooses which occurrences to mark."""
    with Session(engine) as session:
        document = review_document(session, document_id, actor_id, now)
        version = _version(document)
        finding = _active_finding(session, version, finding_id)
        revision = session.get(SourceRevision, version.source_revision_id)
        source = keys.decrypt_text(
            ProtectedValue(revision.source_ciphertext, revision.source_key_id)
        )
        needle = source[finding.start_offset : finding.end_offset]
        occupied = _rows(session, version)
        spans: list[SourceSpan] = []
        cursor = 0
        occupied_index = 0
        truncated = False
        while (position := source.find(needle, cursor)) != -1:
            cursor = position + 1
            end = position + len(needle)
            while (
                occupied_index < len(occupied) and occupied[occupied_index].end_offset <= position
            ):
                occupied_index += 1
            if occupied_index < len(occupied) and occupied[occupied_index].start_offset < end:
                continue
            if len(spans) == 100:
                truncated = True
                break
            spans.append(SourceSpan(start=position, end=end))
        return ExactMatches(version, tuple(spans), truncated)


def _require_nonoverlap(
    session: Session, version: VersionRef, span: SourceSpan, *, exclude_id: UUID | None = None
) -> None:
    for other in _rows(session, version):
        if other.id == exclude_id:
            continue
        if span.start < other.end_offset and other.start_offset < span.end:
            raise ReviewValidationError(
                "overlapping_finding",
                "This range overlaps another finding. Correct or remove that finding first.",
            )


def _touch_review(document: Document, now: datetime) -> None:
    document.decision_version += 1
    if document.status != DocumentStatus.NEEDS_REVIEW:
        require_transition(DocumentStatus(document.status), DocumentStatus.NEEDS_REVIEW)
    document.status = DocumentStatus.NEEDS_REVIEW
    document.updated_at = now


def _record_review_edit(
    session: Session, document: Document, actor_id: UUID, event_code: str, now: datetime
) -> None:
    record_event(
        session,
        workspace_id=document.workspace_id,
        actor_id=actor_id,
        document_id=document.id,
        event_code=event_code,
        now=now,
    )


def add_finding(
    engine: Engine,
    *,
    document_id: UUID,
    actor_id: UUID,
    expected: VersionRef,
    span: SourceSpan,
    category: FindingCategory,
    keys: KeyRing,
    now: datetime,
) -> FindingsSnapshot:
    with Session(engine) as session, session.begin():
        document, version = _current_locked(session, document_id, actor_id, expected, now)
        source = _validated_selection(session, version, span, keys)
        _require_nonoverlap(session, version, span)
        created_id = uuid4()
        before = capture(session, [], created=(created_id,))
        session.add(
            Finding(
                id=created_id,
                document_id=document_id,
                source_revision_id=version.source_revision_id,
                category=category.value,
                date_format=format_for_span(source, span.start, span.end, document.phone_region) if category == FindingCategory.DATE else None,
                origin="manual",
                start_offset=span.start,
                end_offset=span.end,
                created_at=now,
            )
        )
        _touch_review(document, now)
        _record_review_edit(session, document, actor_id, "finding_added", now)
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
    return snapshot


def revise_finding(
    engine: Engine,
    *,
    document_id: UUID,
    finding_id: UUID,
    actor_id: UUID,
    expected: VersionRef,
    span: SourceSpan,
    category: FindingCategory,
    keys: KeyRing,
    now: datetime,
) -> FindingsSnapshot:
    with Session(engine) as session, session.begin():
        document, version = _current_locked(session, document_id, actor_id, expected, now)
        finding = _active_finding(session, version, finding_id)
        source = _validated_selection(session, version, span, keys)
        _require_nonoverlap(session, version, span, exclude_id=finding_id)
        if (finding.start_offset, finding.end_offset, finding.category) == (
            span.start,
            span.end,
            category.value,
        ):
            return _snapshot(session, version, actor_id, now)
        before = capture(session, [finding])
        finding.start_offset = span.start
        finding.end_offset = span.end
        finding.category = category.value
        finding.date_format = format_for_span(source, span.start, span.end, document.phone_region) if category == FindingCategory.DATE else None
        finding.origin = "manual"
        finding.scan_run_id = None
        finding.rule_id = None
        finding.rule_version = None
        finding.reason = None
        finding.group_id = None
        decision = session.get(Decision, finding_id)
        if decision is not None:
            session.delete(decision)
        _touch_review(document, now)
        _record_review_edit(session, document, actor_id, "finding_corrected", now)
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
    return snapshot


def remove_finding(
    engine: Engine,
    *,
    document_id: UUID,
    finding_id: UUID,
    actor_id: UUID,
    expected: VersionRef,
    now: datetime,
) -> FindingsSnapshot:
    with Session(engine) as session, session.begin():
        document, version = _current_locked(session, document_id, actor_id, expected, now)
        finding = _active_finding(session, version, finding_id)
        before = capture(session, [finding])
        finding.removed_at = now
        decision = session.get(Decision, finding_id)
        if decision is not None:
            session.delete(decision)
        _touch_review(document, now)
        _record_review_edit(session, document, actor_id, "finding_removed", now)
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
    return snapshot


def add_exact_match(
    engine: Engine,
    *,
    document_id: UUID,
    actor_id: UUID,
    finding_id: UUID,
    expected: VersionRef,
    span: SourceSpan,
    keys: KeyRing,
    now: datetime,
) -> FindingsSnapshot:
    """Mark one user-confirmed exact occurrence; never infer a shared identity."""
    with Session(engine) as session, session.begin():
        document, version = _current_locked(session, document_id, actor_id, expected, now)
        source_finding = _active_finding(session, version, finding_id)
        revision = session.get(SourceRevision, version.source_revision_id)
        source = keys.decrypt_text(
            ProtectedValue(revision.source_ciphertext, revision.source_key_id)
        )
        if (
            span.end > len(source)
            or source[span.start : span.end]
            != source[source_finding.start_offset : source_finding.end_offset]
        ):
            raise ReviewValidationError("not_exact_match", "This range is not an exact match.")
        _require_nonoverlap(session, version, span)
        created_id = uuid4()
        before = capture(session, [], created=(created_id,))
        session.add(
            Finding(
                id=created_id,
                document_id=document_id,
                source_revision_id=version.source_revision_id,
                category=source_finding.category,
                date_format=format_for_span(source, span.start, span.end, document.phone_region) if source_finding.category == FindingCategory.DATE else None,
                origin="manual",
                start_offset=span.start,
                end_offset=span.end,
                created_at=now,
            )
        )
        _touch_review(document, now)
        _record_review_edit(session, document, actor_id, "finding_added", now)
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
    return snapshot


def _group_for_finding(
    session: Session, document: Document, finding: Finding, now: datetime
) -> EntityGroup:
    if finding.group_id is not None:
        group = session.get(EntityGroup, finding.group_id)
        if group is not None:
            return group
    group = allocate_group_locked(
        session, document=document, category=FindingCategory(finding.category), now=now
    )
    finding.group_id = group.id
    return group


def split_finding(
    engine: Engine,
    *,
    document_id: UUID,
    actor_id: UUID,
    finding_id: UUID,
    expected: VersionRef,
    now: datetime,
) -> FindingsSnapshot:
    with Session(engine) as session, session.begin():
        document, version = _current_locked(session, document_id, actor_id, expected, now)
        finding = _active_finding(session, version, finding_id)
        if finding.group_id is None:
            raise ReviewValidationError("not_grouped", "This occurrence is not in a group.")
        members = [row for row in _rows(session, version) if row.group_id == finding.group_id]
        if len(members) < 2:
            raise ReviewValidationError("single_member_group", "This group has one occurrence.")
        before = capture(session, members)
        finding.group_id = allocate_group_locked(
            session, document=document, category=FindingCategory(finding.category), now=now
        ).id
        _touch_review(document, now)
        _record_review_edit(session, document, actor_id, "group_split", now)
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
    return snapshot


def merge_findings(
    engine: Engine,
    *,
    document_id: UUID,
    actor_id: UUID,
    source_finding_id: UUID,
    target_finding_id: UUID,
    expected: VersionRef,
    now: datetime,
) -> FindingsSnapshot:
    with Session(engine) as session, session.begin():
        document, version = _current_locked(session, document_id, actor_id, expected, now)
        source = _active_finding(session, version, source_finding_id)
        target = _active_finding(session, version, target_finding_id)
        if source.id == target.id:
            raise ReviewValidationError("same_finding", "Choose two occurrences to merge.")
        if source.category != target.category:
            raise ReviewValidationError("incompatible_category", "Categories must match to merge.")
        already_merged = source.group_id is not None and source.group_id == target.group_id
        if already_merged:
            return _snapshot(session, version, actor_id, now)
        before = capture(
            session,
            [
                row
                for row in _rows(session, version)
                if row.id in {source.id, target.id}
                or (source.group_id is not None and row.group_id == source.group_id)
                or (target.group_id is not None and row.group_id == target.group_id)
            ],
        )
        if target.group_id is None and source.group_id is not None:
            target_group = session.get(EntityGroup, source.group_id)
            target.group_id = target_group.id
        else:
            target_group = _group_for_finding(session, document, target, now)
        old_group_id = source.group_id
        for row in _rows(session, version):
            if row.id == source.id or (old_group_id is not None and row.group_id == old_group_id):
                row.group_id = target_group.id
        _touch_review(document, now)
        _record_review_edit(session, document, actor_id, "group_merged", now)
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
    return snapshot


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
) -> FindingsSnapshot:
    if action == DecisionAction.KEEP:
        if keep_reason not in {"false_match", "intended_disclosure"}:
            raise ReviewValidationError("keep_reason_required", "Choose a Keep reason.")
    elif keep_reason is not None:
        raise ReviewValidationError("unexpected_keep_reason", "Only Keep uses a reason.")
    with Session(engine) as session, session.begin():
        document, version = _current_locked(session, document_id, actor_id, expected, now)
        finding = _active_finding(session, version, finding_id)
        if group_scope:
            if finding.group_id is None:
                raise ReviewValidationError("not_grouped", "This occurrence is not in a group.")
            rows = [row for row in _rows(session, version) if row.group_id == finding.group_id]
        else:
            rows = [finding]
        if affected_ids != {row.id for row in rows}:
            raise ReviewValidationError(
                "affected_occurrences_changed", "Review the affected occurrences again."
            )
        for row in rows:
            _require_nonoverlap(
                session,
                version,
                SourceSpan(start=row.start_offset, end=row.end_offset),
                exclude_id=row.id,
            )
        before = capture(session, rows)
        if action == DecisionAction.LABEL:
            for row in rows:
                _group_for_finding(session, document, row, now)
        _touch_review(document, now)
        for row in rows:
            decision = session.get(Decision, row.id)
            if decision is None:
                decision = Decision(finding_id=row.id)
                session.add(decision)
            decision.action = action.value
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
        )
    return snapshot


def undo_last_review_edit(
    engine: Engine,
    *,
    document_id: UUID,
    actor_id: UUID,
    expected: VersionRef,
    now: datetime,
) -> FindingsSnapshot:
    """Replay the actor's latest current-version edit across processes/restarts."""
    with Session(engine) as session, session.begin():
        document, version = _current_locked(session, document_id, actor_id, expected, now)
        try:
            replay(session, version=version, actor_id=actor_id, now=now)
        except UndoUnavailable as error:
            raise ReviewValidationError(error.code, str(error)) from None
        _touch_review(document, now)
        _record_review_edit(session, document, actor_id, "review_edit_undone", now)
        session.flush()
        return _snapshot(session, _version(document), actor_id, now)
