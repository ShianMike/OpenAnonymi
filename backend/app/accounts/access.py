"""Single place for content ownership and workspace administrator checks."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.contracts import DocumentStatus, WorkspaceRole
from app.db.models import Document, Membership, User, Workspace


class DocumentNotFound(LookupError):
    """Also used for inaccessible documents, to avoid revealing existence."""


class ContentUnavailable(RuntimeError):
    pass


class WorkspaceAccessDenied(RuntimeError):
    pass


def owned_document_record(
    session: Session, document_id: UUID, actor_id: UUID, *, lock: bool = False
) -> Document:
    """Authorize an owner without assuming protected content is still available."""
    statement = (
        select(Document)
        .join(
            Membership,
            and_(
                Membership.workspace_id == Document.workspace_id,
                Membership.user_id == Document.owner_id,
            ),
        )
        .join(User, User.id == Membership.user_id)
        .where(
            Document.id == document_id,
            Document.owner_id == actor_id,
            Membership.revoked_at.is_(None),
            User.disabled_at.is_(None),
        )
    )
    if lock:
        statement = statement.with_for_update(of=Document)
    document = session.scalar(statement)
    if document is None:
        raise DocumentNotFound("Document not found.")
    return document


def owned_document(
    session: Session, document_id: UUID, actor_id: UUID, now: datetime, *, lock: bool = False
) -> Document:
    document = owned_document_record(session, document_id, actor_id, lock=lock)
    if (
        document.deleted_at is not None
        or document.status in (DocumentStatus.EXPIRED, DocumentStatus.DELETED)
        or document.expires_at <= now
    ):
        raise ContentUnavailable("This document has expired or was deleted.")
    return document


def require_administrator(
    session: Session, *, workspace_id: UUID, actor_id: UUID, lock: bool = False
) -> Workspace:
    statement = select(Workspace).where(Workspace.id == workspace_id)
    if lock:
        statement = statement.with_for_update()
    workspace = session.scalar(statement)
    membership = session.get(Membership, (workspace_id, actor_id))
    user = session.get(User, actor_id)
    if (
        workspace is None
        or membership is None
        or membership.role != WorkspaceRole.ADMINISTRATOR
        or membership.revoked_at is not None
        or user is None
        or user.disabled_at is not None
    ):
        raise WorkspaceAccessDenied("Workspace not found.")
    return workspace


def active_workspace(session: Session, workspace_id: UUID, user_id: UUID) -> Workspace:
    workspace = session.scalar(
        select(Workspace)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .join(User, User.id == Membership.user_id)
        .where(
            Workspace.id == workspace_id,
            Membership.user_id == user_id,
            Membership.revoked_at.is_(None),
            User.disabled_at.is_(None),
        )
    )
    if workspace is None:
        raise WorkspaceAccessDenied("Workspace not found.")
    return workspace
