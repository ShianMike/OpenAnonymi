"""Aggregate response retains the existing child contracts and access controls."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.engine import Engine

from app.accounts.access import ContentUnavailable, DocumentNotFound
from app.accounts.api import current_identity
from app.accounts.security import SessionIdentity
from app.contracts import ErrorResponse
from app.db.crypto import ContentKeyUnavailable, KeyRing, ProtectedContentError
from app.detection.api import ScanView
from app.detection.api import _view as scan_view
from app.errors import ApiError
from app.groups.api import FindingsView
from app.groups.api import _view as findings_view
from app.intake.api import SourceView, _source_view
from app.reviews.api import ReviewSummaryView
from app.reviews.service import CompletionRejected
from app.reviews.state import load_review_state
from app.team_review.service import HandoffView
from app.transformations.api import PreviewView, preview_view
from app.transformations.engine import InvalidTransformation


class ReviewStateView(BaseModel):
    source: SourceView
    scan: ScanView
    findings: FindingsView
    preview: PreviewView
    summary: ReviewSummaryView | None
    handoff: HandoffView


def create_review_state_router(engine: Engine) -> APIRouter:
    router = APIRouter(prefix="/api/v1/documents", tags=["review state"])

    @router.get(
        "/{document_id}/review-state",
        response_model=ReviewStateView,
        responses={code: {"model": ErrorResponse} for code in (404, 409, 410, 503)},
    )
    def review_state_route(
        document_id: UUID,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ) -> ReviewStateView:
        try:
            result = load_review_state(
                engine,
                document_id=document_id,
                actor_id=identity.user_id,
                keys=KeyRing.from_settings(request.app.state.settings),
                now=datetime.now(UTC),
            )
            return ReviewStateView(
                source=_source_view(result.source),
                scan=scan_view(result.scan),
                findings=findings_view(result.findings),
                preview=preview_view(result.preview),
                summary=ReviewSummaryView(**vars(result.summary)) if result.summary else None,
                handoff=result.handoff,
            )
        except DocumentNotFound:
            raise ApiError(404, "document_not_found", "Document not found.") from None
        except ContentUnavailable:
            raise ApiError(410, "content_expired", "Document content is unavailable.") from None
        except (ContentKeyUnavailable, ProtectedContentError):
            raise ApiError(503, "content_unavailable", "Content access is unavailable.") from None
        except (CompletionRejected, InvalidTransformation):
            raise ApiError(
                409, "invalid_review_state", "The current review cannot be loaded."
            ) from None

    return router
