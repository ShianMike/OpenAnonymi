"""Authenticated source intake, saved drafts, and immutable source edits."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.accounts.access import WorkspaceAccessDenied, active_workspace
from app.accounts.api import current_identity, mutation_identity
from app.accounts.security import SessionIdentity
from app.contracts import (
    AUTOMATIC_CATEGORIES,
    ConflictResponse,
    DocumentStatus,
    ErrorResponse,
    FindingCategory,
    VersionRef,
)
from app.db.crypto import ContentKeyUnavailable, KeyRing, ProtectedContentError
from app.db.repository import (
    ContentUnavailable,
    DocumentNotFound,
    LoadedSource,
    SavedDocument,
    StorageValidationError,
    VersionConflict,
    append_source_revision,
    create_document,
    load_current_source,
)
from app.errors import ApiError
from app.intake.csv_contracts import (
    ColumnRulesRequest,
    CsvInfo,
    CsvSettingsRequest,
    CsvSettingsView,
)
from app.intake.csv_service import change_csv_settings
from app.intake.csv_structure import CsvError, Delimiter, Header
from app.intake.imports import MAX_FILE_BYTES, extract_import
from app.intake.validation import SourceValidationError
from app.transformations.contracts import CategoryDefault
from app.workspace.presets import PresetNotFound


class SourceView(BaseModel):
    workspace_id: UUID
    can_edit: bool
    version: VersionRef
    text: str
    expires_at: datetime
    status: DocumentStatus
    title: str | None
    categories: list[FindingCategory]
    phone_region: str
    language: str
    preset_id: UUID | None
    preset_version: int | None
    preferred_action: Literal["label", "redact"]
    category_defaults: dict[FindingCategory, CategoryDefault]
    structure: Literal["kept", "simplified", "none"]
    csv: CsvInfo | None = None


class IntakeDefaultsView(BaseModel):
    workspace_id: UUID
    content_retention_days: int
    current_time: datetime


class CreateDraftRequest(BaseModel):
    workspace_id: UUID
    source: str
    title: str | None = Field(default=None, max_length=200)
    categories: list[FindingCategory] = Field(
        default_factory=lambda: [FindingCategory.EMAIL, FindingCategory.PHONE]
    )
    phone_region: str = Field(default="PH", min_length=2, max_length=2)
    retention_days: int | None = Field(default=None, ge=1, le=30)
    preset_id: UUID | None = None
    language: str = Field(default="en", min_length=2, max_length=2)


class EditSourceRequest(BaseModel):
    expected: VersionRef
    source: str


class SavedDraftView(BaseModel):
    version: VersionRef
    expires_at: datetime
    status: DocumentStatus
    structure: Literal["kept", "simplified", "none"]


def _source_view(source: LoadedSource) -> SourceView:
    return SourceView(
        workspace_id=source.workspace_id,
        can_edit=source.can_edit,
        version=source.version,
        text=source.text,
        expires_at=source.expires_at,
        status=source.status,
        title=source.title,
        categories=list(source.categories),
        phone_region=source.phone_region,
        language=source.language,
        preset_id=source.preset_id,
        preset_version=source.preset_version,
        preferred_action=source.preferred_action,
        category_defaults=source.category_defaults,
        structure=source.structure,
        csv=source.csv,
    )


def _saved_view(saved: SavedDocument) -> SavedDraftView:
    return SavedDraftView(
        version=saved.version,
        expires_at=saved.expires_at,
        status=saved.status,
        structure=saved.structure,
    )


def _keys(request: Request) -> KeyRing:
    try:
        return KeyRing.from_settings(request.app.state.settings)
    except ContentKeyUnavailable:
        raise ApiError(503, "content_unavailable", "Content access is unavailable.") from None


def _categories(values: list[FindingCategory]) -> set[FindingCategory]:
    categories = set(values)
    if not categories.issubset(AUTOMATIC_CATEGORIES):
        raise ApiError(
            422, "invalid_categories", "Choose supported automatic suggestion categories."
        )
    return categories


def _input_error(exc: ValueError) -> ApiError:
    return ApiError(422, exc.code if isinstance(exc, CsvError) else "invalid_source", str(exc))


def _conflict(exc: VersionConflict) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content=ConflictResponse(current_version=exc.current).model_dump(mode="json"),
    )


def _load_owned_source(
    engine: Engine, request: Request, document_id: UUID, actor_id: UUID
) -> LoadedSource:
    keys = _keys(request)
    try:
        with Session(engine) as session:
            return load_current_source(
                session,
                document_id=document_id,
                actor_id=actor_id,
                keys=keys,
                now=datetime.now(UTC),
            )
    except DocumentNotFound:
        raise ApiError(404, "document_not_found", "Document not found.") from None
    except ContentUnavailable:
        raise ApiError(410, "content_expired", "Document content is unavailable.") from None
    except (ContentKeyUnavailable, ProtectedContentError):
        raise ApiError(503, "content_unavailable", "Content access is unavailable.") from None


def create_intake_router(engine: Engine) -> APIRouter:
    router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

    @router.get(
        "/intake-defaults/{workspace_id}",
        response_model=IntakeDefaultsView,
        responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def intake_defaults_route(
        workspace_id: UUID,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ) -> IntakeDefaultsView:
        try:
            with Session(engine) as session:
                workspace = active_workspace(session, workspace_id, identity.user_id)
                retention_days = workspace.content_retention_days
        except WorkspaceAccessDenied:
            raise ApiError(404, "workspace_not_found", "Workspace not found.") from None
        return IntakeDefaultsView(
            workspace_id=workspace_id,
            content_retention_days=retention_days,
            current_time=datetime.now(UTC),
        )

    @router.post(
        "",
        response_model=SavedDraftView,
        status_code=201,
        responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def create_pasted_draft_route(
        body: CreateDraftRequest,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> SavedDraftView:
        keys = _keys(request)
        now = datetime.now(UTC)
        try:
            with Session(engine) as session:
                saved = create_document(
                    session,
                    owner_id=identity.user_id,
                    workspace_id=body.workspace_id,
                    source=body.source,
                    title=body.title,
                    categories=_categories(body.categories),
                    phone_region=body.phone_region,
                    language=body.language,
                    keys=keys,
                    now=now,
                    requested_expiry=(now + timedelta(days=body.retention_days))
                    if body.retention_days is not None
                    else None,
                    preset_id=body.preset_id,
                )
        except DocumentNotFound:
            raise ApiError(404, "workspace_not_found", "Workspace not found.") from None
        except PresetNotFound:
            raise ApiError(404, "preset_not_found", "Preset not found.") from None
        except (SourceValidationError, StorageValidationError) as exc:
            raise _input_error(exc) from None
        return _saved_view(saved)

    @router.post(
        "/from-file",
        response_model=SavedDraftView,
        status_code=201,
        responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    async def create_file_draft_route(
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
        workspace_id: Annotated[UUID, Form()],
        file: Annotated[UploadFile, File()],
        title: Annotated[str | None, Form(max_length=200)] = None,
        categories: Annotated[str, Form()] = "email,phone",
        phone_region: Annotated[str, Form(min_length=2, max_length=2)] = "PH",
        language: Annotated[str, Form(min_length=2, max_length=2)] = "en",
        retention_days: Annotated[int | None, Form(ge=1, le=30)] = None,
        preset_id: Annotated[UUID | None, Form()] = None,
        csv_delimiter: Annotated[Delimiter, Form()] = "auto",
        csv_header: Annotated[Header, Form()] = "auto",
    ) -> SavedDraftView:
        # FastAPI has already parsed the multipart body. Reject extra file parts and
        # bound the bytes read from the uploaded file before decoding.
        form = await request.form()
        if (
            len(form.getlist("file")) != 1
            or sum(isinstance(value, StarletteUploadFile) for _name, value in form.multi_items())
            != 1
        ):
            raise ApiError(422, "invalid_file", "Choose exactly one TXT, CSV, PDF or Word DOCX file.")
        try:
            with Session(engine) as session:
                active_workspace(session, workspace_id, identity.user_id)
        except WorkspaceAccessDenied:
            raise ApiError(404, "workspace_not_found", "Workspace not found.") from None
        if file.size is not None and file.size > MAX_FILE_BYTES:
            raise ApiError(422, "invalid_file", "File exceeds the 8 MiB import limit.")
        raw = await file.read(MAX_FILE_BYTES + 1)
        try:
            imported = await run_in_threadpool(
                extract_import, file.filename, raw, csv_delimiter, csv_header
            )
            validated = imported.source
            parsed_categories = [
                FindingCategory(value.strip()) for value in categories.split(",") if value.strip()
            ]
        except (SourceValidationError, ValueError) as exc:
            if isinstance(exc, SourceValidationError):
                raise _input_error(exc) from None
            raise ApiError(
                422, "invalid_categories", "Choose supported automatic suggestion categories."
            ) from None
        keys = _keys(request)
        now = datetime.now(UTC)
        try:
            with Session(engine) as session:
                saved = create_document(
                    session,
                    owner_id=identity.user_id,
                    workspace_id=workspace_id,
                    source=validated.text,
                    title=title,
                    categories=_categories(parsed_categories),
                    phone_region=phone_region,
                    language=language,
                    keys=keys,
                    now=now,
                    requested_expiry=(now + timedelta(days=retention_days))
                    if retention_days is not None
                    else None,
                    preset_id=preset_id,
                    layout=imported.layout,
                    layout_kind=imported.format,
                    validated_source=imported.source,
                )
        except DocumentNotFound:
            raise ApiError(404, "workspace_not_found", "Workspace not found.") from None
        except PresetNotFound:
            raise ApiError(404, "preset_not_found", "Preset not found.") from None
        except (SourceValidationError, StorageValidationError) as exc:
            raise _input_error(exc) from None
        except (ContentKeyUnavailable, ProtectedContentError):
            raise ApiError(503, "content_unavailable", "Content access is unavailable.") from None
        return _saved_view(saved)

    def _csv_mutation(document_id, body, request, identity, *, column_rules=False):
        try:
            result = change_csv_settings(
                engine,
                document_id=document_id,
                actor_id=identity.user_id,
                expected_settings_version=body.expected_settings_version,
                delimiter=None if column_rules else body.delimiter,
                has_header=None if column_rules else body.has_header,
                rules=[rule.model_dump(mode="json") for rule in body.rules]
                if column_rules
                else None,
                keys=_keys(request),
                now=datetime.now(UTC),
            )
            return CsvSettingsView.model_validate(result)
        except DocumentNotFound:
            raise ApiError(404, "document_not_found", "Document not found.") from None
        except ContentUnavailable:
            raise ApiError(410, "content_expired", "Document content is unavailable.") from None
        except VersionConflict as exc:
            return _conflict(exc)
        except SourceValidationError as exc:
            raise _input_error(exc) from None
        except (ContentKeyUnavailable, ProtectedContentError):
            raise ApiError(503, "content_unavailable", "Content access is unavailable.") from None

    @router.get("/{document_id}/column-rules", response_model=CsvSettingsView)
    @router.get("/{document_id}/csv-settings", response_model=CsvSettingsView)
    def csv_settings_route(
        document_id: UUID,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ):
        source = _load_owned_source(engine, request, document_id, identity.user_id)
        if source.csv is None:
            raise ApiError(422, "csv_required", "These settings apply to an imported CSV document.")
        return CsvSettingsView(version=source.version, **source.csv)

    @router.put(
        "/{document_id}/csv-settings",
        response_model=CsvSettingsView,
        responses={409: {"model": ConflictResponse}, 422: {"model": ErrorResponse}},
    )
    def change_csv_settings_route(
        document_id: UUID,
        body: CsvSettingsRequest,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        return _csv_mutation(document_id, body, request, identity)

    @router.put(
        "/{document_id}/column-rules",
        response_model=CsvSettingsView,
        responses={409: {"model": ConflictResponse}, 422: {"model": ErrorResponse}},
    )
    def column_rules_route(
        document_id: UUID,
        body: ColumnRulesRequest,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        return _csv_mutation(document_id, body, request, identity, column_rules=True)

    @router.get(
        "/{document_id}/source",
        response_model=SourceView,
        responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def source_route(
        document_id: UUID,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ) -> SourceView:
        source = _load_owned_source(engine, request, document_id, identity.user_id)
        return _source_view(source)

    @router.put(
        "/{document_id}/source",
        response_model=SavedDraftView,
        responses={409: {"model": ConflictResponse}, 422: {"model": ErrorResponse}},
    )
    def edit_source_route(
        document_id: UUID,
        body: EditSourceRequest,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ) -> SavedDraftView | JSONResponse:
        keys = _keys(request)
        try:
            with Session(engine) as session:
                saved = append_source_revision(
                    session,
                    document_id=document_id,
                    actor_id=identity.user_id,
                    expected=body.expected,
                    source=body.source,
                    keys=keys,
                    now=datetime.now(UTC),
                )
        except DocumentNotFound:
            raise ApiError(404, "document_not_found", "Document not found.") from None
        except ContentUnavailable:
            raise ApiError(410, "content_expired", "Document content is unavailable.") from None
        except VersionConflict as exc:
            return _conflict(exc)
        except SourceValidationError as exc:
            raise _input_error(exc) from None
        except (ContentKeyUnavailable, ProtectedContentError):
            raise ApiError(503, "content_unavailable", "Content access is unavailable.") from None
        return _saved_view(saved)

    @router.get(
        "/{document_id}/revisions/{revision_id}/source",
        response_model=SourceView,
        responses={
            401: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            410: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    def current_source_route(
        document_id: UUID,
        revision_id: UUID,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ) -> SourceView:
        source = _load_owned_source(engine, request, document_id, identity.user_id)
        if source.version.source_revision_id != revision_id:
            raise ApiError(404, "revision_not_found", "Revision not found.")
        return _source_view(source)

    return router
