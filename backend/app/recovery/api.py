"""Owner-only, CSRF-protected recovery storage with versioned writes."""

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import ContentUnavailable, DocumentNotFound, WorkspaceAccessDenied
from app.accounts.api import current_identity, mutation_identity
from app.accounts.security import SessionIdentity
from app.db.crypto import ContentKeyUnavailable, ProtectedContentError
from app.db.recovery import RecoverySnapshot
from app.errors import ApiError
from app.intake.api import _keys
from app.recovery.contracts import RecoveryMetadata, RecoveryView, RecoveryWrite
from app.recovery.service import (
    authorize_scope,
    load_snapshot,
    metadata,
    owned_snapshot,
    save_snapshot,
)


@contextmanager
def recovery_transaction(engine: Engine):
    try:
        with Session(engine) as session, session.begin():
            yield session
    except (WorkspaceAccessDenied, DocumentNotFound):
        raise ApiError(404, "recovery_not_found", "Working draft not found.") from None
    except ContentUnavailable:
        raise ApiError(410, "content_expired", "Document content is unavailable.") from None
    except (ContentKeyUnavailable, ProtectedContentError):
        raise ApiError(503, "content_unavailable", "Working draft access is unavailable.") from None


def create_recovery_router(engine: Engine) -> APIRouter:
    router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/recovery", tags=["recovery"])

    @router.get("", response_model=list[RecoveryMetadata])
    def list_route(
        workspace_id: UUID,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
        document_id: UUID | None = None,
    ):
        now = datetime.now(UTC)
        with recovery_transaction(engine) as session:
            authorize_scope(session, workspace_id, identity.user_id, document_id, now)
            rows = session.scalars(
                select(RecoverySnapshot)
                .where(
                    RecoverySnapshot.owner_id == identity.user_id,
                    RecoverySnapshot.workspace_id == workspace_id,
                    RecoverySnapshot.document_id == document_id,
                    RecoverySnapshot.expires_at > now,
                )
                .order_by(RecoverySnapshot.updated_at.desc())
                .limit(20)
            ).all()
            return [metadata(row) for row in rows]

    @router.get("/{snapshot_id}", response_model=RecoveryView)
    def load_route(
        workspace_id: UUID,
        snapshot_id: UUID,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ):
        with recovery_transaction(engine) as session:
            return load_snapshot(
                session,
                workspace_id,
                snapshot_id,
                identity.user_id,
                datetime.now(UTC),
                _keys(request),
            )

    @router.put("/{snapshot_id}", response_model=RecoveryMetadata)
    def save_route(
        workspace_id: UUID,
        snapshot_id: UUID,
        body: RecoveryWrite,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        with recovery_transaction(engine) as session:
            return save_snapshot(
                session,
                workspace_id,
                snapshot_id,
                identity.user_id,
                body,
                datetime.now(UTC),
                _keys(request),
            )

    @router.delete("/{snapshot_id}", status_code=204)
    def delete_route(
        workspace_id: UUID,
        snapshot_id: UUID,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
        expected_version: Annotated[int, Query(ge=1)],
    ):
        with recovery_transaction(engine) as session:
            row = owned_snapshot(
                session, workspace_id, snapshot_id, identity.user_id, datetime.now(UTC)
            )
            if row.version != expected_version:
                raise ApiError(
                    409,
                    "recovery_conflict",
                    "This working draft changed. Recover it before discarding.",
                )
            session.delete(row)
        return Response(status_code=204)

    return router
