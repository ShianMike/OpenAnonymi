"""Current reviewed-output preview; only the document owner may read it."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine

from app.accounts.access import ContentUnavailable, DocumentNotFound
from app.accounts.api import current_identity
from app.accounts.security import SessionIdentity
from app.contracts import DecisionAction, ErrorResponse, SourceSpan, VersionRef
from app.db.crypto import ContentKeyUnavailable, KeyRing, ProtectedContentError
from app.errors import ApiError
from app.transformations.contracts import StyleChoice
from app.transformations.engine import InvalidTransformation, PreviewStatus
from app.transformations.service import load_preview


class SpanMappingView(BaseModel):
    finding_id: UUID
    source_span: SourceSpan
    preview_span: SourceSpan
    action: DecisionAction | None


class PreviewView(BaseModel):
    version: VersionRef
    status: PreviewStatus
    text: str | None
    mappings: list[SpanMappingView]
    unresolved_finding_ids: list[UUID]
    overlaps: list[tuple[UUID, UUID]]
    fictional_finding_ids: list[UUID] = Field(default_factory=list)
    stand_in_fallback_ids: list[UUID] = Field(default_factory=list)
    style_capabilities: dict[str, dict[str, list[StyleChoice]]] = Field(default_factory=dict)


def create_transform_router(engine: Engine) -> APIRouter:
    router = APIRouter(prefix="/api/v1/documents", tags=["preview"])

    @router.get(
        "/{document_id}/preview",
        response_model=PreviewView,
        responses={
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            410: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    def preview_route(
        document_id: UUID,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ) -> PreviewView:
        try:
            keys = KeyRing.from_settings(request.app.state.settings)
            snapshot = load_preview(
                engine,
                document_id=document_id,
                actor_id=identity.user_id,
                keys=keys,
                now=datetime.now(UTC),
            )
            return PreviewView(
                version=snapshot.version,
                status=snapshot.status,
                text=snapshot.text,
                mappings=[
                    SpanMappingView(
                        finding_id=item.finding_id,
                        source_span=item.source_span,
                        preview_span=item.preview_span,
                        action=item.action,
                    )
                    for item in snapshot.mappings
                ],
                unresolved_finding_ids=list(snapshot.unresolved_ids),
                overlaps=list(snapshot.overlaps),
                fictional_finding_ids=list(snapshot.fictional_ids),
                stand_in_fallback_ids=list(snapshot.stand_in_fallback_ids),
                style_capabilities={
                    str(key): value for key, value in (snapshot.style_capabilities or {}).items()
                },
            )
        except DocumentNotFound:
            raise ApiError(404, "document_not_found", "Document not found.") from None
        except ContentUnavailable:
            raise ApiError(410, "content_expired", "Document content is unavailable.") from None
        except (ContentKeyUnavailable, ProtectedContentError):
            raise ApiError(503, "content_unavailable", "Content access is unavailable.") from None
        except InvalidTransformation:
            raise ApiError(
                409, "invalid_review_state", "The current findings cannot be previewed."
            ) from None

    return router
