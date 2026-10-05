"""Bounded title search and personal flags, using live owner/reviewer authorization."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, model_validator
from sqlalchemy import and_, delete, tuple_
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import (
    active_workspace,
    owned_document_record,
    refresh_document_access,
    review_document,
    review_document_statement,
)
from app.cleanup.service import purge_document
from app.contracts import DocumentStatus
from app.db.crypto import KeyRing, ProtectedValue
from app.db.document_preferences import DocumentPreference
from app.db.models import Document, Workspace
from app.workspace.activity import record_event

SEARCH_CANDIDATES = 500
BulkAction = Literal["favorite", "unfavorite", "pin", "unpin", "delete"]


class SearchCursor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    created_at: AwareDatetime
    id: UUID


class DocumentSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(default="", max_length=100)
    cursor: SearchCursor | None = None
    workspace_id: UUID | None = None
    favorites_only: StrictBool = False
    limit: int = Field(default=20, ge=1, le=50)


class DocumentSearchItem(BaseModel):
    id: UUID
    workspace_id: UUID
    workspace_name: str
    title: str | None
    status: DocumentStatus
    is_owner: bool
    favorite: bool
    pinned: bool


class DocumentSearchView(BaseModel):
    items: list[DocumentSearchItem]
    next_cursor: SearchCursor | None
    scanned_count: int


class DocumentPreferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    favorite: StrictBool | None = None
    pinned: StrictBool | None = None

    @model_validator(mode="after")
    def needs_flag(self):
        if self.favorite is None and self.pinned is None:
            raise ValueError("Choose a document preference.")
        return self


class DocumentPreferenceView(BaseModel):
    document_id: UUID
    favorite: bool
    pinned: bool


class BulkDocumentsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_ids: list[UUID] = Field(min_length=1, max_length=50)
    action: BulkAction

    @model_validator(mode="after")
    def unique_documents(self):
        if len(set(self.document_ids)) != len(self.document_ids):
            raise ValueError("Choose each document once.")
        return self


class BulkDocumentOutcome(BaseModel):
    document_id: UUID
    outcome: Literal["updated", "deleted", "not_found", "unavailable", "session_ended"]
    favorite: bool | None = None
    pinned: bool | None = None


class BulkDocumentsView(BaseModel):
    outcomes: list[BulkDocumentOutcome]


def available_documents(actor_id: UUID, now: datetime):
    return review_document_statement(actor_id).where(
        Document.deleted_at.is_(None),
        Document.expires_at > now,
        Document.status.not_in([DocumentStatus.EXPIRED, DocumentStatus.DELETED]),
    )


def search_documents(
    engine: Engine,
    *,
    actor_id: UUID,
    body: DocumentSearchRequest,
    keys: KeyRing,
) -> DocumentSearchView:
    with Session(engine) as session:
        if body.workspace_id is not None:
            active_workspace(session, body.workspace_id, actor_id)
        statement = (
            available_documents(actor_id, datetime.now(UTC))
            .join(Workspace, Workspace.id == Document.workspace_id)
            .outerjoin(
                DocumentPreference,
                and_(
                    DocumentPreference.document_id == Document.id,
                    DocumentPreference.actor_id == actor_id,
                ),
            )
            .add_columns(Workspace.name, DocumentPreference.favorite, DocumentPreference.pinned)
        )
        if body.workspace_id is not None:
            statement = statement.where(Document.workspace_id == body.workspace_id)
        if body.favorites_only:
            statement = statement.where(DocumentPreference.favorite.is_(True))
        if body.cursor is not None:
            statement = statement.where(
                tuple_(Document.created_at, Document.id)
                < tuple_(body.cursor.created_at, body.cursor.id)
            )
        rows = session.execute(
            statement.order_by(Document.created_at.desc(), Document.id.desc()).limit(
                SEARCH_CANDIDATES + 1
            )
        ).all()
        items, next_cursor, scanned = [], None, 0
        query = body.query.strip().casefold()
        for document, workspace_name, favorite, pinned in rows[:SEARCH_CANDIDATES]:
            scanned += 1
            title = None
            if document.title_ciphertext is not None and document.title_key_id is not None:
                title = keys.decrypt_text(
                    ProtectedValue(document.title_ciphertext, document.title_key_id)
                )
            label = title or "Untitled review"
            if not query or query in label.casefold():
                items.append(
                    DocumentSearchItem(
                        id=document.id,
                        workspace_id=document.workspace_id,
                        workspace_name=workspace_name,
                        title=title,
                        status=document.status,
                        is_owner=document.owner_id == actor_id,
                        favorite=bool(favorite),
                        pinned=bool(pinned),
                    )
                )
            if len(items) == body.limit:
                break
        if scanned and scanned < len(rows):
            last = rows[scanned - 1][0]
            next_cursor = SearchCursor(created_at=last.created_at, id=last.id)
        # Decryption can take time. Never return titles for a grant revoked or a
        # retention deadline reached during this request. Select scalar IDs so
        # the ORM identity map cannot reuse stale membership/user state.
        if body.workspace_id is not None:
            active_workspace(session, body.workspace_id, actor_id)
        checked_ids = [item.id for item in items]
        if next_cursor is not None:
            checked_ids.append(next_cursor.id)
        allowed = (
            set(
                session.scalars(
                    available_documents(actor_id, datetime.now(UTC))
                    .with_only_columns(Document.id)
                    .where(Document.id.in_(checked_ids))
                ).all()
            )
            if checked_ids
            else set()
        )
        if next_cursor is not None and next_cursor.id not in allowed:
            next_cursor = None
        return DocumentSearchView(
            items=[item for item in items if item.id in allowed],
            next_cursor=next_cursor,
            scanned_count=scanned,
        )


def update_preference(
    engine: Engine,
    *,
    document_id: UUID,
    actor_id: UUID,
    body: DocumentPreferenceRequest,
    authorize: Callable[[], None],
    workspace_id: UUID | None = None,
) -> DocumentPreferenceView:
    with Session(engine) as session, session.begin():
        document = review_document(session, document_id, actor_id, datetime.now(UTC), lock=True)
        refresh_document_access(session, document_id, actor_id, authorize)
        if workspace_id is not None and document.workspace_id != workspace_id:
            from app.accounts.access import DocumentNotFound

            raise DocumentNotFound("Document not found.")
        flag = session.get(DocumentPreference, (actor_id, document_id))
        favorite = body.favorite if body.favorite is not None else bool(flag and flag.favorite)
        pinned = body.pinned if body.pinned is not None else bool(flag and flag.pinned)
        if not favorite and not pinned:
            if flag is not None:
                session.delete(flag)
        elif flag is None:
            session.add(
                DocumentPreference(
                    actor_id=actor_id, document_id=document_id, favorite=favorite, pinned=pinned
                )
            )
        else:
            flag.favorite, flag.pinned = favorite, pinned
        view = DocumentPreferenceView(document_id=document_id, favorite=favorite, pinned=pinned)
        session.flush()
        refresh_document_access(session, document_id, actor_id, authorize)
        return view


def delete_owned_document(
    engine: Engine,
    *,
    document_id: UUID,
    actor_id: UUID,
    workspace_id: UUID,
    authorize: Callable[[], None],
) -> None:
    with Session(engine) as session, session.begin():
        document = owned_document_record(session, document_id, actor_id, lock=True)
        if document.workspace_id != workspace_id:
            from app.accounts.access import DocumentNotFound

            raise DocumentNotFound("Document not found.")
        authorize()
        owned_document_record(session, document_id, actor_id)
        now = datetime.now(UTC)
        if document.deleted_at is None:
            document.deleted_at, document.status, document.updated_at = (
                now,
                DocumentStatus.DELETED,
                now,
            )
            record_event(
                session,
                workspace_id=workspace_id,
                actor_id=actor_id,
                document_id=document_id,
                event_code="document_deleted",
                now=now,
            )
            session.flush()
        # The same transaction removes content; a per-item success is concrete.
        purge_document(session, document, now)
        session.execute(
            delete(DocumentPreference).where(DocumentPreference.document_id == document_id)
        )
        session.flush()
        authorize()
        owned_document_record(session, document_id, actor_id)
