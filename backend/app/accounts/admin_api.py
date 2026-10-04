"""Administrator-only workspace membership and default-setting routes."""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import WorkspaceAccessDenied
from app.accounts.api import current_identity, mutation_identity
from app.accounts.email_rules import EmailRuleError
from app.accounts.memberships import (
    LastAdministrator,
    MemberExists,
    MemberNotFound,
    MemberRecord,
    WorkspaceRecord,
    WorkspaceVersionConflict,
    change_member_role,
    get_workspace_settings,
    invite_member,
    list_members,
    restore_member,
    revoke_member,
    update_workspace_settings,
)
from app.accounts.recovery import RecoveryDeliveryError
from app.accounts.reset_second_factor import reset_factor
from app.accounts.second_factor import FactorError
from app.accounts.second_factor_api import factor_failure
from app.accounts.security import SessionIdentity
from app.accounts.security_notices import deliver_notice
from app.contracts import ErrorResponse, WorkspaceRole
from app.errors import ApiError


class MemberView(BaseModel):
    user_id: UUID
    email: str
    role: WorkspaceRole
    revoked_at: datetime | None
    disabled_at: datetime | None


class WorkspaceSettingsView(BaseModel):
    id: UUID
    name: str
    content_retention_days: int
    activity_retention_days: int
    settings_version: int
    require_second_factor: bool
    members_without_second_factor: int
    approval_policy: Literal["owner_choice", "always"]
    active_member_count: int


