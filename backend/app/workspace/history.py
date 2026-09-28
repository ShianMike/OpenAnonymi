"""Owner-authorized, content-free history for a saved review."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import DocumentNotFound, owned_document_record
from app.contracts import DocumentStatus
from app.db.models import AuditEvent, SourceRevision
from app.workspace.activity import EVENT_CODES
from app.workspace.documents import _effective_status


@dataclass(frozen=True)
class RevisionHistoryEntry:
    number: int
    created_at: datetime
    is_current: bool


@dataclass(frozen=True)
class DocumentHistory:
    document_id: UUID
    status: DocumentStatus
    created_at: datetime
    expires_at: datetime
    deleted_at: datetime | None
    revisions: list[RevisionHistoryEntry]
    revision_total: int
    events: list[tuple[str, str, datetime]]
    event_total: int


def load_document_history(
    engine: Engine, *, workspace_id: UUID, document_id: UUID, actor_id: UUID, now: datetime
) -> DocumentHistory:
    with Session(engine) as session:
        document = owned_document_record(session, document_id, actor_id)
        if document.workspace_id != workspace_id:
            raise DocumentNotFound("Document not found.")
        revision_total = (
            session.scalar(
                select(func.count(SourceRevision.id)).where(
                    SourceRevision.document_id == document_id
                )
            )
            or 0
        )
        revisions = session.execute(
            select(SourceRevision.revision_number, SourceRevision.created_at, SourceRevision.id)
            .where(SourceRevision.document_id == document_id)
            .order_by(SourceRevision.revision_number.desc())
            .limit(100)
        ).all()
        event_total = (
            session.scalar(
                select(func.count(AuditEvent.id)).where(
                    AuditEvent.workspace_id == workspace_id,
                    AuditEvent.document_id == document_id,
                    AuditEvent.event_code.in_(EVENT_CODES),
                )
            )
            or 0
        )
        events = session.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.workspace_id == workspace_id,
                AuditEvent.document_id == document_id,
                AuditEvent.event_code.in_(EVENT_CODES),
            )
            .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
            .limit(100)
        ).all()
        return DocumentHistory(
            document_id=document.id,
            status=_effective_status(document, now),
            created_at=document.created_at,
            expires_at=document.expires_at,
            deleted_at=document.deleted_at,
            revisions=[
                RevisionHistoryEntry(
                    number=number,
                    created_at=created_at,
                    is_current=revision_id == document.current_revision_id,
                )
                for number, created_at, revision_id in revisions
            ],
            revision_total=revision_total,
            events=[(event.event_code, event.outcome, event.occurred_at) for event in events],
            event_total=event_total,
        )
