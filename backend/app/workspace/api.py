"""Workspace document index and reporting endpoints."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.engine import Engine

from app.accounts.access import WorkspaceAccessDenied
from app.accounts.api import current_identity
from app.accounts.security import SessionIdentity
from app.contracts import DocumentStatus, ErrorResponse
from app.db.crypto import ContentKeyUnavailable, KeyRing, ProtectedContentError
from app.errors import ApiError
from app.workspace.activity import load_activity
from app.workspace.documents import list_documents, load_overview


class DocumentIndexView(BaseModel):
    id: UUID
    title: str | None
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    current_revision_id: UUID | None
    finding_count: int
    decided_count: int


class OverviewView(BaseModel):
    as_of: datetime
    own_total: int
    own_created_last_30_days: int
    own_by_status: dict[str, int]
    workspace_total: int | None


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


def create_workspace_router(engine: Engine) -> APIRouter:
    router = APIRouter(prefix="/api/v1/workspaces", tags=["workspace"])

    @router.get(
        "/{workspace_id}/documents",
        response_model=list[DocumentIndexView],
        responses={404: {"model": ErrorResponse}},
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
            return [
                DocumentIndexView.model_validate(record, from_attributes=True) for record in records
            ]
        except WorkspaceAccessDenied:
            raise ApiError(404, "workspace_not_found", "Workspace not found.") from None
        except (ContentKeyUnavailable, ProtectedContentError):
            raise ApiError(503, "content_unavailable", "Document titles are unavailable.") from None

    @router.get(
        "/{workspace_id}/overview",
        response_model=OverviewView,
        responses={404: {"model": ErrorResponse}},
    )
    def overview_route(
        workspace_id: UUID,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ) -> OverviewView:
        try:
            record = load_overview(
                engine,
                workspace_id=workspace_id,
                actor_id=identity.user_id,
                now=datetime.now(UTC),
            )
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
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ) -> ActivityView:
        try:
            record = load_activity(
                engine,
                workspace_id=workspace_id,
                actor_id=identity.user_id,
                now=datetime.now(UTC),
            )
            return ActivityView.model_validate(record, from_attributes=True)
        except WorkspaceAccessDenied:
            raise ApiError(404, "workspace_not_found", "Workspace not found.") from None

    return router
