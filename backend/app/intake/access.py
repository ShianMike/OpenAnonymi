"""Refresh session and membership after slow transient file processing."""

from uuid import UUID

from fastapi import Request
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import WorkspaceAccessDenied, active_workspace
from app.accounts.api import current_identity
from app.errors import ApiError


def require_current_intake_access(engine: Engine, request: Request, workspace_id: UUID):
    identity = current_identity(request)
    try:
        with Session(engine) as session:
            active_workspace(session, workspace_id, identity.user_id)
    except WorkspaceAccessDenied:
        raise ApiError(404, "workspace_not_found", "Workspace not found.") from None
    return identity
