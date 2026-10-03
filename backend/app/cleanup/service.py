"""Immediate access revocation followed by repeatable protected-content removal."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import owned_document_record
from app.contracts import DocumentStatus
from app.db.custom_rules import DocumentRuleSnapshot
from app.db.durable import AttemptEvent, ReviewUndoEntry
from app.db.email_verification import EmailVerification, PendingRegistration
from app.db.models import AuditEvent, Document, LabelCounter, SourceRevision, Workspace
from app.db.recovery import RecoverySnapshot
from app.db.team_review import ReviewHandoff
from app.workspace.activity import record_event


@dataclass(frozen=True)
class CleanupResult:
    documents_purged: int
    activity_removed: int


def mark_document_deleted(
    engine: Engine, *, document_id: UUID, actor_id: UUID, now: datetime
) -> None:
    with Session(engine) as session, session.begin():
        document = owned_document_record(session, document_id, actor_id, lock=True)
        if document.deleted_at is not None:
            return
        document.deleted_at = now
        document.status = DocumentStatus.DELETED
        document.updated_at = now
        record_event(
            session,
            workspace_id=document.workspace_id,
            actor_id=actor_id,
            document_id=document.id,
            event_code="document_deleted",
            now=now,
        )


def purge_unavailable_content(
    engine: Engine, *, now: datetime, batch_size: int = 100
) -> CleanupResult:
    """Remove content for deleted/expired documents; safe to retry after interruption."""
    if batch_size < 1 or batch_size > 1000:
        raise ValueError("Choose a cleanup batch size from 1 to 1000.")
    with Session(engine) as session, session.begin():
        documents = session.scalars(
            select(Document)
            .where(
                or_(
                    Document.deleted_at.is_not(None),
                    Document.expires_at <= now,
                    Document.status.in_([DocumentStatus.EXPIRED, DocumentStatus.DELETED]),
                ),
                or_(
                    Document.current_revision_id.is_not(None),
                    Document.title_ciphertext.is_not(None),
                ),
            )
            .order_by(Document.expires_at, Document.id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        ).all()
        for document in documents:
            if document.deleted_at is None and document.status != DocumentStatus.EXPIRED:
                document.status = DocumentStatus.EXPIRED
                document.updated_at = now
                record_event(
                    session,
                    workspace_id=document.workspace_id,
                    actor_id=None,
                    document_id=document.id,
                    event_code="document_expired",
                    now=now,
                )
            session.execute(delete(ReviewHandoff).where(ReviewHandoff.document_id == document.id))
            session.execute(
                delete(ReviewUndoEntry).where(ReviewUndoEntry.document_id == document.id)
            )
            document.current_revision_id = None
            document.title_ciphertext = None
            document.title_key_id = None
            session.flush()
            session.execute(delete(SourceRevision).where(SourceRevision.document_id == document.id))
            session.execute(delete(LabelCounter).where(LabelCounter.document_id == document.id))
            session.execute(
                delete(RecoverySnapshot).where(RecoverySnapshot.document_id == document.id)
            )
            session.execute(
                delete(DocumentRuleSnapshot).where(DocumentRuleSnapshot.document_id == document.id)
            )

        session.execute(delete(RecoverySnapshot).where(RecoverySnapshot.expires_at <= now))
        session.execute(delete(PendingRegistration).where(PendingRegistration.expires_at <= now))
        session.execute(delete(EmailVerification).where(EmailVerification.expires_at <= now))
        session.execute(
            delete(AttemptEvent).where(AttemptEvent.attempted_at <= now - timedelta(days=1))
        )
        session.execute(
            delete(ReviewUndoEntry).where(ReviewUndoEntry.created_at <= now - timedelta(hours=1))
        )

        activity_removed = 0
        for workspace in session.scalars(select(Workspace)).all():
            result = session.execute(
                delete(AuditEvent).where(
                    AuditEvent.workspace_id == workspace.id,
                    AuditEvent.occurred_at
                    < now - timedelta(days=workspace.activity_retention_days),
                )
            )
            activity_removed += result.rowcount
        return CleanupResult(len(documents), activity_removed)
