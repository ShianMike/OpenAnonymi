from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.accounts.access import WorkspaceAccessDenied, active_workspace
from app.accounts.api import mutation_identity
from app.accounts.response_boundary import protected_json_response
from app.accounts.security import SessionIdentity
from app.contracts import ErrorResponse
from app.errors import ApiError
from app.intake.access import require_current_intake_access
from app.intake.imports import MAX_FILE_BYTES, ImportedPagePreview, extract_import
from app.intake.validation import SourceValidationError


class ImportPreview(BaseModel):
    text: str
    format: str
    pages: int | None
    code_points: int
    utf8_bytes: int
    notes: list[str]
    page_previews: list[ImportedPagePreview] = Field(default_factory=list)


def create_import_router(engine: Engine):
    router = APIRouter(prefix="/api/v1/documents", tags=["imports"])

    @router.post(
        "/import-preview",
        response_model=ImportPreview,
        responses={code: {"model": ErrorResponse} for code in (401, 404, 422)},
    )
    async def preview_route(
        request: Request,
        file: Annotated[UploadFile, File()],
        workspace_id: Annotated[UUID, Form()],
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        try:
            with Session(engine) as session:
                active_workspace(session, workspace_id, identity.user_id)
        except WorkspaceAccessDenied:
            raise ApiError(404, "workspace_not_found", "Workspace not found.") from None
        form = await request.form()
        if (
            len(form.getlist("file")) != 1
            or sum(isinstance(value, StarletteUploadFile) for _, value in form.multi_items()) != 1
        ):
            raise ApiError(422, "invalid_file", "Choose exactly one file.")
        if file.size is not None and file.size > MAX_FILE_BYTES:
            raise ApiError(422, "invalid_file", "File exceeds the 8 MiB import limit.")
        raw = await file.read(MAX_FILE_BYTES + 1)
        try:
            result = await run_in_threadpool(
                extract_import, file.filename, raw, include_previews=True
            )
        except SourceValidationError as exc:
            raise ApiError(422, "invalid_file", str(exc)) from None
        require_current_intake_access(engine, request, workspace_id)
        view = ImportPreview(
            text=result.source.text,
            format=result.format,
            pages=result.pages,
            code_points=result.source.code_points,
            utf8_bytes=result.source.utf8_bytes,
            notes=list(result.notes),
            page_previews=list(result.page_previews),
        )
        return await run_in_threadpool(
            protected_json_response, view, request, identity,
            lambda current: require_current_intake_access(engine, request, workspace_id),
        )

    return router
