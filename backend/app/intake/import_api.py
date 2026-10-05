from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
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
from app.intake.csv_contracts import CsvInfo
from app.intake.csv_structure import CsvError, Delimiter, Header, cell_value
from app.intake.imports import MAX_FILE_BYTES, extract_import
from app.intake.validation import SourceValidationError


class ImportPreview(BaseModel):
    text: str
    format: str
    pages: int | None
    code_points: int
    utf8_bytes: int
    notes: list[str]
    csv: CsvInfo | None = None


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
        csv_delimiter: Annotated[Delimiter, Form()] = "auto",
        csv_header: Annotated[Header, Form()] = "auto",
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
                extract_import, file.filename, raw, csv_delimiter, csv_header
            )
        except CsvError as exc:
            raise ApiError(422, exc.code, str(exc)) from None
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
            csv=CsvInfo(
                delimiter=result.layout["delimiter"],
                has_header=result.layout["has_header"],
                columns=result.layout["columns"],
                data_rows=len(result.layout["records"]) - int(result.layout["has_header"]),
                headers=[
                    cell_value(result.source.text, cell) for cell in result.layout["records"][0]
                ]
                if result.layout["has_header"]
                else [],
                rules=[],
                cells=result.layout["records"],
            )
            if result.format == "csv"
            else None,
        )
        return await run_in_threadpool(
            protected_json_response, view, request, identity,
            lambda current: require_current_intake_access(engine, request, workspace_id),
        )

    return router
