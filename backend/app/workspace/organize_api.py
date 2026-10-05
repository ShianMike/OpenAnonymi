"""Authenticated title search, personal document flags and bounded bulk actions."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import (
    ContentUnavailable,
    DocumentNotFound,
    WorkspaceAccessDenied,
    active_workspace,
    owned_document_record,
    review_document,
)
from app.accounts.api import mutation_identity
from app.accounts.limits import AttemptLimiter
from app.accounts.response_boundary import protected_json_response
from app.accounts.security import SessionIdentity
from app.config import Settings
from app.contracts import ErrorResponse
from app.db.crypto import ContentKeyUnavailable, KeyRing, ProtectedContentError
from app.db.document_preferences import DocumentPreference
from app.errors import ApiError
from app.workspace.organize import (
    BulkDocumentOutcome,
    BulkDocumentsRequest,
    BulkDocumentsView,
    DocumentPreferenceRequest,
    DocumentPreferenceView,
    DocumentSearchRequest,
    DocumentSearchView,
    delete_owned_document,
    search_documents,
    update_preference,
)
from app.workspace.private_titles import validate_title_view


def create_organize_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["document organization"])
    search_limit = AttemptLimiter(
        engine,
        settings,
        scope="document_search",
        maximum=60,
        window_seconds=60,
        network_scope=False,
    )
    bulk_limit = AttemptLimiter(
        engine, settings, scope="document_bulk", maximum=10, window_seconds=60, network_scope=False
    )
    preference_limit = AttemptLimiter(
        engine,
        settings,
        scope="document_preference",
        maximum=120,
        window_seconds=60,
        network_scope=False,
    )
    errors = {code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 410, 422, 429, 503)}

    def take(limiter, identity):
        if not limiter.take(str(identity.user_id)):
            raise ApiError(429, "action_limited", "Please wait a minute and try again.")

    def protected_flags(view, request, identity):
        def authorize(current):
            with Session(engine) as session:
                rows = view.outcomes if isinstance(view, BulkDocumentsView) else [view]
                for row in rows:
                    if isinstance(row, BulkDocumentOutcome) and row.outcome != "updated":
                        if row.outcome == "deleted":
                            owned_document_record(session, row.document_id, current.user_id)
                        continue
                    review_document(session, row.document_id, current.user_id, datetime.now(UTC))
                    flag = session.get(DocumentPreference, (current.user_id, row.document_id))
                    if (row.favorite, row.pinned) != (bool(flag and flag.favorite), bool(flag and flag.pinned)):
                        raise ApiError(409, "preferences_changed", "Document preferences changed. Reload to continue.")
        return protected_json_response(view, request, identity, authorize)

    @router.post("/search/documents", response_model=DocumentSearchView, responses=errors)
    def search_route(
        body: DocumentSearchRequest,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        take(search_limit, identity)
        try:
            keys = KeyRing.from_settings(settings)
            result = search_documents(engine, actor_id=identity.user_id, body=body, keys=keys)

            def authorize(current):
                with Session(engine) as session:
                    validate_title_view(
                        session, current.user_id, result, keys, workspace_id=body.workspace_id
                    )

            return protected_json_response(result, request, identity, authorize)
        except (WorkspaceAccessDenied, DocumentNotFound):
            raise ApiError(404, "workspace_not_found", "Workspace not found.") from None
        except ContentUnavailable:
            raise ApiError(410, "content_expired", "Document content is unavailable.") from None
        except (ContentKeyUnavailable, ProtectedContentError):
            raise ApiError(503, "content_unavailable", "Document titles are unavailable.") from None

    @router.patch(
        "/documents/{document_id}/preferences",
        response_model=DocumentPreferenceView,
        responses=errors,
    )
    def preference_route(
        document_id: UUID,
        body: DocumentPreferenceRequest,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        take(preference_limit, identity)
        try:
            view = update_preference(
                engine,
                document_id=document_id,
                actor_id=identity.user_id,
                body=body,
                authorize=lambda: mutation_identity(request),
            )
            return protected_flags(view, request, identity)
        except DocumentNotFound:
            raise ApiError(404, "document_not_found", "Document not found.") from None
        except ContentUnavailable:
            raise ApiError(410, "content_expired", "Document content is unavailable.") from None

    @router.post(
        "/workspaces/{workspace_id}/documents/bulk",
        response_model=BulkDocumentsView,
        responses=errors,
    )
    def bulk_route(
        workspace_id: UUID,
        body: BulkDocumentsRequest,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        with Session(engine) as session:
            try:
                active_workspace(session, workspace_id, identity.user_id)
            except WorkspaceAccessDenied:
                raise ApiError(404, "workspace_not_found", "Workspace not found.") from None
        take(bulk_limit, identity)
        outcomes, session_ended = [], False
        for document_id in body.document_ids:
            if session_ended:
                outcomes.append(
                    BulkDocumentOutcome(document_id=document_id, outcome="session_ended")
                )
                continue
            try:
                mutation_identity(request)
                if body.action == "delete":
                    delete_owned_document(
                        engine,
                        document_id=document_id,
                        actor_id=identity.user_id,
                        workspace_id=workspace_id,
                        authorize=lambda: mutation_identity(request),
                    )
                    result = BulkDocumentOutcome(document_id=document_id, outcome="deleted")
                else:
                    field = "favorite" if body.action in ("favorite", "unfavorite") else "pinned"
                    flags = update_preference(
                        engine,
                        document_id=document_id,
                        actor_id=identity.user_id,
                        body=DocumentPreferenceRequest(
                            **{field: body.action in ("favorite", "pin")}
                        ),
                        workspace_id=workspace_id,
                        authorize=lambda: mutation_identity(request),
                    )
                    result = BulkDocumentOutcome(
                        document_id=document_id,
                        outcome="updated",
                        favorite=flags.favorite,
                        pinned=flags.pinned,
                    )
            except DocumentNotFound:
                result = BulkDocumentOutcome(document_id=document_id, outcome="not_found")
            except ContentUnavailable:
                result = BulkDocumentOutcome(document_id=document_id, outcome="unavailable")
            except ApiError as exc:
                if exc.status_code != 401:
                    raise
                session_ended = True
                result = BulkDocumentOutcome(document_id=document_id, outcome="session_ended")
            outcomes.append(result)
        try:
            return protected_flags(BulkDocumentsView(outcomes=outcomes), request, identity)
        except DocumentNotFound:
            raise ApiError(404, "document_not_found", "Document not found.") from None
        except ContentUnavailable:
            raise ApiError(410, "content_expired", "Document content is unavailable.") from None

    return router
