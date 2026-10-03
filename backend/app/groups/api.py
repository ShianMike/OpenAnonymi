"""Exact-span manual finding routes for one authorized document owner."""

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
    DecisionAction,
    ErrorResponse,
    FindingCategory,
    SourceSpan,
    VersionRef,
)
from app.db.crypto import ContentKeyUnavailable, KeyRing, ProtectedContentError
from app.db.repository import VersionConflict
from app.errors import ApiError
from app.groups.service import (
    FindingNotFound,
    FindingsSnapshot,
    ReviewValidationError,
    add_exact_match,
    add_finding,
    decide_findings,
    exact_matches,
    load_findings,
    merge_findings,
    remove_finding,
    revise_finding,
    split_finding,
    undo_last_review_edit,
)
from app.transformations.contracts import StyleName, StyleOption


class FindingView(BaseModel):
    finding_id: UUID
    span: SourceSpan
    category: FindingCategory
    origin: Literal["manual", "automatic"]
    rule_id: str | None
    rule_version: str | None
    reason: str | None
    group_id: UUID | None
    label: str | None
    action: Literal["label", "redact", "keep"] | None
    keep_reason: str | None
    style: StyleName
    style_option: StyleOption | None
    date_format: str | None


class FindingsView(BaseModel):
    version: VersionRef
    findings: list[FindingView]
    overlaps: list[tuple[UUID, UUID]]
    undo_available: int = Field(default=0, ge=0, le=20)


class ExactMatchesView(BaseModel):
    version: VersionRef
    spans: list[SourceSpan]
    truncated: bool


class NewFindingRequest(BaseModel):
    expected: VersionRef
    span: SourceSpan
    category: FindingCategory


class ReviseFindingRequest(NewFindingRequest):
    pass


class RemoveFindingRequest(BaseModel):
    expected: VersionRef


class ExactMatchRequest(BaseModel):
    expected: VersionRef
    span: SourceSpan


class MergeRequest(BaseModel):
    expected: VersionRef
    target_finding_id: UUID


class DecisionRequest(BaseModel):
    expected: VersionRef
    action: DecisionAction
    keep_reason: str | None = None
    group_scope: bool = False
    affected_finding_ids: set[UUID]
    style: Literal["token", "stand_in", "date_shift", "partial_mask", "generalize"] = "token"
    style_option: str | None = Field(default=None, max_length=24)


class RefreshDefaultsRequest(BaseModel):
    expected_decision_version: int = Field(ge=0)


def _view(snapshot: FindingsSnapshot) -> FindingsView:
    return FindingsView(
        version=snapshot.version,
        undo_available=snapshot.undo_available,
        overlaps=list(snapshot.overlaps),
        findings=[
            FindingView(
                finding_id=item.id,
                span=item.span,
                category=item.category,
                origin=item.origin,
                rule_id=item.rule_id,
                rule_version=item.rule_version,
                reason=item.reason,
                group_id=item.group_id,
                label=item.label,
                action=item.action,
                keep_reason=item.keep_reason,
                style=item.style,
                style_option=item.style_option,
                date_format=item.date_format,
            )
            for item in snapshot.findings
        ],
    )


def _error(exc: Exception) -> JSONResponse | ApiError:
    if isinstance(exc, VersionConflict):
        return JSONResponse(
            status_code=409,
            content=ConflictResponse(current_version=exc.current).model_dump(mode="json"),
        )
    if isinstance(exc, (DocumentNotFound, FindingNotFound)):
        return ApiError(404, "finding_not_found", "Finding or document not found.")
    if isinstance(exc, ContentUnavailable):
        return ApiError(410, "content_expired", "Document content is unavailable.")
    if isinstance(exc, (ContentKeyUnavailable, ProtectedContentError)):
        return ApiError(503, "content_unavailable", "Content access is unavailable.")
    if isinstance(exc, ReviewValidationError):
        return ApiError(422, exc.code, str(exc))
    raise exc


def _keys(request: Request) -> KeyRing:
    try:
        return KeyRing.from_settings(request.app.state.settings)
    except ContentKeyUnavailable:
        raise ApiError(503, "content_unavailable", "Content access is unavailable.") from None


