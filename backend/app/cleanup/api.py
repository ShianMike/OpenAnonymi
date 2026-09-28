"""Owner-only document deletion."""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.engine import Engine

from app.accounts.access import DocumentNotFound
from app.accounts.api import mutation_identity
from app.accounts.security import SessionIdentity
from app.cleanup.service import mark_document_deleted
from app.contracts import ErrorResponse
from app.errors import ApiError


class DeletedView(BaseModel):
    status: Literal["deleted"] = "deleted"


def create_cleanup_router(engine: Engine) -> APIRouter:
    router = APIRouter(prefix="/api/v1/documents", tags=["document lifecycle"])

    @router.delete(
        "/{document_id}",
        response_model=DeletedView,
        responses={404: {"model": ErrorResponse}},
    )
    def delete_route(
        document_id: UUID,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> DeletedView:
        try:
            mark_document_deleted(
                engine,
                document_id=document_id,
                actor_id=identity.user_id,
                now=datetime.now(UTC),
            )
            return DeletedView()
        except DocumentNotFound:
            raise ApiError(404, "document_not_found", "Document not found.") from None

    return router
