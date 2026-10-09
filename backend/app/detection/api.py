"""Owned-document scan and suggestion settings endpoints."""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine

from app.accounts.access import ContentUnavailable, DocumentNotFound
from app.accounts.api import current_identity, mutation_identity
from app.accounts.security import SessionIdentity
from app.contracts import (
    ConflictResponse,
    ErrorResponse,
    FindingCategory,
    SourceSpan,
    VersionRef,
)
from app.db.crypto import ContentKeyUnavailable, KeyRing, ProtectedContentError
from app.db.repository import VersionConflict
from app.detection.service import (
    ScanExecutionFailed,
    ScanSnapshot,
    change_scan_settings,
    load_scan_state,
    scan_document,
)
from app.errors import ApiError


class ScanRequest(BaseModel):
    expected: VersionRef


class ScanSettingsRequest(BaseModel):
    expected: VersionRef
    categories: list[FindingCategory] = Field(default_factory=list)
    phone_region: str = Field(min_length=2, max_length=2)
    language: str | None = Field(default=None, min_length=2, max_length=2)


class ScanSettingsView(BaseModel):
    version: VersionRef


class SuggestionView(BaseModel):
    finding_id: UUID
    span: SourceSpan
    category: FindingCategory
    rule_id: str
    rule_version: str
    reason: str
    date_format: str | None


class ScanView(BaseModel):
    version: VersionRef
    status: Literal["not_started", "scanning", "completed", "failed", "superseded"]
    attempt_count: int
    match_count: int | None
    failure_code: str | None
    suggestions: list[SuggestionView]
    dropped_suggestions: int


def _view(snapshot: ScanSnapshot) -> ScanView:
    return ScanView(
        version=snapshot.version,
        status=snapshot.status,
        attempt_count=snapshot.attempt_count,
        match_count=snapshot.match_count,
        failure_code=snapshot.failure_code,
        dropped_suggestions=snapshot.dropped_suggestions,
        suggestions=[
            SuggestionView(
                finding_id=item.id,
                span=item.span,
                category=item.category,
                rule_id=item.rule_id,
                rule_version=item.rule_version,
                reason=item.reason,
                date_format=item.date_format,
            )
            for item in snapshot.suggestions
        ],
    )


def _conflict(exc: VersionConflict) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content=ConflictResponse(current_version=exc.current).model_dump(mode="json"),
    )


def create_detection_router(engine: Engine) -> APIRouter:
    router = APIRouter(prefix="/api/v1/documents", tags=["detection"])

    @router.get(
        "/{document_id}/scan",
        response_model=ScanView,
        responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def scan_state_route(
        document_id: UUID,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ) -> ScanView:
        try:
            return _view(
                load_scan_state(
                    engine,
                    document_id=document_id,
                    actor_id=identity.user_id,
                    now=datetime.now(UTC),
                )
            )
        except DocumentNotFound:
            raise ApiError(404, "document_not_found", "Document not found.") from None
        except ContentUnavailable:
            raise ApiError(410, "content_expired", "Document content is unavailable.") from None

    @router.post(
        "/{document_id}/scan",
        response_model=ScanView,
        responses={409: {"model": ConflictResponse}, 503: {"model": ErrorResponse}},
    )
    def scan_route(
        document_id: UUID,
        body: ScanRequest,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> ScanView | JSONResponse:
        try:
            keys = KeyRing.from_settings(request.app.state.settings)
            snapshot = scan_document(
                engine,
                document_id=document_id,
                actor_id=identity.user_id,
                expected=body.expected,
                keys=keys,
                now=datetime.now(UTC),
                reauthorize=lambda: current_identity(request),
            )
            return _view(snapshot)
        except DocumentNotFound:
            raise ApiError(404, "document_not_found", "Document not found.") from None
        except ContentUnavailable:
            raise ApiError(410, "content_expired", "Document content is unavailable.") from None
        except VersionConflict as exc:
            return _conflict(exc)
        except (ContentKeyUnavailable, ProtectedContentError):
            raise ApiError(503, "content_unavailable", "Content access is unavailable.") from None
        except ScanExecutionFailed as exc:
            if exc.code == "local_model_unavailable":
                raise ApiError(
                    503,
                    exc.code,
                    "The local English model is unavailable. An administrator must install the model before scanning these categories.",
                ) from None
            if exc.code in ("too_many_suggestions", "too_many_phone_candidates"):
                raise ApiError(
                    422,
                    exc.code,
                    "There are too many possible matches. Narrow the text or change categories.",
                ) from None
            raise ApiError(
                503, "scan_failed", "Suggestions could not be generated. Retry the scan."
            ) from None

    @router.put(
        "/{document_id}/scan-settings",
        response_model=ScanSettingsView,
        responses={409: {"model": ConflictResponse}, 422: {"model": ErrorResponse}},
    )
    def scan_settings_route(
        document_id: UUID,
        body: ScanSettingsRequest,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> ScanSettingsView | JSONResponse:
        try:
            version = change_scan_settings(
                engine,
                document_id=document_id,
                actor_id=identity.user_id,
                expected=body.expected,
                categories=set(body.categories),
                phone_region=body.phone_region,
                language=body.language,
                now=datetime.now(UTC),
                reauthorize=lambda: current_identity(request),
            )
            return ScanSettingsView(version=version)
        except DocumentNotFound:
            raise ApiError(404, "document_not_found", "Document not found.") from None
        except ContentUnavailable:
            raise ApiError(410, "content_expired", "Document content is unavailable.") from None
        except VersionConflict as exc:
            return _conflict(exc)
        except ValueError as exc:
            raise ApiError(422, "invalid_scan_settings", str(exc)) from None

    return router
