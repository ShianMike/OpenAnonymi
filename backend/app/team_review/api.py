from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine

from app.accounts.access import ContentUnavailable, DocumentNotFound
from app.accounts.api import current_identity, mutation_identity
from app.accounts.security import SessionIdentity
from app.contracts import ConflictResponse, VersionRef
from app.db.crypto import ContentKeyUnavailable, KeyRing, ProtectedContentError
from app.db.repository import VersionConflict
from app.errors import ApiError
from app.reviews.service import CompletionRejected
from app.team_review.comments import CommentView, add_comment, delete_comment, load_comments
from app.team_review.service import (
    HandoffPolicyRejected,
    HandoffView,
    TeammateView,
    approve_review,
    change_handoff,
    list_teammates,
    load_handoff,
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


def _keys(request):
    try:
        return KeyRing.from_settings(request.app.state.settings)
    except ContentKeyUnavailable:
        raise ApiError(503, "content_unavailable", "Content access is unavailable.") from None


def create_team_router(engine: Engine):
    router = APIRouter(prefix="/api/v1/documents", tags=["team review"])

    @router.get("/{document_id}/handoff", response_model=HandoffView)
    def get_handoff(
        document_id: UUID, identity: Annotated[SessionIdentity, Depends(current_identity)]
    ):
        return _guard(
            load_handoff,
            engine=engine,
            document_id=document_id,
            actor_id=identity.user_id,
            now=datetime.now(UTC),
        )

    @router.get("/{document_id}/teammates", response_model=list[TeammateView])
    def get_teammates(
        document_id: UUID, identity: Annotated[SessionIdentity, Depends(current_identity)]
    ):
        return _guard(
            list_teammates,
            engine=engine,
            document_id=document_id,
            actor_id=identity.user_id,
            now=datetime.now(UTC),
        )

    @router.put("/{document_id}/handoff", response_model=HandoffView)
    def put_handoff(
        document_id: UUID,
        body: HandoffInput,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        return _guard(
            change_handoff,
            engine=engine,
            document_id=document_id,
            actor_id=identity.user_id,
            expected=body.expected,
            reviewer_id=body.reviewer_id,
            require_approval=body.require_approval,
            now=datetime.now(UTC),
        )

    @router.post("/{document_id}/approval", response_model=HandoffView)
    def approval(
        document_id: UUID,
        body: ApprovalInput,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        return _guard(
            approve_review,
            engine=engine,
            document_id=document_id,
            actor_id=identity.user_id,
            expected=body.expected,
            confirmed_preview=body.confirmed_preview,
            keys=_keys(request),
            now=datetime.now(UTC),
        )

    @router.get("/{document_id}/findings/{finding_id}/comments", response_model=list[CommentView])
    def comments(
        document_id: UUID,
        finding_id: UUID,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ):
        return _guard(
            load_comments,
            engine=engine,
            document_id=document_id,
            finding_id=finding_id,
            actor_id=identity.user_id,
            keys=_keys(request),
            now=datetime.now(UTC),
        )

    @router.post(
        "/{document_id}/findings/{finding_id}/comments", response_model=CommentView, status_code=201
    )
    def comment(
        document_id: UUID,
        finding_id: UUID,
        body: CommentInput,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        return _guard(
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
        )

    @router.delete("/{document_id}/comments/{comment_id}", status_code=204)
    def remove(
        document_id: UUID,
        comment_id: UUID,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        _guard(
            delete_comment,
            engine=engine,
            document_id=document_id,
            comment_id=comment_id,
            actor_id=identity.user_id,
            now=datetime.now(UTC),
        )
        return Response(status_code=204)

    return router
