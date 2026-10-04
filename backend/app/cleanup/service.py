"""Immediate access revocation followed by repeatable protected-content removal."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, delete, exists, or_, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import owned_document_record
from app.contracts import DocumentStatus
from app.db.batches import ScanJob
from app.db.column_rules import DocumentColumnRules
from app.db.custom_rules import DocumentRuleSnapshot
from app.db.durable import AttemptEvent, ReviewUndoEntry
from app.db.email_verification import EmailVerification, PendingRegistration
from app.db.models import AuditEvent, Document, LabelCounter, SourceRevision, Workspace
from app.db.models import Session as StoredSession
from app.db.recovery import RecoverySnapshot
from app.db.replacement_secrets import DocumentReplacementSecret
from app.db.second_factor import AuthChallenge, UserSecondFactor
from app.db.team_review import ReviewHandoff
from app.workspace.activity import record_event


@dataclass(frozen=True)
class CleanupResult:
    documents_purged: int
    activity_removed: int
    expired_rows_removed: int = 0


def unavailable_content(now: datetime):
    return and_(
        or_(
            Document.deleted_at.is_not(None),
            Document.expires_at <= now,
            Document.status.in_([DocumentStatus.EXPIRED, DocumentStatus.DELETED]),
        ),
        or_(Document.current_revision_id.is_not(None), Document.title_ciphertext.is_not(None)),
    )


def purge_document(session: Session, document: Document, now: datetime) -> bool:
    """Recheck under the same row lock used by edits and retention changes."""
    document = session.scalar(
        select(Document)
        .where(Document.id == document.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if document is None or (
        document.deleted_at is None
        and document.status not in (DocumentStatus.EXPIRED, DocumentStatus.DELETED)
        and document.expires_at > now
    ):
        return False
    if document.current_revision_id is None and document.title_ciphertext is None:
        return False
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
    session.execute(delete(ReviewUndoEntry).where(ReviewUndoEntry.document_id == document.id))
    session.execute(delete(ScanJob).where(ScanJob.document_id == document.id))
    session.execute(
        delete(DocumentColumnRules).where(DocumentColumnRules.document_id == document.id)
    )
    session.execute(
        delete(DocumentReplacementSecret).where(
            DocumentReplacementSecret.document_id == document.id
        )
    )
    document.current_revision_id = None
    document.title_ciphertext = None
    document.title_key_id = None
    session.flush()
    # Revision-owned findings, decisions, scans, completions and encrypted layouts cascade here.
    session.execute(delete(SourceRevision).where(SourceRevision.document_id == document.id))
    session.execute(delete(LabelCounter).where(LabelCounter.document_id == document.id))
    session.execute(delete(RecoverySnapshot).where(RecoverySnapshot.document_id == document.id))
    session.execute(
        delete(DocumentRuleSnapshot).where(DocumentRuleSnapshot.document_id == document.id)
    )
    return True


def expired_row_predicates(now: datetime):
    return (
        (RecoverySnapshot, RecoverySnapshot.expires_at <= now),
        (PendingRegistration, PendingRegistration.expires_at <= now),
        (EmailVerification, EmailVerification.expires_at <= now),
        (
            UserSecondFactor,
            and_(
                UserSecondFactor.status == "pending",
                UserSecondFactor.created_at <= now - timedelta(minutes=10),
            ),
        ),
        (AuthChallenge, AuthChallenge.expires_at <= now - timedelta(hours=1)),
        (
            StoredSession,
            or_(
                StoredSession.expires_at <= now - timedelta(hours=24),
                StoredSession.revoked_at <= now - timedelta(hours=24),
            ),
        ),
        (AttemptEvent, AttemptEvent.attempted_at <= now - timedelta(days=1)),
        (ReviewUndoEntry, ReviewUndoEntry.created_at <= now - timedelta(hours=1)),
    )


def expired_activity(now: datetime):
    # One database predicate replaces a workspace-by-workspace delete loop.
    return exists(
        select(Workspace.id).where(
            Workspace.id == AuditEvent.workspace_id,
            AuditEvent.occurred_at
            < now - Workspace.activity_retention_days * text("INTERVAL '1 day'"),
        )
    )


def cleanup_remaining(session: Session, now: datetime) -> bool:
    from app.cleanup.batches import removable_batches

    if session.scalar(select(exists().where(removable_batches(now)))):
        return True
    if session.scalar(select(exists().where(unavailable_content(now)))):
        return True
    for model, predicate in expired_row_predicates(now):
        if session.scalar(select(exists().where(predicate))):
            return True
    return bool(session.scalar(select(select(AuditEvent.id).where(expired_activity(now)).exists())))


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
    engine: Engine, *, now: datetime, batch_size: int = 100, statement_timeout_ms: int | None = None
) -> CleanupResult:
    """Remove content for deleted/expired documents; safe to retry after interruption."""
    if batch_size < 1 or batch_size > 1000:
        raise ValueError("Choose a cleanup batch size from 1 to 1000.")
    with Session(engine) as session, session.begin():
        if statement_timeout_ms is not None:
            session.execute(
                text("SELECT set_config('statement_timeout', :timeout, true)"),
                {"timeout": str(max(1, statement_timeout_ms))},
            )
            session.execute(
                text("SELECT set_config('transaction_timeout', :timeout, true)"),
                {"timeout": str(max(1, statement_timeout_ms))},
            )
            session.execute(text("SET LOCAL lock_timeout = '500ms'"))
        documents = session.scalars(
            select(Document)
            .where(unavailable_content(now))
            .order_by(Document.expires_at, Document.id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        ).all()
        documents_purged = sum(purge_document(session, document, now) for document in documents)
        expired_rows_removed = 0
        from app.cleanup.batches import purge_empty_batches

        expired_rows_removed += purge_empty_batches(session, now, batch_size)
        for model, predicate in expired_row_predicates(now):
            key = model.__mapper__.primary_key[0]
            candidates = (
                select(key)
                .where(predicate)
                .order_by(key)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
            result = session.execute(delete(model).where(key.in_(candidates)))
            expired_rows_removed += result.rowcount
        candidates = (
            select(AuditEvent.id)
            .where(expired_activity(now))
            .order_by(AuditEvent.id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        activity_removed = session.execute(
            delete(AuditEvent).where(AuditEvent.id.in_(candidates))
        ).rowcount
        return CleanupResult(documents_purged, activity_removed, expired_rows_removed)
