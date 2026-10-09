from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import (
    ContentUnavailable,
    DocumentNotFound,
    WorkspaceAccessDenied,
    active_workspace,
    owned_document,
)
from app.accounts.api import current_identity, mutation_identity
from app.accounts.response_boundary import protected_json_response
from app.accounts.security import SessionIdentity
from app.contracts import ConflictResponse, ErrorResponse
from app.custom_rules.contracts import (
    RefreshRulesInput,
    RuleInput,
    RuleSnapshotView,
    RuleTestInput,
    RuleTestMatch,
    RuleTestView,
    RuleUpdate,
    RuleView,
)
from app.custom_rules.matching import matches
from app.custom_rules.service import (
    RuleConflict,
    RuleNotFound,
    refresh_snapshot,
    save_rule,
    snapshot_state,
    validate_rule_view,
    validate_snapshot_view,
    workspace_rules,
)
from app.db.crypto import ContentKeyUnavailable, KeyRing, ProtectedContentError
from app.db.repository import VersionConflict
from app.detection.rules import DetectionLimitError
from app.errors import ApiError


def guarded(operation):
    try:
        return operation()
    except (WorkspaceAccessDenied, RuleNotFound, DocumentNotFound):
        raise ApiError(404, "rule_not_found", "Rule, workspace or review not found.") from None
    except ContentUnavailable:
        raise ApiError(410, "content_expired", "Document content is unavailable.") from None
    except (ContentKeyUnavailable, ProtectedContentError):
        raise ApiError(503, "content_unavailable", "Rule content is unavailable.") from None
    except RuleConflict:
        raise ApiError(409, "rule_conflict", "This rule changed. Reload before saving.") from None
    except VersionConflict as exc:
        return JSONResponse(
            status_code=409,
            content=ConflictResponse(current_version=exc.current).model_dump(mode="json"),
        )
    except DetectionLimitError:
        raise ApiError(
            422, "rule_test_limit", "Too many test matches. Use a more specific rule."
        ) from None
    except ValueError as exc:
        raise ApiError(422, "invalid_rule", str(exc)) from None


def create_custom_rules_router(engine: Engine) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["custom rules"])
    errors = {
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        410: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    }

    def protect(view, request, identity, authorize, *, status_code=200):
        def current(current_actor):
            with Session(engine) as session:
                authorize(session, current_actor.user_id)

        return protected_json_response(view, request, identity, current, status_code=status_code)

    def rule_response(view, request, identity, workspace_id, *, status_code=200):
        return protect(
            view,
            request,
            identity,
            lambda session, actor: validate_rule_view(session, workspace_id, actor, view),
            status_code=status_code,
        )

    def snapshot_response(view, request, identity, document_id):
        return protect(
            view,
            request,
            identity,
            lambda session, actor: validate_snapshot_view(session, document_id, actor, view),
        )

    @router.get("/workspaces/{workspace_id}/rules", response_model=list[RuleView], responses=errors)
    def list_route(
        workspace_id: UUID,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ):
        def operation():
            with Session(engine) as session:
                active_workspace(session, workspace_id, identity.user_id)
                view = workspace_rules(
                    session, workspace_id, KeyRing.from_settings(request.app.state.settings)
                )
            return rule_response(view, request, identity, workspace_id)

        return guarded(operation)

    @router.post(
        "/workspaces/{workspace_id}/rules",
        response_model=RuleView,
        status_code=201,
        responses=errors,
    )
    def create_route(
        workspace_id: UUID,
        body: RuleInput,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        def operation():
            with Session(engine) as session:
                view = save_rule(
                    session,
                    workspace_id=workspace_id,
                    actor_id=identity.user_id,
                    keys=KeyRing.from_settings(request.app.state.settings),
                    now=datetime.now(UTC),
                    body=body,
                    reauthorize=lambda: current_identity(request),
                )
            return rule_response(view, request, identity, workspace_id, status_code=201)

        return guarded(operation)

    @router.put(
        "/workspaces/{workspace_id}/rules/{rule_id}", response_model=RuleView, responses=errors
    )
    def update_route(
        workspace_id: UUID,
        rule_id: UUID,
        body: RuleUpdate,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        def operation():
            with Session(engine) as session:
                view = save_rule(
                    session,
                    workspace_id=workspace_id,
                    actor_id=identity.user_id,
                    keys=KeyRing.from_settings(request.app.state.settings),
                    now=datetime.now(UTC),
                    body=RuleInput(**body.model_dump(exclude={"expected_version"})),
                    rule_id=rule_id,
                    expected_version=body.expected_version,
                    reauthorize=lambda: current_identity(request),
                )
            return rule_response(view, request, identity, workspace_id)

        return guarded(operation)

    @router.post(
        "/workspaces/{workspace_id}/rules/test", response_model=RuleTestView, responses=errors
    )
    def test_route(
        workspace_id: UUID,
        body: RuleTestInput,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        def operation():
            with Session(engine) as session:
                active_workspace(session, workspace_id, identity.user_id)
            spans = matches(body.text, body.rule, limit=100)
            view = RuleTestView(
                matches=[
                    RuleTestMatch(span=span, text=body.text[span.start : span.end])
                    for span in spans
                ],
                match_count=len(spans),
            )
            return protect(
                view,
                request,
                identity,
                lambda session, actor: active_workspace(session, workspace_id, actor),
            )

        return guarded(operation)

    @router.get("/documents/{document_id}/rules", response_model=RuleSnapshotView, responses=errors)
    def snapshot_route(
        document_id: UUID,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ):
        def operation():
            with Session(engine) as session:
                document = owned_document(session, document_id, identity.user_id, datetime.now(UTC))
                view = snapshot_state(
                    session, document, KeyRing.from_settings(request.app.state.settings)
                )
            return snapshot_response(view, request, identity, document_id)

        return guarded(operation)

    @router.put("/documents/{document_id}/rules", response_model=RuleSnapshotView, responses=errors)
    def refresh_route(
        document_id: UUID,
        body: RefreshRulesInput,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        def operation():
            with Session(engine) as session:
                view = refresh_snapshot(
                    session,
                    document_id,
                    identity.user_id,
                    body.expected,
                    datetime.now(UTC),
                    KeyRing.from_settings(request.app.state.settings),
                    reauthorize=lambda: current_identity(request),
                )
            return snapshot_response(view, request, identity, document_id)

        return guarded(operation)

    return router