class InviteMemberRequest(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    role: WorkspaceRole = WorkspaceRole.MEMBER


class ChangeRoleRequest(BaseModel):
    role: WorkspaceRole


class UpdateWorkspaceSettingsRequest(BaseModel):
    expected_version: int = Field(ge=1)
    content_retention_days: int = Field(ge=1, le=30)
    activity_retention_days: int = Field(ge=1, le=365)
    require_second_factor: bool | None = None
    approval_policy: Literal["owner_choice", "always"] | None = None


def _member_view(record: MemberRecord) -> MemberView:
    return MemberView(
        user_id=record.user_id,
        email=record.email,
        role=record.role,
        revoked_at=record.revoked_at,
        disabled_at=record.disabled_at,
    )


def _settings_view(record: WorkspaceRecord) -> WorkspaceSettingsView:
    return WorkspaceSettingsView(
        id=record.id,
        name=record.name,
        content_retention_days=record.content_retention_days,
        activity_retention_days=record.activity_retention_days,
        settings_version=record.settings_version,
        require_second_factor=record.require_second_factor,
        members_without_second_factor=record.members_without_second_factor,
        approval_policy=record.approval_policy,
        active_member_count=record.active_member_count,
    )


def _raise_access_error(exc: Exception) -> None:
    if isinstance(exc, FactorError):
        raise ApiError(exc.status, exc.code, exc.message) from None
    if isinstance(exc, WorkspaceAccessDenied):
        raise ApiError(404, "workspace_not_found", "Workspace not found.") from None
    if isinstance(exc, MemberNotFound):
        raise ApiError(404, "member_not_found", "Member not found.") from None
    if isinstance(exc, MemberExists):
        raise ApiError(409, "member_exists", "This account already exists.") from None
    if isinstance(exc, LastAdministrator):
        raise ApiError(409, "last_administrator", str(exc)) from None
    if isinstance(exc, WorkspaceVersionConflict):
        raise ApiError(409, "settings_conflict", str(exc)) from None
    if isinstance(exc, RecoveryDeliveryError):
        raise ApiError(
            503, "invitation_delivery_failed", "Invitation email could not be sent."
        ) from None
    if isinstance(exc, ValueError):
        raise ApiError(422, "invalid_membership", "Check the submitted values.") from None
    raise exc


def create_admin_router(engine: Engine) -> APIRouter:
    router = APIRouter(prefix="/api/v1/workspaces", tags=["workspace administration"])
    errors = {
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    }

    @router.get("/{workspace_id}/members", response_model=list[MemberView], responses=errors)
    def members_route(
        workspace_id: UUID,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ) -> list[MemberView]:
        try:
            with Session(engine) as session:
                records = list_members(
                    session, workspace_id=workspace_id, actor_id=identity.user_id
                )
        except WorkspaceAccessDenied as exc:
            _raise_access_error(exc)
        return [_member_view(record) for record in records]

    @router.post(
        "/{workspace_id}/members/invitations",
        response_model=MemberView,
        status_code=201,
        responses=errors | {503: {"model": ErrorResponse}},
    )
    def invite_route(
        workspace_id: UUID,
        body: InviteMemberRequest,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> MemberView:
        try:
            with Session(engine) as session:
                get_workspace_settings(
                    session, workspace_id=workspace_id, actor_id=identity.user_id
                )
        except WorkspaceAccessDenied as exc:
            _raise_access_error(exc)
        mailer = request.app.state.recovery_mailer
        if mailer is None:
            raise ApiError(503, "invitations_unavailable", "Invitation email is not configured.")
        try:
            with Session(engine) as session:
                record = invite_member(
                    session,
                    workspace_id=workspace_id,
                    actor_id=identity.user_id,
                    email=body.email,
                    role=body.role,
                    mailer=mailer,
                    settings=request.app.state.settings,
                    now=datetime.now(UTC),
                )
        except EmailRuleError as exc:
            raise ApiError(exc.status, exc.code, exc.message) from None
        except (WorkspaceAccessDenied, MemberExists, RecoveryDeliveryError, ValueError) as exc:
            _raise_access_error(exc)
        return _member_view(record)

    @router.patch(
        "/{workspace_id}/members/{user_id}/role", response_model=MemberView, responses=errors
    )
    def role_route(
        workspace_id: UUID,
        user_id: UUID,
        body: ChangeRoleRequest,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> MemberView:
        try:
            with Session(engine) as session:
                record = change_member_role(
                    session,
                    workspace_id=workspace_id,
                    actor_id=identity.user_id,
                    user_id=user_id,
                    role=body.role,
                )
        except (WorkspaceAccessDenied, MemberNotFound, LastAdministrator) as exc:
            _raise_access_error(exc)
        return _member_view(record)

    @router.post(
        "/{workspace_id}/members/{user_id}/revoke", response_model=MemberView, responses=errors
    )
    def revoke_route(
        workspace_id: UUID,
        user_id: UUID,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> MemberView:
        try:
            with Session(engine) as session:
                record = revoke_member(
                    session,
                    workspace_id=workspace_id,
                    actor_id=identity.user_id,
                    user_id=user_id,
                    now=datetime.now(UTC),
                )
        except (WorkspaceAccessDenied, MemberNotFound, LastAdministrator) as exc:
            _raise_access_error(exc)
        return _member_view(record)

    @router.post(
        "/{workspace_id}/members/{user_id}/restore", response_model=MemberView, responses=errors
    )
    def restore_route(
        workspace_id: UUID,
        user_id: UUID,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> MemberView:
        try:
            with Session(engine) as session:
                record = restore_member(
                    session,
                    workspace_id=workspace_id,
                    actor_id=identity.user_id,
                    user_id=user_id,
                )
        except (WorkspaceAccessDenied, MemberNotFound) as exc:
            _raise_access_error(exc)
        return _member_view(record)

    @router.get("/{workspace_id}/settings", response_model=WorkspaceSettingsView, responses=errors)
    def settings_route(
        workspace_id: UUID,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ) -> WorkspaceSettingsView:
        try:
            with Session(engine) as session:
                record = get_workspace_settings(
                    session, workspace_id=workspace_id, actor_id=identity.user_id
                )
        except WorkspaceAccessDenied as exc:
            _raise_access_error(exc)
        return _settings_view(record)

    @router.put("/{workspace_id}/settings", response_model=WorkspaceSettingsView, responses=errors)
    def update_settings_route(
        workspace_id: UUID,
        body: UpdateWorkspaceSettingsRequest,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> WorkspaceSettingsView:
        try:
            with Session(engine) as session:
                record = update_workspace_settings(
                    session,
                    workspace_id=workspace_id,
                    actor_id=identity.user_id,
                    expected_version=body.expected_version,
                    content_retention_days=body.content_retention_days,
                    activity_retention_days=body.activity_retention_days,
                    require_second_factor=body.require_second_factor,
                    approval_policy=body.approval_policy,
                )
        except (WorkspaceAccessDenied, WorkspaceVersionConflict, FactorError, ValueError) as exc:
            _raise_access_error(exc)
        return _settings_view(record)

    @router.post(
        "/{workspace_id}/members/{user_id}/second-factor/reset", status_code=204, responses=errors
    )
    def reset_route(
        workspace_id: UUID,
        user_id: UUID,
        request: Request,
        background: BackgroundTasks,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        try:
            delivered = reset_factor(
                engine,
                user_id,
                datetime.now(UTC),
                actor_id=identity.user_id,
                workspace_id=workspace_id,
                actor_session_id=identity.session_id,
            )
            for notice in delivered:
                background.add_task(deliver_notice, request.app.state.recovery_mailer, notice)
            return Response(status_code=204, background=background)
        except FactorError as error:
            return factor_failure(error, request)
        except WorkspaceAccessDenied as error:
            _raise_access_error(error)

    return router
