"""Owner-scoped document index and content-free workspace counts."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import active_workspace, review_document_statement
from app.contracts import DocumentStatus, WorkspaceRole
from app.db.crypto import KeyRing, ProtectedValue
from app.db.document_preferences import DocumentPreference
from app.db.models import Decision, Document, Finding, Membership
from app.workspace.analytics import OverviewAnalytics, load_analytics


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
    favorite: bool = False
    pinned: bool = False


@dataclass(frozen=True)
class OverviewCounts:
    as_of: datetime
    own_total: int
    own_created_last_30_days: int
    own_by_status: dict[str, int]
    workspace_total: int | None
    analytics: OverviewAnalytics


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
        # Re-query scalar columns after decryption. An ORM-cached grant or document
        # must not keep a title visible after access or retention changes.
        active_workspace(session, workspace_id, actor_id)
        latest = {
            row.id: row
            for row in session.execute(
                review_document_statement(actor_id)
                .with_only_columns(
                    Document.id, Document.expires_at, Document.status, Document.current_revision_id
                )
                .where(Document.id.in_([item.id for item in result]), Document.deleted_at.is_(None))
            ).all()
        }
        flags = {
            flag.document_id: flag
            for flag in session.scalars(
                select(DocumentPreference).where(
                    DocumentPreference.actor_id == actor_id,
                    DocumentPreference.document_id.in_(latest),
                )
            ).all()
        }
        late_now = max(now, datetime.now(UTC))
        checked = []
        for item in result:
            row = latest.get(item.id)
            if row is None:
                continue
            expired = row.expires_at <= late_now or row.status == DocumentStatus.EXPIRED
            flag = flags.get(item.id)
            checked.append(
                replace(
                    item,
                    title=None if expired else item.title,
                    status=DocumentStatus.EXPIRED if expired else DocumentStatus(row.status),
                    expires_at=row.expires_at,
                    current_revision_id=row.current_revision_id,
                    favorite=bool(flag and flag.favorite and not expired),
                    pinned=bool(flag and flag.pinned and not expired),
                )
            )
        return checked


def load_overview(
    engine: Engine, *, workspace_id: UUID, actor_id: UUID, now: datetime
) -> OverviewCounts:
    with Session(engine) as session:
        active_workspace(session, workspace_id, actor_id)
        own_scope = (
            Document.workspace_id == workspace_id,
            Document.owner_id == actor_id,
            Document.deleted_at.is_(None),
        )
        status = case(
            (Document.status == DocumentStatus.DELETED, DocumentStatus.DELETED.value),
            (
                or_(Document.expires_at <= now, Document.status == DocumentStatus.EXPIRED),
                DocumentStatus.EXPIRED.value,
            ),
            else_=Document.status,
        )
        by_status = dict(
            session.execute(
                select(status, func.count(Document.id)).where(*own_scope).group_by(status)
            ).all()
        )
        created_recently = session.scalar(
            select(func.count(Document.id)).where(
                *own_scope,
                Document.created_at >= now - timedelta(days=30),
                Document.created_at <= now,
            )
        )
        analytics = load_analytics(session, workspace_id=workspace_id, actor_id=actor_id, now=now)
        # Counts reveal workspace activity too. Refresh access and role after all
        # aggregate work instead of trusting an ORM-cached administrator grant.
        active_workspace(session, workspace_id, actor_id)
        role = session.scalar(
            select(Membership.role).where(
                Membership.workspace_id == workspace_id,
                Membership.user_id == actor_id,
                Membership.revoked_at.is_(None),
            )
        )
        workspace_total = None
        if role == WorkspaceRole.ADMINISTRATOR:
            workspace_total = session.scalar(
                select(func.count(Document.id)).where(
                    Document.workspace_id == workspace_id,
                    Document.deleted_at.is_(None),
                )
            )
        active_workspace(session, workspace_id, actor_id)
        latest_role = session.scalar(
            select(Membership.role).where(
                Membership.workspace_id == workspace_id, Membership.user_id == actor_id
            )
        )
        if latest_role != WorkspaceRole.ADMINISTRATOR:
            workspace_total = None
        return OverviewCounts(
            as_of=now,
            own_total=sum(by_status.values()),
            own_created_last_30_days=created_recently,
            own_by_status=by_status,
            workspace_total=workspace_total,
            analytics=analytics,
        )
