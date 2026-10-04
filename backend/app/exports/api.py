"""Completed output copy and UTF-8 TXT routes."""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy.engine import Engine

from app.accounts.access import ContentUnavailable, DocumentNotFound
from app.accounts.api import mutation_identity
from app.accounts.security import SessionIdentity
from app.contracts import ConflictResponse, ErrorResponse, VersionRef
from app.db.crypto import ContentKeyUnavailable, KeyRing, ProtectedContentError
from app.db.repository import VersionConflict
from app.errors import ApiError
from app.exports.docx import MEDIA_TYPE
from app.exports.service import (
    ExportConflict,
    generate_output,
    generate_txt,
    prepare_copy,
    record_copy_success,
)
from app.intake.structure import InvalidLayout
from app.reviews.service import CompletionRejected
from app.transformations.engine import InvalidTransformation


class CopyPayloadRequest(BaseModel):
    expected: VersionRef


class CopyPayloadView(BaseModel):
    version: VersionRef
    completion_id: UUID
    text: str


class ExportRequest(BaseModel):
    expected: VersionRef
    event_id: UUID


class CsvExportRequest(ExportRequest):
    variant: Literal["spreadsheet_safe", "unmodified"] = "spreadsheet_safe"


class CopyAckRequest(ExportRequest):
    completion_id: UUID


class ExportEventView(BaseModel):
    event_id: UUID
    recorded_at: datetime


def _keys(request: Request) -> KeyRing:
    return KeyRing.from_settings(request.app.state.settings)


def _error(exc: Exception) -> JSONResponse | ApiError:
    if isinstance(exc, VersionConflict):
        return JSONResponse(
            status_code=409,
            content=ConflictResponse(current_version=exc.current).model_dump(mode="json"),
        )
    if isinstance(exc, DocumentNotFound):
        return ApiError(404, "document_not_found", "Document not found.")
    if isinstance(exc, ContentUnavailable):
        return ApiError(410, "content_expired", "Document content is unavailable.")
    if isinstance(exc, (ContentKeyUnavailable, ProtectedContentError, InvalidLayout)):
        return ApiError(503, "content_unavailable", "Content access is unavailable.")
    if isinstance(exc, CompletionRejected):
        return ApiError(409, exc.code, str(exc))
    if isinstance(exc, ExportConflict):
        return ApiError(409, "export_attempt_conflict", str(exc))
    if isinstance(exc, InvalidTransformation):
        return ApiError(409, "invalid_review_state", "The current review cannot be exported.")
    raise exc


def create_exports_router(engine: Engine) -> APIRouter:
    router = APIRouter(prefix="/api/v1/documents", tags=["exports"])

    @router.post(
        "/{document_id}/exports/copy-payload",
        response_model=CopyPayloadView,
        responses={409: {"model": ErrorResponse}},
    )
    def copy_payload_route(
        document_id: UUID,
        body: CopyPayloadRequest,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> CopyPayloadView | JSONResponse:
        try:
            result = prepare_copy(
                engine,
                document_id=document_id,
                actor_id=identity.user_id,
                expected=body.expected,
                keys=_keys(request),
                now=datetime.now(UTC),
            )
            return CopyPayloadView(
                version=result.version, completion_id=result.completion_id, text=result.text
            )
        except (
            VersionConflict,
            DocumentNotFound,
            ContentUnavailable,
            ContentKeyUnavailable,
            ProtectedContentError,
            CompletionRejected,
            InvalidTransformation,
        ) as exc:
            error = _error(exc)
            if isinstance(error, ApiError):
                raise error from None
            return error

    @router.post(
        "/{document_id}/exports/copy-success",
        response_model=ExportEventView,
    )
    def copy_success_route(
        document_id: UUID,
        body: CopyAckRequest,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> ExportEventView | JSONResponse:
        try:
            recorded_at = record_copy_success(
                engine,
                document_id=document_id,
                actor_id=identity.user_id,
                expected=body.expected,
                completion_id=body.completion_id,
                event_id=body.event_id,
                now=datetime.now(UTC),
            )
            return ExportEventView(event_id=body.event_id, recorded_at=recorded_at)
        except (
            VersionConflict,
            DocumentNotFound,
            ContentUnavailable,
            CompletionRejected,
            ExportConflict,
        ) as exc:
            error = _error(exc)
            if isinstance(error, ApiError):
                raise error from None
            return error

    @router.post(
        "/{document_id}/exports/txt",
        response_class=Response,
        responses={200: {"content": {"text/plain": {}}}},
    )
    def txt_route(
        document_id: UUID,
        body: ExportRequest,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> Response:
        try:
            payload, output = generate_txt(
                engine,
                document_id=document_id,
                actor_id=identity.user_id,
                expected=body.expected,
                event_id=body.event_id,
                keys=_keys(request),
                now=datetime.now(UTC),
            )
            return Response(
                content=payload,
                media_type="text/plain; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="{output.filename}"',
                    "X-Content-Type-Options": "nosniff",
                },
            )
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
        "/{document_id}/exports/docx",
        response_class=Response,
        responses={200: {"content": {MEDIA_TYPE: {}}}},
    )
    def docx_route(
        document_id: UUID,
        body: ExportRequest,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> Response:
        try:
            payload, output = generate_output(
                engine,
                document_id=document_id,
                actor_id=identity.user_id,
                expected=body.expected,
                event_id=body.event_id,
                keys=_keys(request),
                now=datetime.now(UTC),
                format="docx",
            )
            return Response(
                content=payload,
                media_type=MEDIA_TYPE,
                headers={
                    "Content-Disposition": f'attachment; filename="{output.filename}"',
                    "X-Content-Type-Options": "nosniff",
                },
            )
        except (
            VersionConflict,
            DocumentNotFound,
            ContentUnavailable,
            ContentKeyUnavailable,
            ProtectedContentError,
            CompletionRejected,
            ExportConflict,
            InvalidTransformation,
            InvalidLayout,
        ) as exc:
            error = _error(exc)
            if isinstance(error, ApiError):
                raise error from None
            return error

    @router.post(
        "/{document_id}/exports/csv",
        response_class=Response,
        responses={200: {"content": {"text/csv": {}}}},
    )
    def csv_route(
        document_id: UUID,
        body: CsvExportRequest,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> Response:
        try:
            payload, output = generate_output(
                engine,
                document_id=document_id,
                actor_id=identity.user_id,
                expected=body.expected,
                event_id=body.event_id,
                keys=_keys(request),
                now=datetime.now(UTC),
                format="csv",
                variant=body.variant,
            )
            return Response(
                content=payload,
                media_type="text/csv; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="{output.filename}"',
                    "X-Content-Type-Options": "nosniff",
                    "X-CSV-Prefixed-Cells": str(output.prefixed_cells),
                },
            )
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

    return router
