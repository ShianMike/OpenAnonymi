"""Final preview confirmation and content-free review summary."""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.engine import Engine

from app.accounts.access import ContentUnavailable, DocumentNotFound
from app.accounts.api import current_identity, mutation_identity
from app.accounts.security import SessionIdentity
from app.contracts import ConflictResponse, ErrorResponse, VersionRef
from app.db.crypto import ContentKeyUnavailable, KeyRing, ProtectedContentError
from app.db.repository import VersionConflict
from app.errors import ApiError
from app.reviews.service import CompletionRejected, confirm_review, load_review_summary
from app.transformations.engine import InvalidTransformation


class ConfirmReviewRequest(BaseModel):
    expected: VersionRef
    confirmed_preview: bool


class CompletionView(BaseModel):
    version: VersionRef
    completion_id: UUID
    confirmed_at: datetime
    status: Literal["ready"] = "ready"


class ReviewSummaryView(BaseModel):
    version: VersionRef
    confirmed_at: datetime
    last_output_generated_at: datetime | None
    finding_count: int
    counts_by_category: dict[str, int]
    counts_by_action: dict[str, int]


def create_reviews_router(engine: Engine) -> APIRouter:
    router = APIRouter(prefix="/api/v1/documents", tags=["review"])

    @router.post(
        "/{document_id}/complete",
        response_model=CompletionView,
        responses={409: {"model": ConflictResponse}, 422: {"model": ErrorResponse}},
    )
    def complete_route(
        document_id: UUID,
        body: ConfirmReviewRequest,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> CompletionView | JSONResponse:
        try:
            keys = KeyRing.from_settings(request.app.state.settings)
            result = confirm_review(
                engine,
                document_id=document_id,
                actor_id=identity.user_id,
                expected=body.expected,
                confirmed_preview=body.confirmed_preview,
                keys=keys,
                now=datetime.now(UTC),
            )
            return CompletionView(
                version=result.version,
                completion_id=result.completion_id,
                confirmed_at=result.confirmed_at,
            )
        except VersionConflict as exc:
            return JSONResponse(
                status_code=409,
                content=ConflictResponse(current_version=exc.current).model_dump(mode="json"),
            )
        except DocumentNotFound:
            raise ApiError(404, "document_not_found", "Document not found.") from None
        except ContentUnavailable:
            raise ApiError(410, "content_expired", "Document content is unavailable.") from None
        except (ContentKeyUnavailable, ProtectedContentError):
            raise ApiError(503, "content_unavailable", "Content access is unavailable.") from None
        except CompletionRejected as exc:
            raise ApiError(422, exc.code, str(exc)) from None
        except InvalidTransformation:
            raise ApiError(
                409, "invalid_review_state", "The current review cannot be confirmed."
            ) from None

    @router.get("/{document_id}/summary", response_model=ReviewSummaryView)
    def summary_route(
        document_id: UUID,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ) -> ReviewSummaryView:
        try:
            result = load_review_summary(
                engine,
                document_id=document_id,
                actor_id=identity.user_id,
                now=datetime.now(UTC),
            )
            return ReviewSummaryView(
                version=result.version,
                confirmed_at=result.confirmed_at,
                last_output_generated_at=result.last_output_generated_at,
                finding_count=result.finding_count,
                counts_by_category=result.counts_by_category,
                counts_by_action=result.counts_by_action,
            )
        except DocumentNotFound:
            raise ApiError(404, "document_not_found", "Document not found.") from None
        except ContentUnavailable:
            raise ApiError(410, "content_expired", "Document content is unavailable.") from None
        except CompletionRejected as exc:
            raise ApiError(409, exc.code, str(exc)) from None

    return router
