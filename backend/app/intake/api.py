"""Authenticated source read path; intake writes follow in T04."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.api import current_identity
from app.accounts.security import SessionIdentity
from app.contracts import DocumentStatus, ErrorResponse, VersionRef
from app.db.crypto import ContentKeyUnavailable, KeyRing, ProtectedContentError
from app.db.repository import ContentUnavailable, DocumentNotFound, load_current_source
from app.errors import ApiError


class SourceView(BaseModel):
    version: VersionRef
    text: str
    expires_at: datetime
    status: DocumentStatus


def create_intake_router(engine: Engine) -> APIRouter:
    router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

    @router.get(
        "/{document_id}/revisions/{revision_id}/source",
        response_model=SourceView,
        responses={
            401: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            410: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    def current_source_route(
        document_id: UUID,
        revision_id: UUID,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ) -> SourceView:
        try:
            keys = KeyRing.from_settings(request.app.state.settings)
        except ContentKeyUnavailable:
            raise ApiError(503, "content_unavailable", "Content access is unavailable.") from None
        try:
            with Session(engine) as session:
                source = load_current_source(
                    session,
                    document_id=document_id,
                    actor_id=identity.user_id,
                    keys=keys,
                    now=datetime.now(UTC),
                )
        except DocumentNotFound:
            raise ApiError(404, "document_not_found", "Document not found.") from None
        except ContentUnavailable:
            raise ApiError(410, "content_expired", "Document content is unavailable.") from None
        except (ContentKeyUnavailable, ProtectedContentError):
            raise ApiError(503, "content_unavailable", "Content access is unavailable.") from None
        if source.version.source_revision_id != revision_id:
            raise ApiError(404, "revision_not_found", "Revision not found.")
        return SourceView(
            version=source.version,
            text=source.text,
            expires_at=source.expires_at,
            status=source.status,
        )

    return router
