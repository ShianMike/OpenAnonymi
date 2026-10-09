from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine

from app.accounts.access import ContentUnavailable, DocumentNotFound
from app.accounts.api import current_identity, mutation_identity
from app.accounts.response_boundary import protected_json_response
from app.accounts.security import SessionIdentity
from app.contracts import ConflictResponse, ErrorResponse, VersionRef
from app.db.crypto import ContentKeyUnavailable, KeyRing, ProtectedContentError
from app.db.repository import VersionConflict
from app.errors import ApiError
from app.reviews.service import CompletionRejected
from app.team_review.comments import (
    CommentView,
    add_comment,
    delete_comment,
    load_comments,
    validate_comment_views,
)
from app.team_review.service import (
    HandoffPolicyRejected,
    HandoffView,
    TeammateView,
    TeamReadChanged,
    approve_review,
    change_handoff,
    list_teammates,
    load_handoff,
    validate_handoff_view,
    validate_teammates,
)


class HandoffInput(BaseModel):
    expected: VersionRef
    reviewer_id: UUID | None
    require_approval: bool


class ApprovalInput(BaseModel):
    expected: VersionRef
    confirmed_preview: bool


class CommentInput(BaseModel):
    id: UUID
    expected: VersionRef
    text: str = Field(min_length=1, max_length=2000)


def _guard(function, **kwargs):
    try:
        return function(**kwargs)
    except DocumentNotFound:
        raise ApiError(404, "review_not_found", "Review, reviewer or comment not found.") from None
    except ContentUnavailable:
        raise ApiError(410, "content_expired", "Document content is unavailable.") from None
    except (ContentKeyUnavailable, ProtectedContentError):
        raise ApiError(503, "content_unavailable", "Content access is unavailable.") from None
    except VersionConflict as exc:
        return JSONResponse(
            status_code=409,
            content=ConflictResponse(current_version=exc.current).model_dump(mode="json"),
        )
    except CompletionRejected as exc:
        raise ApiError(409, exc.code, str(exc)) from None
    except HandoffPolicyRejected:
        raise ApiError(
            422, "approval_required_by_policy", "Workspace policy requires reviewer approval."
        ) from None
    except TeamReadChanged:
        raise ApiError(409, "team_changed", "Review access or discussion changed. Reload.") from None


def _keys(request):
    try:
        return KeyRing.from_settings(request.app.state.settings)
    except ContentKeyUnavailable:
        raise ApiError(503, "content_unavailable", "Content access is unavailable.") from None


def create_team_router(engine: Engine):
    router = APIRouter(prefix="/api/v1/documents", tags=["team review"])
    errors = {code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 410, 422, 503)}

    def handoff_response(view, document_id, request, identity):
        if isinstance(view, Response):
            return view
        return protected_json_response(view, request, identity, lambda current: _guard(
            validate_handoff_view, engine=engine, document_id=document_id,
            actor_id=current.user_id, view=view,
        ))

    def comment_response(view, document_id, finding_id, request, identity, *, status=200):
        if isinstance(view, Response):
            return view
        return protected_json_response(view, request, identity, lambda current: _guard(
            validate_comment_views, engine=engine, document_id=document_id, finding_id=finding_id,
            actor_id=current.user_id, views=view if isinstance(view, list) else [view],
        ), status_code=status)

    @router.get("/{document_id}/handoff", response_model=HandoffView, responses=errors)
    def get_handoff(
        document_id: UUID, request: Request,
        identity: Annotated[SessionIdentity, Depends(current_identity)]
    ):
        view = _guard(
            load_handoff,
            engine=engine,
            document_id=document_id,
            actor_id=identity.user_id,
            now=datetime.now(UTC),
        )
        return handoff_response(view, document_id, request, identity)

    @router.get("/{document_id}/teammates", response_model=list[TeammateView], responses=errors)
    def get_teammates(
        document_id: UUID, request: Request,
        identity: Annotated[SessionIdentity, Depends(current_identity)]
    ):
        view = _guard(
            list_teammates,
            engine=engine,
            document_id=document_id,
            actor_id=identity.user_id,
            now=datetime.now(UTC),
        )
        if isinstance(view, Response):
            return view
        return protected_json_response(view, request, identity, lambda current: _guard(
            validate_teammates, engine=engine, document_id=document_id,
            actor_id=current.user_id, view=view,
        ))

    @router.put("/{document_id}/handoff", response_model=HandoffView, responses=errors)
    def put_handoff(
        document_id: UUID,
        body: HandoffInput,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        view = _guard(
            change_handoff,
            engine=engine,
            document_id=document_id,
            actor_id=identity.user_id,
            expected=body.expected,
            reviewer_id=body.reviewer_id,
            require_approval=body.require_approval,
            now=datetime.now(UTC),
            reauthorize=lambda: current_identity(request),
        )
        return handoff_response(view, document_id, request, identity)

    @router.post("/{document_id}/approval", response_model=HandoffView, responses=errors)
    def approval(
        document_id: UUID,
        body: ApprovalInput,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        view = _guard(
            approve_review,
            engine=engine,
            document_id=document_id,
            actor_id=identity.user_id,
            expected=body.expected,
            confirmed_preview=body.confirmed_preview,
            keys=_keys(request),
            now=datetime.now(UTC),
            reauthorize=lambda: current_identity(request),
        )
        return handoff_response(view, document_id, request, identity)

    @router.get("/{document_id}/findings/{finding_id}/comments", response_model=list[CommentView], responses=errors)
    def comments(
        document_id: UUID,
        finding_id: UUID,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ):
        view = _guard(
            load_comments,
            engine=engine,
            document_id=document_id,
            finding_id=finding_id,
            actor_id=identity.user_id,
            keys=_keys(request),
            now=datetime.now(UTC),
        )
        return comment_response(view, document_id, finding_id, request, identity)

    @router.post(
        "/{document_id}/findings/{finding_id}/comments", response_model=CommentView,
        status_code=201, responses=errors,
    )
    def comment(
        document_id: UUID,
        finding_id: UUID,
        body: CommentInput,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        view = _guard(
            add_comment,
            engine=engine,
            document_id=document_id,
            finding_id=finding_id,
            actor_id=identity.user_id,
            comment_id=body.id,
            expected=body.expected,
            text=body.text,
            keys=_keys(request),
            now=datetime.now(UTC),
            reauthorize=lambda: current_identity(request),
        )
        return comment_response(view, document_id, finding_id, request, identity, status=201)

    @router.delete("/{document_id}/comments/{comment_id}", status_code=204, responses=errors)
    def remove(
        document_id: UUID,
        comment_id: UUID,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        _guard(
            delete_comment,
            engine=engine,
            document_id=document_id,
            comment_id=comment_id,
            actor_id=identity.user_id,
            now=datetime.now(UTC),
            reauthorize=lambda: current_identity(request),
        )
        return Response(status_code=204)

    return router
