"""Owner-scoped document index and content-free workspace counts."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import active_workspace, review_document_statement
from app.contracts import DocumentStatus, WorkspaceRole
from app.db.crypto import KeyRing, ProtectedValue
from app.db.models import Decision, Document, Finding, Membership


@dataclass(frozen=True)
class DocumentIndexEntry:
    id: UUID
    is_owner: bool
    title: str | None
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    current_revision_id: UUID | None
    finding_count: int
    decided_count: int


@dataclass(frozen=True)
class OverviewCounts:
    as_of: datetime
    own_total: int
    own_created_last_30_days: int
    own_by_status: dict[str, int]
    workspace_total: int | None


def _effective_status(document: Document, now: datetime) -> DocumentStatus:
    if document.deleted_at is not None or document.status == DocumentStatus.DELETED:
        return DocumentStatus.DELETED
    if document.expires_at <= now or document.status == DocumentStatus.EXPIRED:
        return DocumentStatus.EXPIRED
    return DocumentStatus(document.status)


def list_documents(
    engine: Engine,
    *,
    workspace_id: UUID,
    actor_id: UUID,
    keys: KeyRing,
    now: datetime,
) -> list[DocumentIndexEntry]:
    with Session(engine) as session:
        active_workspace(session, workspace_id, actor_id)
        documents = session.scalars(
            review_document_statement(actor_id)
            .where(
                Document.workspace_id == workspace_id,
                Document.deleted_at.is_(None),
            )
            .order_by(Document.created_at.desc(), Document.id.desc())
        ).all()
        if not documents:
            return []
        finding_rows = session.execute(
            select(
                Finding.document_id,
                func.count(Finding.id),
                func.count(Decision.finding_id),
            )
            .join(
                Document,
                and_(
                    Document.id == Finding.document_id,
                    Document.current_revision_id == Finding.source_revision_id,
                ),
            )
            .outerjoin(Decision, Decision.finding_id == Finding.id)
            .where(
                Finding.document_id.in_([document.id for document in documents]),
                Finding.removed_at.is_(None),
            )
            .group_by(Finding.document_id)
        ).all()
        progress = {
            document_id: (finding_count, decided_count)
            for document_id, finding_count, decided_count in finding_rows
        }
        result = []
        for document in documents:
            status = _effective_status(document, now)
            title = None
            if (
                status not in (DocumentStatus.EXPIRED, DocumentStatus.DELETED)
                and document.title_ciphertext is not None
                and document.title_key_id is not None
            ):
                title = keys.decrypt_text(
                    ProtectedValue(document.title_ciphertext, document.title_key_id)
                )
            finding_count, decided_count = progress.get(document.id, (0, 0))
            result.append(
                DocumentIndexEntry(
                    id=document.id,
                    is_owner=document.owner_id == actor_id,
                    title=title,
                    status=status,
                    created_at=document.created_at,
                    updated_at=document.updated_at,
                    expires_at=document.expires_at,
                    current_revision_id=document.current_revision_id,
                    finding_count=finding_count,
                    decided_count=decided_count,
                )
            )
        return result


def load_overview(
    engine: Engine, *, workspace_id: UUID, actor_id: UUID, now: datetime
) -> OverviewCounts:
    with Session(engine) as session:
        active_workspace(session, workspace_id, actor_id)
        membership = session.get(Membership, (workspace_id, actor_id))
        own = session.scalars(
            select(Document).where(
                Document.workspace_id == workspace_id,
                Document.owner_id == actor_id,
                Document.deleted_at.is_(None),
            )
        ).all()
        by_status = Counter(_effective_status(document, now).value for document in own)
        workspace_total = None
        if membership.role == WorkspaceRole.ADMINISTRATOR:
            workspace_total = session.scalar(
                select(func.count(Document.id)).where(
                    Document.workspace_id == workspace_id,
                    Document.deleted_at.is_(None),
                )
            )
        return OverviewCounts(
            as_of=now,
            own_total=len(own),
            own_created_last_30_days=sum(
                document.created_at >= now - timedelta(days=30) for document in own
            ),
            own_by_status=dict(by_status),
            workspace_total=workspace_total,
        )
