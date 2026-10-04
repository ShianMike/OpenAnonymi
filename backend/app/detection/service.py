"""Version-bound scan orchestration and persisted unresolved suggestions."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import (
    ContentUnavailable,
    DocumentNotFound,
    owned_document,
    review_document,
)
from app.contracts import (
    AUTOMATIC_CATEGORIES,
    DocumentStatus,
    FindingCategory,
    SourceSpan,
    VersionRef,
)
from app.db.crypto import KeyRing, ProtectedValue
from app.db.models import Document, Finding, ScanRun, SourceRevision
from app.db.repository import VersionConflict
from app.detection.dates import format_for_span
from app.detection.rules import DETECTOR_VERSION, DetectionLimitError, detect_suggestions
from app.lifecycle import require_transition
from app.workspace.activity import record_event

ScanStatus = Literal["not_started", "scanning", "completed", "failed", "superseded"]
SCAN_LEASE = timedelta(minutes=2)


class ScanExecutionFailed(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class StoredSuggestion:
    id: UUID
    span: SourceSpan
    category: FindingCategory
    rule_id: str
    rule_version: str
    reason: str
    date_format: str | None


@dataclass(frozen=True)
class ScanSnapshot:
    version: VersionRef
    status: ScanStatus
    attempt_count: int
    match_count: int | None
    failure_code: str | None
    suggestions: tuple[StoredSuggestion, ...]
    dropped_suggestions: int = 0


def _version(document: Document) -> VersionRef:
    if document.current_revision_id is None:
        raise ContentUnavailable("The document has no saved source revision.")
    return VersionRef(
        document_id=document.id,
        source_revision_id=document.current_revision_id,
        decision_version=document.decision_version,
        settings_version=document.settings_version,
    )


def _run_for_current(
    session: Session, version: VersionRef, *, lock: bool = False
) -> ScanRun | None:
    query = select(ScanRun).where(
        ScanRun.document_id == version.document_id,
        ScanRun.source_revision_id == version.source_revision_id,
        ScanRun.settings_version == version.settings_version,
    )
    if lock:
        query = query.with_for_update()
    return session.scalar(query)


def _snapshot(session: Session, version: VersionRef, run: ScanRun | None) -> ScanSnapshot:
    if run is None:
        return ScanSnapshot(version, "not_started", 0, None, None, ())
    rows = session.scalars(
        select(Finding)
        .where(Finding.scan_run_id == run.id, Finding.removed_at.is_(None))
        .order_by(Finding.start_offset, Finding.end_offset, Finding.id)
    ).all()
    return ScanSnapshot(
        version=version,
        status=run.status,
        attempt_count=run.attempt_count,
        match_count=run.match_count,
        failure_code=run.failure_code,
        dropped_suggestions=run.dropped_suggestions,
        suggestions=tuple(
            StoredSuggestion(
                id=row.id,
                span=SourceSpan(start=row.start_offset, end=row.end_offset),
                category=FindingCategory(row.category),
                rule_id=row.rule_id,
                rule_version=row.rule_version,
                reason=row.reason,
                date_format=row.date_format,
            )
            for row in rows
        ),
    )


def load_scan_state(
    engine: Engine, *, document_id: UUID, actor_id: UUID, now: datetime
) -> ScanSnapshot:
    with Session(engine) as session, session.begin():
        document = review_document(session, document_id, actor_id, now, lock=True)
        version = _version(document)
        run = _run_for_current(session, version, lock=True)
        if run is not None and run.status == "scanning" and now - run.started_at >= SCAN_LEASE:
            run.status = "failed"
            run.failure_code = "scan_interrupted"
            run.finished_at = now
            if document.status == DocumentStatus.SCANNING:
                require_transition(DocumentStatus(document.status), DocumentStatus.FAILED)
                document.status = DocumentStatus.FAILED
                document.updated_at = now
            record_event(
                session,
                workspace_id=document.workspace_id,
                actor_id=None,
                document_id=document.id,
                event_code="scan_failed",
                now=now,
                outcome="failed",
            )
        return _snapshot(session, version, run)


def invalidate_scan_settings(session, document, actor_id, now, *, copy_columns=True):
    """All scan-setting mutations share versioning, undo and review invalidation."""
    previous_settings = document.settings_version
    document.settings_version += 1
    from app.custom_rules.service import copy_snapshot
    from app.db.column_rules import copy_rules
    from app.groups.undo_store import clear_document

    clear_document(session, document.id)
    copy_snapshot(session, document, previous_settings)
    if copy_columns:
        copy_rules(session, document, previous_settings)
    document.decision_version += 1
    if document.status != DocumentStatus.DRAFT:
        require_transition(DocumentStatus(document.status), DocumentStatus.DRAFT)
    document.status = DocumentStatus.DRAFT
    document.updated_at = now
    session.flush()
    record_event(
        session,
        workspace_id=document.workspace_id,
        actor_id=actor_id,
        document_id=document.id,
        event_code="scan_settings_changed",
        now=now,
    )


def change_scan_settings(
    engine: Engine,
    *,
    document_id: UUID,
    actor_id: UUID,
    expected: VersionRef,
    categories: set[FindingCategory],
    phone_region: str,
    now: datetime,
    language: str | None = None,
) -> VersionRef:
    if not categories.issubset(AUTOMATIC_CATEGORIES):
        raise ValueError("Choose supported automatic suggestion categories.")
    # Detector validation is the single source for supported regions.
    from phonenumbers import SUPPORTED_REGIONS

    region = phone_region.upper()
    if region not in SUPPORTED_REGIONS:
        raise ValueError("Choose a supported phone region.")
    from app.detection.local_nlp import SUPPORTED_LANGUAGES

    if language is not None and language not in SUPPORTED_LANGUAGES:
        raise ValueError("Choose a supported language.")
    encoded_categories = ",".join(sorted(category.value for category in categories))
    with Session(engine) as session, session.begin():
        document = owned_document(session, document_id, actor_id, now, lock=True)
        current = _version(document)
        if expected != current:
            raise VersionConflict(current)
        selected_language = language if language is not None else document.language
        if (
            document.category_settings == encoded_categories
            and document.phone_region == region
            and document.language == selected_language
        ):
            return current
        document.category_settings = encoded_categories
        document.phone_region = region
        document.language = selected_language
        invalidate_scan_settings(session, document, actor_id, now)
        return _version(document)


def _finish_failed(
    engine: Engine,
    *,
    run_id: UUID,
    expected: VersionRef,
    actor_id: UUID,
    attempt_count: int,
    code: str,
) -> VersionRef | None:
    now = datetime.now(UTC)
    try:
        with Session(engine) as session, session.begin():
            document = owned_document(session, expected.document_id, actor_id, now, lock=True)
            run = session.get(ScanRun, run_id)
            if run is None or run.status != "scanning" or run.attempt_count != attempt_count:
                return None
            run.finished_at = now
            if _version(document) != expected:
                run.status = "superseded"
                return _version(document)
            run.status = "failed"
            run.failure_code = code
            require_transition(DocumentStatus(document.status), DocumentStatus.FAILED)
            document.status = DocumentStatus.FAILED
            document.updated_at = now
            record_event(
                session,
                workspace_id=document.workspace_id,
                actor_id=actor_id,
                document_id=document.id,
                event_code="scan_failed",
                now=now,
                outcome="failed",
            )
    except (DocumentNotFound, ContentUnavailable):
        _supersede_run(engine, run_id, attempt_count)
        raise
    return None


def _supersede_run(engine: Engine, run_id: UUID, attempt_count: int) -> None:
    """Close an in-flight run even when the initiating member lost access."""
    with Session(engine) as session, session.begin():
        run = session.scalar(select(ScanRun).where(ScanRun.id == run_id).with_for_update())
        if run is not None and run.status == "scanning" and run.attempt_count == attempt_count:
            run.status = "superseded"
            run.finished_at = datetime.now(UTC)


def scan_document(
    engine: Engine,
    *,
    document_id: UUID,
    actor_id: UUID,
    expected: VersionRef,
    keys: KeyRing,
    now: datetime,
) -> ScanSnapshot:
    """Claim a run, detect outside the lock, then commit only for the same version."""
    with Session(engine) as session, session.begin():
        document = owned_document(session, document_id, actor_id, now, lock=True)
        current = _version(document)
        if (
            expected.document_id != document_id
            or expected.source_revision_id != current.source_revision_id
            or expected.settings_version != current.settings_version
        ):
            raise VersionConflict(current)
        run = _run_for_current(session, current, lock=True)
        if run is not None and run.status == "completed":
            return _snapshot(session, current, run)
        if run is not None and run.status == "scanning" and now - run.started_at < SCAN_LEASE:
            return _snapshot(session, current, run)
        if expected != current:
            raise VersionConflict(current)
        revision = session.get(SourceRevision, current.source_revision_id)
        if revision is None or revision.document_id != document_id:
            raise ContentUnavailable("The current source revision is unavailable.")
        source = keys.decrypt_text(
            ProtectedValue(revision.source_ciphertext, revision.source_key_id)
        )
        from app.db.source_structures import load_csv, load_word
        from app.intake.structure import allows_span

        csv_layout, column_rules = None, []
        if document.csv_delimiter is not None:
            from app.db.column_rules import load_rules

            csv_layout = load_csv(
                session,
                current.source_revision_id,
                keys,
                source,
                document.csv_delimiter,
                document.csv_has_header,
            )
            column_rules = load_rules(session, document, keys)
            layout = None
        else:
            layout = load_word(session, current.source_revision_id, keys, len(source), source)
        categories = {
            FindingCategory(value) for value in document.category_settings.split(",") if value
        }
        region = document.phone_region
        language = document.language
        from app.custom_rules.service import load_snapshot

        custom_rules = load_snapshot(session, document, keys)
        if run is None:
            run = ScanRun(
                id=uuid4(),
                document_id=document_id,
                source_revision_id=current.source_revision_id,
                settings_version=current.settings_version,
                detector_version=DETECTOR_VERSION,
                status="scanning",
                attempt_count=1,
                started_at=now,
            )
            session.add(run)
        else:
            run.status = "scanning"
            run.attempt_count += 1
            run.match_count = None
            run.dropped_suggestions = 0
            run.failure_code = None
            run.started_at = now
            run.finished_at = None
            run.detector_version = DETECTOR_VERSION
        if document.status != DocumentStatus.SCANNING:
            require_transition(DocumentStatus(document.status), DocumentStatus.SCANNING)
        document.status = DocumentStatus.SCANNING
        document.updated_at = now
        session.flush()
        run_id = run.id
        attempt_count = run.attempt_count

    try:
        if csv_layout is not None:
            from app.detection.columns import detect_columns

            detected = detect_columns(
                source, csv_layout, column_rules, categories, region, language, custom_rules
            )
        else:
            detected = detect_suggestions(source, categories, region, language)
            from app.custom_rules.matching import detect_custom

            detected.extend(
                detect_custom(source, [(rule.id, rule.version, rule) for rule in custom_rules])
            )
        unique = {}
        for suggestion in detected:
            unique.setdefault(
                (
                    suggestion.span.start,
                    suggestion.span.end,
                    suggestion.category,
                    suggestion.rule_id,
                ),
                suggestion,
            )
        detected = list(unique.values())
        dropped = sum(
            not allows_span(layout, source, item.span.start, item.span.end) for item in detected
        )
        detected = [
            item for item in detected if allows_span(layout, source, item.span.start, item.span.end)
        ]
        if len(detected) > 1_000:
            raise DetectionLimitError("too_many_suggestions")
        detected.sort(key=lambda item: (item.span.start, item.span.end, item.category.value))
    except DetectionLimitError as exc:
        stale = _finish_failed(
            engine,
            run_id=run_id,
            expected=expected,
            actor_id=actor_id,
            attempt_count=attempt_count,
            code=exc.code,
        )
        if stale is not None:
            raise VersionConflict(stale) from None
        raise ScanExecutionFailed(exc.code) from None
    except Exception:  # noqa: BLE001 — persist an explicit failed run for any detector failure
        stale = _finish_failed(
            engine,
            run_id=run_id,
            expected=expected,
            actor_id=actor_id,
            attempt_count=attempt_count,
            code="detector_error",
        )
        if stale is not None:
            raise VersionConflict(stale) from None
        raise ScanExecutionFailed("detector_error") from None

    try:
        with Session(engine) as session, session.begin():
            document = owned_document(session, document_id, actor_id, datetime.now(UTC), lock=True)
            run = session.get(ScanRun, run_id)
            current = _version(document)
            if run is None:
                raise VersionConflict(current)
            if run.attempt_count != attempt_count:
                if current != expected:
                    raise VersionConflict(current)
                return _snapshot(session, current, run)
            if run.status != "scanning":
                raise VersionConflict(current)
            if current != expected:
                run.status = "superseded"
                run.finished_at = datetime.now(UTC)
                conflict = VersionConflict(current)
            else:
                session.add_all(
                    Finding(
                        id=uuid4(),
                        document_id=document_id,
                        source_revision_id=current.source_revision_id,
                        scan_run_id=run_id,
                        category=item.category.value,
                        origin="automatic",
                        rule_id=item.rule_id,
                        rule_version=item.rule_version,
                        reason=item.reason,
                        date_format=item.date_format
                        or (
                            format_for_span(source, item.span.start, item.span.end, region)
                            if item.category == FindingCategory.DATE
                            else None
                        ),
                        start_offset=item.span.start,
                        end_offset=item.span.end,
                        created_at=datetime.now(UTC),
                    )
                    for item in detected
                )
                run.status = "completed"
                run.match_count = len(detected)
                run.dropped_suggestions = dropped
                run.finished_at = datetime.now(UTC)
                document.decision_version += 1
                require_transition(DocumentStatus(document.status), DocumentStatus.NEEDS_REVIEW)
                document.status = DocumentStatus.NEEDS_REVIEW
                document.updated_at = datetime.now(UTC)
                session.flush()
                record_event(
                    session,
                    workspace_id=document.workspace_id,
                    actor_id=actor_id,
                    document_id=document.id,
                    event_code="scan_completed",
                    now=datetime.now(UTC),
                )
                return _snapshot(session, _version(document), run)
    except (DocumentNotFound, ContentUnavailable):
        _supersede_run(engine, run_id, attempt_count)
        raise
    raise conflict
