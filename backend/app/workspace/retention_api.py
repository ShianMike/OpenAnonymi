"""Fresh authenticated retention policy and optimistic owner-only renewal."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.engine import Engine

from app.accounts.access import ContentUnavailable, DocumentNotFound
from app.accounts.api import current_identity, mutation_identity
from app.accounts.limits import AttemptLimiter
from app.accounts.response_boundary import protected_json_response
from app.accounts.security import SessionIdentity
from app.config import Settings
from app.contracts import ErrorResponse
from app.errors import ApiError
from app.workspace.retention import RetentionRequest, RetentionView, renew_retention, retention_view


def create_retention_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1/documents", tags=["retention"])
    limiter = AttemptLimiter(
        engine,
        settings,
        scope="retention_renewal",
        maximum=30,
        window_seconds=60,
        network_scope=False,
    )
    errors = {code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 410, 422, 429)}

    def translate(operation):
        try:
            return operation()
        except DocumentNotFound:
            raise ApiError(404, "document_not_found", "Document not found.") from None
        except ContentUnavailable:
            raise ApiError(
                410, "content_expired", "Expired or deleted content cannot be renewed."
            ) from None

    def protected(view, document_id, request, identity):
        def authorize(current):
            latest = retention_view(engine, document_id=document_id, actor_id=current.user_id)
            if (view.expires_at, view.maximum_days) != (latest.expires_at, latest.maximum_days):
                raise ApiError(409, "retention_changed", "The retention date changed. Check it before renewing.")
        return translate(lambda: protected_json_response(view, request, identity, authorize))

    @router.get("/{document_id}/retention", response_model=RetentionView, responses=errors)
    def read(
        document_id: UUID,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ):
        view = translate(
            lambda: retention_view(engine, document_id=document_id, actor_id=identity.user_id)
        )
        return protected(view, document_id, request, identity)

    @router.patch("/{document_id}/retention", response_model=RetentionView, responses=errors)
    def renew(
        document_id: UUID,
        body: RetentionRequest,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        if not limiter.take(str(identity.user_id)):
            raise ApiError(429, "action_limited", "Please wait a minute and try again.")
        view = translate(
            lambda: renew_retention(
                engine,
                document_id=document_id,
                actor_id=identity.user_id,
                body=body,
                authorize=lambda: mutation_identity(request),
            )
        )
        return protected(view, document_id, request, identity)

    return router