def create_groups_router(engine: Engine) -> APIRouter:
    router = APIRouter(prefix="/api/v1/documents", tags=["findings"])

    @router.get(
        "/{document_id}/findings",
        response_model=FindingsView,
        responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def findings_route(
        document_id: UUID,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ) -> FindingsView:
        try:
            return _view(
                load_findings(
                    engine,
                    document_id=document_id,
                    actor_id=identity.user_id,
                    now=datetime.now(UTC),
                )
            )
        except (DocumentNotFound, ContentUnavailable) as exc:
            result = _error(exc)
            if isinstance(result, ApiError):
                raise result from None
            return result

    @router.post(
        "/{document_id}/findings",
        response_model=FindingsView,
        responses={409: {"model": ConflictResponse}, 422: {"model": ErrorResponse}},
    )
    def add_route(
        document_id: UUID,
        body: NewFindingRequest,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> FindingsView | JSONResponse:
        try:
            return _view(
                add_finding(
                    engine,
                    document_id=document_id,
                    actor_id=identity.user_id,
                    expected=body.expected,
                    span=body.span,
                    category=body.category,
                    keys=_keys(request),
                    now=datetime.now(UTC),
                )
            )
        except (
            VersionConflict,
            DocumentNotFound,
            ContentUnavailable,
            ContentKeyUnavailable,
            ProtectedContentError,
            ReviewValidationError,
        ) as exc:
            result = _error(exc)
            if isinstance(result, ApiError):
                raise result from None
            return result

    @router.put(
        "/{document_id}/findings/{finding_id}",
        response_model=FindingsView,
        responses={409: {"model": ConflictResponse}, 422: {"model": ErrorResponse}},
    )
    def revise_route(
        document_id: UUID,
        finding_id: UUID,
        body: ReviseFindingRequest,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> FindingsView | JSONResponse:
        try:
            return _view(
                revise_finding(
                    engine,
                    document_id=document_id,
                    finding_id=finding_id,
                    actor_id=identity.user_id,
                    expected=body.expected,
                    span=body.span,
                    category=body.category,
                    keys=_keys(request),
                    now=datetime.now(UTC),
                )
            )
        except (
            VersionConflict,
            DocumentNotFound,
            FindingNotFound,
            ContentUnavailable,
            ContentKeyUnavailable,
            ProtectedContentError,
            ReviewValidationError,
        ) as exc:
            result = _error(exc)
            if isinstance(result, ApiError):
                raise result from None
            return result

    @router.post(
        "/{document_id}/findings/{finding_id}/remove",
        response_model=FindingsView,
        responses={409: {"model": ConflictResponse}},
    )
    def remove_route(
        document_id: UUID,
        finding_id: UUID,
        body: RemoveFindingRequest,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> FindingsView | JSONResponse:
        try:
            return _view(
                remove_finding(
                    engine,
                    document_id=document_id,
                    finding_id=finding_id,
                    actor_id=identity.user_id,
                    expected=body.expected,
                    now=datetime.now(UTC),
                )
            )
        except (VersionConflict, DocumentNotFound, FindingNotFound, ContentUnavailable) as exc:
            result = _error(exc)
            if isinstance(result, ApiError):
                raise result from None
            return result

    @router.get(
        "/{document_id}/findings/{finding_id}/exact-matches",
        response_model=ExactMatchesView,
    )
    def exact_matches_route(
        document_id: UUID,
        finding_id: UUID,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ) -> ExactMatchesView:
        try:
            result = exact_matches(
                engine,
                document_id=document_id,
                finding_id=finding_id,
                actor_id=identity.user_id,
                keys=_keys(request),
                now=datetime.now(UTC),
            )
            return ExactMatchesView(
                version=result.version, spans=list(result.spans), truncated=result.truncated
            )
        except (
            DocumentNotFound,
            FindingNotFound,
            ContentUnavailable,
            ContentKeyUnavailable,
            ProtectedContentError,
        ) as exc:
            result = _error(exc)
            if isinstance(result, ApiError):
                raise result from None
            return result

    @router.post(
        "/{document_id}/findings/{finding_id}/exact-matches",
        response_model=FindingsView,
    )
    def add_exact_match_route(
        document_id: UUID,
        finding_id: UUID,
        body: ExactMatchRequest,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> FindingsView | JSONResponse:
        try:
            return _view(
                add_exact_match(
                    engine,
                    document_id=document_id,
                    finding_id=finding_id,
                    actor_id=identity.user_id,
                    expected=body.expected,
                    span=body.span,
                    keys=_keys(request),
                    now=datetime.now(UTC),
                )
            )
        except (
            VersionConflict,
            DocumentNotFound,
            FindingNotFound,
            ContentUnavailable,
            ContentKeyUnavailable,
            ProtectedContentError,
            ReviewValidationError,
        ) as exc:
            result = _error(exc)
            if isinstance(result, ApiError):
                raise result from None
            return result

    @router.post(
        "/{document_id}/findings/{finding_id}/split",
        response_model=FindingsView,
    )
    def split_route(
        document_id: UUID,
        finding_id: UUID,
        body: RemoveFindingRequest,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> FindingsView | JSONResponse:
        try:
            return _view(
                split_finding(
                    engine,
                    document_id=document_id,
                    finding_id=finding_id,
                    actor_id=identity.user_id,
                    expected=body.expected,
                    now=datetime.now(UTC),
                )
            )
        except (
            VersionConflict,
            DocumentNotFound,
            FindingNotFound,
            ContentUnavailable,
            ReviewValidationError,
        ) as exc:
            result = _error(exc)
            if isinstance(result, ApiError):
                raise result from None
            return result

    @router.post(
        "/{document_id}/findings/{finding_id}/merge",
        response_model=FindingsView,
    )
    def merge_route(
        document_id: UUID,
        finding_id: UUID,
        body: MergeRequest,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> FindingsView | JSONResponse:
        try:
            return _view(
                merge_findings(
                    engine,
                    document_id=document_id,
                    source_finding_id=finding_id,
                    target_finding_id=body.target_finding_id,
                    actor_id=identity.user_id,
                    expected=body.expected,
                    now=datetime.now(UTC),
                )
            )
        except (
            VersionConflict,
            DocumentNotFound,
            FindingNotFound,
            ContentUnavailable,
            ReviewValidationError,
        ) as exc:
            result = _error(exc)
            if isinstance(result, ApiError):
                raise result from None
            return result

    @router.post(
        "/{document_id}/findings/{finding_id}/decision",
        response_model=FindingsView,
    )
    def decision_route(
        document_id: UUID,
        finding_id: UUID,
        body: DecisionRequest,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> FindingsView | JSONResponse:
        try:
            return _view(
                decide_findings(
                    engine,
                    document_id=document_id,
                    finding_id=finding_id,
                    actor_id=identity.user_id,
                    expected=body.expected,
                    action=body.action,
                    keep_reason=body.keep_reason,
                    affected_ids=body.affected_finding_ids,
                    group_scope=body.group_scope,
                    style=body.style,
                    style_option=body.style_option,
                    keys=_keys(request),
                    now=datetime.now(UTC),
                )
            )
        except (
            VersionConflict,
            DocumentNotFound,
            FindingNotFound,
            ContentUnavailable,
            ReviewValidationError,
            ContentKeyUnavailable,
            ProtectedContentError,
        ) as exc:
            result = _error(exc)
            if isinstance(result, ApiError):
                raise result from None
            return result

    @router.post("/{document_id}/category-defaults/refresh", response_model=FindingsView)
    def refresh_defaults_route(
        document_id: UUID,
        body: RefreshDefaultsRequest,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        from app.transformations.defaults import refresh_defaults

        try:
            return _view(
                refresh_defaults(
                    engine,
                    document_id=document_id,
                    actor_id=identity.user_id,
                    expected_decision_version=body.expected_decision_version,
                    now=datetime.now(UTC),
                )
            )
        except (
            VersionConflict,
            DocumentNotFound,
            ContentUnavailable,
            ReviewValidationError,
        ) as exc:
            result = _error(exc)
            if isinstance(result, ApiError):
                raise result from None
            return result

    @router.post(
        "/{document_id}/review/undo",
        response_model=FindingsView,
        responses={409: {"model": ConflictResponse}, 422: {"model": ErrorResponse}},
    )
    def undo_route(
        document_id: UUID,
        body: RemoveFindingRequest,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> FindingsView | JSONResponse:
        try:
            return _view(
                undo_last_review_edit(
                    engine,
                    document_id=document_id,
                    actor_id=identity.user_id,
                    expected=body.expected,
                    now=datetime.now(UTC),
                )
            )
        except (
            VersionConflict,
            DocumentNotFound,
            ContentUnavailable,
            ReviewValidationError,
        ) as exc:
            result = _error(exc)
            if isinstance(result, ApiError):
                raise result from None
            return result

    return router
