"""Atomic authorized output snapshots and content-free export events."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from time import perf_counter
from uuid import UUID

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import owned_document
from app.contracts import DocumentStatus, VersionRef
from app.db.crypto import KeyRing
from app.db.models import Document, ExportEvent, ReviewCompletion
from app.db.repository import VersionConflict
from app.groups.service import _snapshot, _version
from app.lifecycle import require_transition
from app.reviews.service import CompletionRejected, current_completion
from app.transformations.service import build_current_preview
from app.workspace.activity import record_event


class ExportConflict(ValueError):
    pass


class OutputTooLarge(ValueError):
    pass


@dataclass(frozen=True)
class AuthorizedOutput:
    version: VersionRef
    completion_id: UUID
    text: str
    filename: str
    confirmed_at: datetime | None = None
    layout: dict | None = field(default=None, repr=False)
    csv_cells: tuple[tuple[str, ...], ...] | None = field(default=None, repr=False)
    csv_delimiter: str | None = None
    prefixed_cells: int = 0
    report: dict | None = field(default=None, repr=False)


def _current_output(
    session: Session,
    document: Document,
    expected: VersionRef,
    keys: KeyRing,
    *,
    format: str = "txt",
) -> tuple[AuthorizedOutput, ReviewCompletion]:
    version = _version(document)
    if version != expected:
        raise VersionConflict(version)
    completion = current_completion(session, document)
    from app.team_review.service import require_second_approval

    require_second_approval(session, document)
    findings = _snapshot(session, version) if format == "report" else None
    preview = build_current_preview(session, document=document, keys=keys, findings=findings)
    if preview.status != "complete" or preview.text is None:
        raise CompletionRejected(
            "review_not_completed", "The completed review no longer has a valid output."
        )
    layout = None
    if format == "csv" and preview.csv_cells is None:
        raise ExportConflict("CSV output requires an imported CSV document.")
    if format == "docx" and document.csv_delimiter is None:
        from app.db.models import SourceRevision
        from app.db.source_structures import load_word
        from app.intake.structure import output_layout

        revision = session.get(SourceRevision, expected.source_revision_id)
        layout = output_layout(
            load_word(session, revision.id, keys, revision.code_points),
            preview.mappings,
            preview.text,
        )
    return (
        AuthorizedOutput(
            version=version,
            completion_id=completion.id,
            text=preview.text,
            filename=(
                f"redaction-report-{document.id}.json"
                if format == "report"
                else f"reviewed-{document.id}.{format}"
            ),
            confirmed_at=completion.confirmed_at,
            layout=layout,
            csv_cells=preview.csv_cells,
            csv_delimiter=document.csv_delimiter,
            report=_report(version, completion.confirmed_at, findings, preview)
            if findings
            else None,
        ),
        completion,
    )


def _report(version, confirmed_at, findings, preview):
    from app.exports.report import build_report

    return build_report(version, confirmed_at, findings, preview)


def _require_current_output_access(session, document, actor_id, now, reauthorize):
    if reauthorize is not None:
        reauthorize()
        now = max(now, datetime.now(UTC))
    owned_document(session, document.id, actor_id, now, lock=True)
    from app.team_review.service import require_second_approval

    require_second_approval(session, document)


def prepare_copy(
    engine: Engine,
    *,
    document_id: UUID,
    actor_id: UUID,
    expected: VersionRef,
    keys: KeyRing,
    now: datetime,
    reauthorize: Callable[[], object] | None = None,
) -> AuthorizedOutput:
    started = perf_counter()
    with Session(engine) as session, session.begin():
        document = owned_document(session, document_id, actor_id, now, lock=True)
        if reauthorize is not None:
            reauthorize()
        output, _completion = _current_output(session, document, expected, keys)
        finished_at = now + timedelta(seconds=max(0, perf_counter() - started))
        _require_current_output_access(session, document, actor_id, finished_at, reauthorize)
        return output


def _record_event(
    session: Session,
    *,
    document: Document,
    completion: ReviewCompletion,
    actor_id: UUID,
    event_id: UUID,
    format: str,
    now: datetime,
) -> ExportEvent:
    existing = session.get(ExportEvent, event_id)
    if existing is not None:
        if (
            existing.document_id != document.id
            or existing.completion_id != completion.id
            or existing.actor_id != actor_id
            or existing.format != format
        ):
            raise ExportConflict("This output attempt ID belongs to another operation.")
        return existing
    event = ExportEvent(
        id=event_id,
        document_id=document.id,
        completion_id=completion.id,
        actor_id=actor_id,
        format=format,
        occurred_at=now,
    )
    session.add(event)
    record_event(
        session,
        workspace_id=document.workspace_id,
        actor_id=actor_id,
        document_id=document.id,
        event_code="output_copied" if format == "copy" else "output_generated",
        now=now,
    )
    if document.status == DocumentStatus.READY:
        require_transition(DocumentStatus(document.status), DocumentStatus.EXPORTED)
        document.status = DocumentStatus.EXPORTED
        document.updated_at = now
    session.flush()
    return event


def record_copy_success(
    engine: Engine,
    *,
    document_id: UUID,
    actor_id: UUID,
    expected: VersionRef,
    completion_id: UUID,
    event_id: UUID,
    now: datetime,
    reauthorize: Callable[[], object] | None = None,
) -> datetime:
    started = perf_counter()
    with Session(engine) as session, session.begin():
        document = owned_document(session, document_id, actor_id, now, lock=True)
        if reauthorize is not None:
            reauthorize()
        version = _version(document)
        if version != expected:
            raise VersionConflict(version)
        completion = current_completion(session, document)
        from app.team_review.service import require_second_approval

        require_second_approval(session, document)
        if completion.id != completion_id:
            raise ExportConflict("The confirmed review changed before copy was recorded.")
        event = _record_event(
            session,
            document=document,
            completion=completion,
            actor_id=actor_id,
            event_id=event_id,
            format="copy",
            now=now,
        )
        finished_at = now + timedelta(seconds=max(0, perf_counter() - started))
        _require_current_output_access(session, document, actor_id, finished_at, reauthorize)
        return event.occurred_at


def generate_output(
    engine: Engine,
    *,
    document_id: UUID,
    actor_id: UUID,
    expected: VersionRef,
    event_id: UUID,
    keys: KeyRing,
    now: datetime,
    format: str = "txt",
    variant: str = "spreadsheet_safe",
    maximum_bytes: int | None = None,
    reauthorize: Callable[[], object] | None = None,
) -> tuple[bytes, AuthorizedOutput]:
    started = perf_counter()
    if format not in {"txt", "docx", "csv", "pdf", "report"}:
        raise ExportConflict("Choose a supported reviewed output format.")
    with Session(engine) as session, session.begin():
        document = owned_document(session, document_id, actor_id, now, lock=True)
        if reauthorize is not None:
            reauthorize()
        output, completion = _current_output(session, document, expected, keys, format=format)
        if format == "pdf":
            from app.exports.pdf import generate_pdf

            payload = generate_pdf(output.text, now)
        elif format == "report":
            from app.exports.report import generate_report

            payload = generate_report(output.report, now)
        elif format == "docx":
            from app.exports.docx import generate_word

            payload = generate_word(output.text, output.layout, now)
        elif format == "csv":
            from dataclasses import replace

            from app.exports.csv_export import generate_csv

            csv = generate_csv(output.csv_cells, output.csv_delimiter, variant)
            payload = csv.payload
            output = replace(output, prefixed_cells=csv.prefixed_cells)
        else:
            payload = output.text.encode("utf-8")
        if maximum_bytes is not None and len(payload) > maximum_bytes:
            raise OutputTooLarge("Reviewed outputs exceed the archive size limit.")
        # Rendering may take time. Recheck access/expiry and fresh policy before release.
        finished_at = now + timedelta(seconds=max(0, perf_counter() - started))
        _require_current_output_access(session, document, actor_id, finished_at, reauthorize)
        _record_event(
            session,
            document=document,
            completion=completion,
            actor_id=actor_id,
            event_id=event_id,
            format=format,
            now=finished_at,
        )
        _require_current_output_access(session, document, actor_id, finished_at, reauthorize)
        return payload, output


def generate_txt(engine: Engine, **kwargs):
    return generate_output(engine, **kwargs, format="txt")
