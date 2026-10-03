"""Single place for content ownership and workspace administrator checks."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, aliased

from app.contracts import DocumentStatus, WorkspaceRole
from app.db.models import Document, Membership, User, Workspace
from app.db.team_review import ReviewHandoff


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


def review_document_statement(actor_id: UUID):
    """Both parties must remain active; administrator role adds no content access."""
    actor_member, actor_user = aliased(Membership), aliased(User)
    grant = (
        select(ReviewHandoff.document_id)
        .where(
            ReviewHandoff.document_id == Document.id,
            ReviewHandoff.reviewer_id == actor_id,
        )
        .exists()
    )
    return (
        select(Document)
        .join(
            Membership,
            and_(
                Membership.workspace_id == Document.workspace_id,
                Membership.user_id == Document.owner_id,
            ),
        )
        .join(User, User.id == Document.owner_id)
        .join(
            actor_member,
            and_(
                actor_member.workspace_id == Document.workspace_id, actor_member.user_id == actor_id
            ),
        )
        .join(actor_user, actor_user.id == actor_id)
        .where(
            Membership.revoked_at.is_(None),
            User.disabled_at.is_(None),
            actor_member.revoked_at.is_(None),
            actor_user.disabled_at.is_(None),
            or_(Document.owner_id == actor_id, grant),
        )
    )


def review_document_record(session: Session, document_id: UUID, actor_id: UUID, *, lock=False):
    query = review_document_statement(actor_id).where(Document.id == document_id)
    if lock:
        query = query.with_for_update(of=Document)
    document = session.scalar(query)
    if document is None:
        raise DocumentNotFound("Document not found.")
    return document


def review_document(
    session: Session, document_id: UUID, actor_id: UUID, now: datetime, *, lock=False
):
    document = review_document_record(session, document_id, actor_id, lock=lock)
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
        statement = statement.with_for_update(key_share=True)
    workspace = session.scalar(statement.execution_options(populate_existing=True))
    membership = session.get(Membership, (workspace_id, actor_id), populate_existing=True)
    user = session.get(User, actor_id, populate_existing=True)
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
