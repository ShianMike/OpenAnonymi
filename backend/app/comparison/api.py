from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.engine import Engine

from app.accounts.access import ContentUnavailable, DocumentNotFound
from app.accounts.api import current_identity
from app.accounts.security import SessionIdentity
from app.comparison.service import ComparisonView, compare_revisions
from app.db.crypto import ContentKeyUnavailable, KeyRing, ProtectedContentError
from app.errors import ApiError


def create_comparison_router(engine: Engine) -> APIRouter:
    router = APIRouter(prefix="/api/v1/documents", tags=["comparison"])

    @router.get("/{document_id}/compare", response_model=ComparisonView)
    def compare_route(
        document_id: UUID,
        before: UUID,
        after: UUID,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ) -> ComparisonView:
        try:
            return compare_revisions(
                engine,
                document_id=document_id,
                actor_id=identity.user_id,
                before_id=before,
                after_id=after,
                keys=KeyRing.from_settings(request.app.state.settings),
                now=datetime.now(UTC),
            )
        except DocumentNotFound:
            raise ApiError(404, "revision_not_found", "Document or revision not found.") from None
        except ContentUnavailable:
            raise ApiError(410, "content_expired", "Document content is unavailable.") from None
        except (ContentKeyUnavailable, ProtectedContentError):
            raise ApiError(503, "content_unavailable", "Content access is unavailable.") from None

    return router
