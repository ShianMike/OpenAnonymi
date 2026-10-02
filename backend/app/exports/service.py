"""Atomic authorized output snapshots and content-free export events."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import owned_document
from app.contracts import DocumentStatus, VersionRef
from app.db.crypto import KeyRing
from app.db.models import Document, ExportEvent, ReviewCompletion
from app.db.repository import VersionConflict
from app.groups.service import _version
from app.lifecycle import require_transition
from app.reviews.service import CompletionRejected, current_completion
from app.transformations.service import build_current_preview
from app.workspace.activity import record_event


class ExportConflict(ValueError):
    pass


@dataclass(frozen=True)
class AuthorizedOutput:
    version: VersionRef
    completion_id: UUID
    text: str
    filename: str


def _current_output(
    session: Session, document: Document, expected: VersionRef, keys: KeyRing
) -> tuple[AuthorizedOutput, ReviewCompletion]:
    version = _version(document)
    if version != expected:
        raise VersionConflict(version)
    completion = current_completion(session, document)
    from app.team_review.service import require_second_approval

    require_second_approval(session, document)
    preview = build_current_preview(session, document=document, keys=keys)
    if preview.status != "complete" or preview.text is None:
        raise CompletionRejected(
            "review_not_completed", "The completed review no longer has a valid output."
        )
    return (
        AuthorizedOutput(
            version=version,
            completion_id=completion.id,
            text=preview.text,
            filename=f"reviewed-{document.id}.txt",
        ),
        completion,
    )


def prepare_copy(
    engine: Engine,
    *,
    document_id: UUID,
    actor_id: UUID,
    expected: VersionRef,
    keys: KeyRing,
    now: datetime,
) -> AuthorizedOutput:
    with Session(engine) as session, session.begin():
        document = owned_document(session, document_id, actor_id, now, lock=True)
        output, _completion = _current_output(session, document, expected, keys)
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
) -> datetime:
    with Session(engine) as session, session.begin():
        document = owned_document(session, document_id, actor_id, now, lock=True)
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
        return event.occurred_at


def generate_txt(
    engine: Engine,
    *,
    document_id: UUID,
    actor_id: UUID,
    expected: VersionRef,
    event_id: UUID,
    keys: KeyRing,
    now: datetime,
) -> tuple[bytes, AuthorizedOutput]:
    with Session(engine) as session, session.begin():
        document = owned_document(session, document_id, actor_id, now, lock=True)
        output, completion = _current_output(session, document, expected, keys)
        payload = output.text.encode("utf-8")
        _record_event(
            session,
            document=document,
            completion=completion,
            actor_id=actor_id,
            event_id=event_id,
            format="txt",
            now=now,
        )
        return payload, output
