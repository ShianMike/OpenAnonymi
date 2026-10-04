"""Reviewed PDF/report downloads share the ordinary locked output gate."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.engine import Engine

from app.accounts.access import ContentUnavailable, DocumentNotFound
from app.accounts.api import mutation_identity
from app.accounts.security import SessionIdentity
from app.db.crypto import ContentKeyUnavailable, ProtectedContentError
from app.db.repository import VersionConflict
from app.errors import ApiError
from app.exports.api import ExportRequest, _error, _keys
from app.exports.errors import PdfUnavailable
from app.exports.service import ExportConflict, generate_output
from app.reviews.service import CompletionRejected
from app.transformations.engine import InvalidTransformation


def create_render_router(engine: Engine) -> APIRouter:
    router = APIRouter(prefix="/api/v1/documents", tags=["exports"])

    def download(document_id, body, request, identity, format):
        try:
            payload, output = generate_output(
                engine,
                document_id=document_id,
                actor_id=identity.user_id,
                expected=body.expected,
                event_id=body.event_id,
                keys=_keys(request),
                now=datetime.now(UTC),
                format=format,
            )
            return Response(
                payload,
                media_type="application/pdf" if format == "pdf" else "application/json",
                headers={
                    "Content-Disposition": f'attachment; filename="{output.filename}"',
                    "X-Content-Type-Options": "nosniff",
                },
            )
        except PdfUnavailable as exc:
            raise ApiError(409, "pdf_unavailable", str(exc)) from None
        except (
            VersionConflict,
            DocumentNotFound,
            ContentUnavailable,
            ContentKeyUnavailable,
            ProtectedContentError,
            CompletionRejected,
            ExportConflict,
            InvalidTransformation,
        ) as exc:
            error = _error(exc)
            if isinstance(error, ApiError):
                raise error from None
            return error

    @router.post(
        "/{document_id}/exports/pdf",
        response_class=Response,
        responses={200: {"content": {"application/pdf": {}}}},
    )
    def pdf_route(
        document_id: UUID,
        body: ExportRequest,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> Response:
        return download(document_id, body, request, identity, "pdf")

    @router.post(
        "/{document_id}/exports/report",
        response_class=Response,
        responses={200: {"content": {"application/json": {}}}},
    )
    def report_route(
        document_id: UUID,
        body: ExportRequest,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> Response:
        return download(document_id, body, request, identity, "report")

    return router
