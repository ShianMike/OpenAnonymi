"""Member-readable presets and administrator-only changes."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import WorkspaceAccessDenied
from app.accounts.api import current_identity, mutation_identity
from app.accounts.response_boundary import protected_json_response
from app.accounts.security import SessionIdentity
from app.contracts import ErrorResponse, FindingCategory
from app.db.crypto import ContentKeyUnavailable, KeyRing, ProtectedContentError
from app.errors import ApiError
from app.intake.column_rules import ColumnRule
from app.transformations.contracts import CategoryDefault
from app.workspace.presets import (
    PresetExists,
    PresetNotFound,
    PresetRecord,
    PresetVersionConflict,
    list_presets,
    save_preset,
    validate_preset_view,
)


class PresetView(BaseModel):
    id: UUID
    name: str
    categories: list[FindingCategory]
    phone_region: str
    preferred_action: Literal["label", "redact"]
    version: int
    is_default: bool
    category_defaults: dict[FindingCategory, CategoryDefault]
    column_rules: list[ColumnRule]


class PresetInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    categories: list[FindingCategory] = Field(default_factory=list)
    phone_region: str = Field(min_length=2, max_length=2)
    preferred_action: Literal["label", "redact"] = "label"
    is_default: bool = False
    category_defaults: dict[FindingCategory, CategoryDefault] | None = Field(
        default=None, max_length=12
    )
    column_rules: list[ColumnRule] | None = Field(default=None, max_length=50)


class UpdatePresetInput(PresetInput):
    expected_version: int = Field(ge=1)


def _view(record: PresetRecord) -> PresetView:
    return PresetView.model_validate(record, from_attributes=True)


def _save(
    engine: Engine,
    workspace_id: UUID,
    actor_id: UUID,
    body: PresetInput,
    preset_id: UUID | None,
    expected_version: int | None,
    keys: KeyRing,
    reauthorize: Callable[[], object] | None = None,
) -> PresetView:
    try:
        with Session(engine) as session:
            record = save_preset(
                session,
                workspace_id=workspace_id,
                actor_id=actor_id,
                preset_id=preset_id,
                expected_version=expected_version,
                name=body.name,
                categories=set(body.categories),
                phone_region=body.phone_region,
                preferred_action=body.preferred_action,
                is_default=body.is_default,
                now=datetime.now(UTC),
                category_defaults={
                    category.value: choice.model_dump(mode="json")
                    for category, choice in body.category_defaults.items()
                }
                if body.category_defaults is not None
                else None,
                column_rules=[rule.model_dump(mode="json") for rule in body.column_rules]
                if body.column_rules is not None
                else None,
                keys=keys,
                reauthorize=reauthorize,
            )
    except (WorkspaceAccessDenied, PresetNotFound):
        raise ApiError(404, "preset_not_found", "Preset or workspace not found.") from None
    except PresetExists:
        raise ApiError(409, "preset_exists", "A preset with this name already exists.") from None
    except PresetVersionConflict:
        raise ApiError(
            409, "preset_conflict", "This preset changed. Reload before saving."
        ) from None
    except (ContentKeyUnavailable, ProtectedContentError):
        raise ApiError(503, "content_unavailable", "Content access is unavailable.") from None
    except ValueError as exc:
        raise ApiError(422, "invalid_preset", str(exc)) from None
    return _view(record)


def _keys(request: Request):
    try:
        return KeyRing.from_settings(request.app.state.settings)
    except ContentKeyUnavailable:
        raise ApiError(503, "content_unavailable", "Content access is unavailable.") from None


def create_presets_router(engine: Engine) -> APIRouter:
    router = APIRouter(prefix="/api/v1/workspaces", tags=["presets"])
    errors = {404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}}

    def protected(view, request, identity, workspace_id, *, status_code=200):
        def authorize(current):
            with Session(engine) as session:
                validate_preset_view(session, workspace_id, current.user_id, view)

        try:
            return protected_json_response(
                view, request, identity, authorize, status_code=status_code
            )
        except WorkspaceAccessDenied:
            raise ApiError(404, "workspace_not_found", "Workspace not found.") from None

    @router.get("/{workspace_id}/presets", response_model=list[PresetView], responses=errors)
    def presets_route(
        workspace_id: UUID,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ) -> list[PresetView]:
        try:
            with Session(engine) as session:
                records = list_presets(
                    session,
                    workspace_id=workspace_id,
                    actor_id=identity.user_id,
                    keys=_keys(request),
                )
        except WorkspaceAccessDenied:
            raise ApiError(404, "workspace_not_found", "Workspace not found.") from None
        except (ContentKeyUnavailable, ProtectedContentError):
            raise ApiError(503, "content_unavailable", "Content access is unavailable.") from None
        return protected([_view(record) for record in records], request, identity, workspace_id)

    @router.post(
        "/{workspace_id}/presets",
        response_model=PresetView,
        status_code=201,
        responses=errors,
    )
    def create_preset_route(
        workspace_id: UUID,
        body: PresetInput,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> PresetView:
        view = _save(
            engine,
            workspace_id,
            identity.user_id,
            body,
            None,
            None,
            _keys(request),
            lambda: current_identity(request),
        )
        return protected(view, request, identity, workspace_id, status_code=201)

    @router.put("/{workspace_id}/presets/{preset_id}", response_model=PresetView, responses=errors)
    def update_preset_route(
        workspace_id: UUID,
        preset_id: UUID,
        body: UpdatePresetInput,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> PresetView:
        view = _save(
            engine,
            workspace_id,
            identity.user_id,
            body,
            preset_id,
            body.expected_version,
            _keys(request),
            lambda: current_identity(request),
        )
        return protected(view, request, identity, workspace_id)

    return router
