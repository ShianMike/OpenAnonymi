"""Current grants, retention and title state for prepared index/search responses."""

from datetime import UTC, datetime

from sqlalchemy import and_

from app.accounts.access import (
    ContentUnavailable,
    DocumentNotFound,
    active_workspace,
    review_document_statement,
)
from app.contracts import DocumentStatus
from app.db.crypto import ProtectedValue
from app.db.document_preferences import DocumentPreference
from app.db.models import Document, Workspace
from app.errors import ApiError


def _rows(session, actor_id, ids):
    if not ids:
        return {}
    statement = (
        review_document_statement(actor_id)
        .join(Workspace, Workspace.id == Document.workspace_id)
        .outerjoin(
            DocumentPreference,
            and_(
                DocumentPreference.document_id == Document.id,
                DocumentPreference.actor_id == actor_id,
            ),
        )
        .with_only_columns(
            Document.id,
            Document.workspace_id,
            Document.owner_id,
            Document.status,
            Document.created_at,
            Document.updated_at,
            Document.expires_at,
            Document.current_revision_id,
            Document.title_ciphertext,
            Document.title_key_id,
            Workspace.name,
            DocumentPreference.favorite,
            DocumentPreference.pinned,
        )
        .where(Document.id.in_(ids), Document.deleted_at.is_(None))
    )
    return {row.id: row for row in session.execute(statement).all()}


def validate_title_view(session, actor_id, view, keys, *, workspace_id=None, index=False):
    """Decrypt only returned titles, then requery scalar grants/state after that work."""
    items = view if index else view.items
    cursor = None if index else view.next_cursor
    ids = {item.id for item in items}
    if cursor is not None:
        ids.add(cursor.id)
    if workspace_id is not None:
        active_workspace(session, workspace_id, actor_id)
    rows = _rows(session, actor_id, ids)
    if set(rows) != ids:
        raise DocumentNotFound("Document not found.")
    for item in items:
        row = rows[item.id]
        expired = row.expires_at <= datetime.now(UTC) or row.status == DocumentStatus.EXPIRED
        if expired and (not index or item.title is not None):
            raise ContentUnavailable("Document content is unavailable.")
        title = (
            keys.decrypt_text(ProtectedValue(row.title_ciphertext, row.title_key_id))
            if not expired and row.title_ciphertext is not None and row.title_key_id is not None
            else None
        )
        status = DocumentStatus.EXPIRED if expired else DocumentStatus(row.status)
        same = (
            item.title == title
            and item.status == status
            and item.is_owner == (row.owner_id == actor_id)
            and item.favorite == (bool(row.favorite) and not expired)
            and item.pinned == (bool(row.pinned) and not expired)
        )
        if index:
            same = same and (
                item.created_at == row.created_at
                and item.updated_at == row.updated_at
                and item.expires_at == row.expires_at
                and item.current_revision_id == row.current_revision_id
                and row.workspace_id == workspace_id
            )
        else:
            same = same and (
                item.workspace_id == row.workspace_id and item.workspace_name == row.name
            )
        if not same:
            raise ApiError(409, "documents_changed", "Documents changed. Reload before continuing.")
    if cursor is not None and rows[cursor.id].created_at != cursor.created_at:
        raise ApiError(409, "documents_changed", "Documents changed. Search again.")
    # The extra title decryption above must not turn an earlier grant into the
    # final authorization. Keep these bounded scalar queries after that work.
    latest = _rows(session, actor_id, ids)
    if set(latest) != ids:
        raise DocumentNotFound("Document not found.")
    if latest != rows:
        raise ApiError(409, "documents_changed", "Documents changed. Reload before continuing.")
    now = datetime.now(UTC)
    private_ids = {item.id for item in items if item.title is not None}
    if any(
        (row.expires_at <= now or row.status == DocumentStatus.EXPIRED)
        and (not index or row.id in private_ids)
        for row in latest.values()
    ):
        raise ContentUnavailable("Document content is unavailable.")
    if workspace_id is not None:
        active_workspace(session, workspace_id, actor_id)
