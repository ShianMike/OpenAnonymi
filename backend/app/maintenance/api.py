"""Hidden bearer maintenance route and administrator-only content-free health."""

import hashlib
import hmac
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.accounts.access import WorkspaceAccessDenied
from app.accounts.api import current_identity, request_client_ip
from app.accounts.limits import AttemptLimiter
from app.accounts.security import SessionIdentity
from app.config import Settings
from app.contracts import ErrorResponse
from app.errors import ApiError
from app.maintenance.service import load_cleanup_health, run_cleanup


class MaintenanceView(BaseModel):
    documents_purged: int
    activity_removed: int
    expired_rows_removed: int
    more_remaining: bool
    duration_ms: int
    started_at: datetime
    finished_at: datetime


class CleanupHealthView(BaseModel):
    last_success_at: datetime | None
    last_failure_at: datetime | None
    overdue: bool
    documents_awaiting_purge: int
    checked_at: datetime


def create_maintenance_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["cleanup health"])
    denied = AttemptLimiter(
        engine, settings, scope="maintenance_denied", maximum=30, window_seconds=3600
    )
    runs = AttemptLimiter(
        engine, settings, scope="maintenance", maximum=12, window_seconds=3600, network_scope=False
    )

    @router.post("/maintenance/cleanup", response_model=MaintenanceView, include_in_schema=False)
    def cleanup_route(request: Request) -> MaintenanceView:
        if settings.maintenance_token_sha256 is None:
            raise ApiError(404, "not_found", "Not found.")
        header = request.headers.get("Authorization", "")
        scheme, separator, token = header.partition(" ")
        if (
            len(header.encode("utf-8")) > 512
            or scheme.lower() != "bearer"
            or not separator
            or not token
            or any(c.isspace() for c in token)
        ):
            raise ApiError(401, "maintenance_denied", "Maintenance access denied.")
        if not hmac.compare_digest(
            hashlib.sha256(token.encode("utf-8")).hexdigest(),
            settings.maintenance_token_sha256.get_secret_value(),
        ):
            if not denied.take(request_client_ip(request)):
                raise ApiError(
                    429, "maintenance_limited", "Maintenance attempts are limited. Try later."
                )
            raise ApiError(401, "maintenance_denied", "Maintenance access denied.")
        if not runs.take("global"):
            raise ApiError(429, "maintenance_limited", "Maintenance is limited. Try later.")
        try:
            return MaintenanceView(**asdict(run_cleanup(engine, trigger="endpoint")))
        except SQLAlchemyError:
            raise ApiError(
                503, "maintenance_unavailable", "Maintenance is temporarily unavailable."
            ) from None

    @router.get(
        "/workspaces/{workspace_id}/cleanup-health",
        response_model=CleanupHealthView,
        responses={404: {"model": ErrorResponse}},
    )
    def health_route(
        workspace_id: UUID, identity: Annotated[SessionIdentity, Depends(current_identity)]
    ) -> CleanupHealthView:
        try:
            result = load_cleanup_health(
                engine, workspace_id=workspace_id, actor_id=identity.user_id, now=datetime.now(UTC)
            )
        except WorkspaceAccessDenied:
            raise ApiError(404, "workspace_not_found", "Workspace not found.") from None
        return CleanupHealthView(**asdict(result))

    return router
