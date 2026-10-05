"""Workspace document index and reporting endpoints."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import ContentUnavailable, DocumentNotFound, WorkspaceAccessDenied
from app.accounts.api import current_identity
from app.accounts.response_boundary import protected_json_response
from app.accounts.security import SessionIdentity
from app.contracts import DocumentStatus, ErrorResponse, FindingCategory
from app.db.crypto import ContentKeyUnavailable, KeyRing, ProtectedContentError
from app.errors import ApiError
from app.workspace.activity import load_activity
from app.workspace.documents import list_documents, load_overview
from app.workspace.history import load_document_history
from app.workspace.private_titles import validate_title_view


class DocumentIndexView(BaseModel):
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
    favorite: bool
    pinned: bool


class CategoryCountView(BaseModel):
    category: FindingCategory
    count: int = Field(ge=0)


class OverviewAnalyticsView(BaseModel):
    since: datetime
    cohort_documents: int = Field(ge=0)
    confirmed_documents: int = Field(ge=0)
    exported_documents: int = Field(ge=0)
    average_time_to_confirm_seconds: float | None = Field(ge=0)
    export_rate: float | None = Field(ge=0, le=1)
    findings_total: int = Field(ge=0)
    categories: list[CategoryCountView]


class OverviewView(BaseModel):
    as_of: datetime
    own_total: int
    own_created_last_30_days: int
    own_by_status: dict[str, int]
    workspace_total: int | None
    analytics: OverviewAnalyticsView


class ActivityEntryView(BaseModel):
    event_code: str
    outcome: str
    document_id: UUID | None
    occurred_at: datetime


class ActivityView(BaseModel):
    as_of: datetime
    since: datetime
    own_events: list[ActivityEntryView]
    own_total: int
    workspace_counts: dict[str, int] | None


class RevisionHistoryView(BaseModel):
    id: UUID
    number: int
    created_at: datetime
    is_current: bool


class HistoryEventView(BaseModel):
    event_code: str
    outcome: str
    occurred_at: datetime


class DocumentHistoryView(BaseModel):
    document_id: UUID
    status: DocumentStatus
    created_at: datetime
    expires_at: datetime
    deleted_at: datetime | None
    revisions: list[RevisionHistoryView]
    revision_total: int
    events: list[HistoryEventView]
    event_total: int


def create_workspace_router(engine: Engine) -> APIRouter:
    router = APIRouter(prefix="/api/v1/workspaces", tags=["workspace"])

    @router.get(
        "/{workspace_id}/documents/{document_id}/history",
        response_model=DocumentHistoryView,
        responses={404: {"model": ErrorResponse}},
    )
    def history_route(
        workspace_id: UUID,
        document_id: UUID,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ) -> DocumentHistoryView:
        try:
            record = load_document_history(
                engine,
                workspace_id=workspace_id,
                document_id=document_id,
                actor_id=identity.user_id,
                now=datetime.now(UTC),
            )
        except DocumentNotFound:
            raise ApiError(404, "document_not_found", "Document not found.") from None
        return DocumentHistoryView(
            document_id=record.document_id,
            status=record.status,
            created_at=record.created_at,
            expires_at=record.expires_at,
            deleted_at=record.deleted_at,
            revisions=[
                RevisionHistoryView.model_validate(item, from_attributes=True)
                for item in record.revisions
            ],
            revision_total=record.revision_total,
            events=[
                HistoryEventView(event_code=code, outcome=outcome, occurred_at=when)
                for code, outcome, when in record.events
            ],
            event_total=record.event_total,
        )

    @router.get(
        "/{workspace_id}/documents",
        response_model=list[DocumentIndexView],
        responses={status: {"model": ErrorResponse} for status in (404, 409, 410, 503)},
    )
    def documents_route(
        workspace_id: UUID,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ) -> list[DocumentIndexView]:
        try:
            keys = KeyRing.from_settings(request.app.state.settings)
            records = list_documents(
                engine,
                workspace_id=workspace_id,
                actor_id=identity.user_id,
                keys=keys,
                now=datetime.now(UTC),
            )
            view = [
                DocumentIndexView.model_validate(record, from_attributes=True) for record in records
            ]

            def authorize(current):
                with Session(engine) as session:
                    validate_title_view(
                        session, current.user_id, view, keys, workspace_id=workspace_id, index=True
                    )

            return protected_json_response(view, request, identity, authorize)
        except (WorkspaceAccessDenied, DocumentNotFound):
            raise ApiError(404, "workspace_not_found", "Workspace not found.") from None
        except ContentUnavailable:
            raise ApiError(410, "content_expired", "Document content is unavailable.") from None
        except (ContentKeyUnavailable, ProtectedContentError):
            raise ApiError(503, "content_unavailable", "Document titles are unavailable.") from None

    @router.get(
        "/{workspace_id}/overview",
        response_model=OverviewView,
        responses={404: {"model": ErrorResponse}},
    )
    def overview_route(
        workspace_id: UUID,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ) -> OverviewView:
        try:
            record = load_overview(
                engine,
                workspace_id=workspace_id,
                actor_id=identity.user_id,
                now=datetime.now(UTC),
            )
            current_identity(request)
            return OverviewView.model_validate(record, from_attributes=True)
        except WorkspaceAccessDenied:
            raise ApiError(404, "workspace_not_found", "Workspace not found.") from None

    @router.get(
        "/{workspace_id}/activity",
        response_model=ActivityView,
        responses={404: {"model": ErrorResponse}},
    )
    def activity_route(
        workspace_id: UUID,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ) -> ActivityView:
        try:
            record = load_activity(
                engine,
                workspace_id=workspace_id,
                actor_id=identity.user_id,
                now=datetime.now(UTC),
            )
            current_identity(request)
            return ActivityView.model_validate(record, from_attributes=True)
        except WorkspaceAccessDenied:
            raise ApiError(404, "workspace_not_found", "Workspace not found.") from None

    return router
