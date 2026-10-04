"""Owner-only batch routes, using the ordinary mutation origin and CSRF checks."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.accounts.access import ContentUnavailable, DocumentNotFound, WorkspaceAccessDenied
from app.accounts.api import current_identity, mutation_identity
from app.accounts.security import SessionIdentity
from app.batches.contracts import (
    BatchEligibility,
    BatchList,
    BatchOutputRequest,
    BatchView,
    CreateBatchRequest,
    DeleteBatchRequest,
)
from app.batches.outputs import BatchOutputRejected, archive_chunks, build_zip, eligibility
from app.batches.service import (
    BatchRejected,
    create_batch,
    delete_batch,
    list_batches,
    load_batch,
    owned_batch,
    retry_document,
    upload_document,
)
from app.cleanup.background import purge_deleted_document
from app.contracts import ErrorResponse
from app.db.crypto import ContentKeyUnavailable, ProtectedContentError
from app.db.repository import StorageValidationError
from app.errors import ApiError
from app.intake.api import SavedDraftView, _keys, _saved_view
from app.intake.csv_structure import CsvError
from app.intake.imports import MAX_FILE_BYTES, extract_import
from app.intake.validation import SourceValidationError
from app.workspace.presets import PresetNotFound


def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except (DocumentNotFound, WorkspaceAccessDenied):
        raise ApiError(404, "batch_not_found", "Batch not found.") from None
    except PresetNotFound:
        raise ApiError(404, "preset_not_found", "Preset not found.") from None
    except ContentUnavailable:
        raise ApiError(410, "content_expired", "Content is unavailable.") from None
    except (ContentKeyUnavailable, ProtectedContentError):
        raise ApiError(503, "content_unavailable", "Content access is unavailable.") from None
    except (BatchRejected, CsvError) as exc:
        raise ApiError(422, exc.code, str(exc)) from None
    except BatchOutputRejected as exc:
        raise ApiError(409, exc.code, str(exc)) from None
    except (SourceValidationError, StorageValidationError) as exc:
        raise ApiError(422, "invalid_source", str(exc)) from None


def create_batch_router(engine: Engine) -> APIRouter:
    router = APIRouter(prefix="/api/v1/batches", tags=["batches"])
    errors = {status: {"model": ErrorResponse} for status in (401, 403, 404, 410, 422, 503)}

    @router.post("", response_model=BatchView, status_code=201, responses=errors)
    def create_route(
        body: CreateBatchRequest,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        keys = _keys(request)
        now = datetime.now(UTC)
        batch_id = _call(create_batch, engine, identity.user_id, body, keys, now)
        return _call(load_batch, engine, batch_id, identity.user_id, keys, now)

    @router.get("", response_model=BatchList, responses=errors)
    def list_route(
        workspace_id: UUID,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ):
        return _call(list_batches, engine, workspace_id, identity.user_id, _keys(request))

    @router.get("/{batch_id}", response_model=BatchView, responses=errors)
    def status_route(
        batch_id: UUID,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ):
        return _call(
            load_batch, engine, batch_id, identity.user_id, _keys(request), datetime.now(UTC)
        )

    @router.post(
        "/{batch_id}/documents", response_model=SavedDraftView, status_code=201, responses=errors
    )
    async def upload_route(
        batch_id: UUID,
        request: Request,
        file: Annotated[UploadFile, File()],
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        def authorize():
            with Session(engine) as session:
                _call(owned_batch, session, batch_id, identity.user_id)

        await run_in_threadpool(authorize)
        form = await request.form()
        if any(key != "file" for key, _ in form.multi_items()):
            raise ApiError(
                422, "batch_settings_fixed", "Use the batch's shared settings for uploads."
            )
        if (
            len(form.getlist("file")) != 1
            or sum(isinstance(value, StarletteUploadFile) for _, value in form.multi_items()) != 1
        ):
            raise ApiError(422, "invalid_file", "Choose exactly one file per upload.")
        if file.size is not None and file.size > MAX_FILE_BYTES:
            raise ApiError(422, "invalid_file", "File exceeds the 8 MiB import limit.")
        raw = await file.read(MAX_FILE_BYTES + 1)
        imported = await run_in_threadpool(_call, extract_import, file.filename, raw)
        saved = await run_in_threadpool(
            _call,
            upload_document,
            engine,
            batch_id,
            identity.user_id,
            imported,
            len(raw),
            _keys(request),
            datetime.now(UTC),
        )
        request.app.state.scan_worker.wake()
        return _saved_view(saved)

    @router.post("/{batch_id}/documents/{document_id}/retry", status_code=204, responses=errors)
    def retry_route(
        batch_id: UUID,
        document_id: UUID,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        _call(retry_document, engine, batch_id, document_id, identity.user_id, datetime.now(UTC))
        request.app.state.scan_worker.wake()
        return Response(status_code=204)

    @router.delete("/{batch_id}", status_code=204, responses=errors)
    def delete_route(
        batch_id: UUID,
        body: DeleteBatchRequest,
        background: BackgroundTasks,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        if not body.confirmed:
            raise ApiError(
                422, "confirmation_required", "Confirm deletion of every document in this batch."
            )
        ids = _call(delete_batch, engine, batch_id, identity.user_id, datetime.now(UTC))
        for document_id in ids:
            background.add_task(purge_deleted_document, engine, document_id)
        return Response(status_code=204)

    @router.get(
        "/{batch_id}/outputs/eligibility", response_model=BatchEligibility, responses=errors
    )
    def eligibility_route(
        batch_id: UUID, identity: Annotated[SessionIdentity, Depends(current_identity)]
    ):
        return _call(eligibility, engine, batch_id, identity.user_id, datetime.now(UTC))

    @router.post(
        "/{batch_id}/outputs",
        response_class=StreamingResponse,
        responses={
            **errors,
            409: {"model": ErrorResponse},
            200: {
                "content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}}
            },
        },
    )
    async def output_route(
        batch_id: UUID,
        body: BatchOutputRequest,
        request: Request,
        background: BackgroundTasks,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        spool = await run_in_threadpool(
            _call,
            build_zip,
            engine,
            batch_id,
            identity.user_id,
            body.request_id,
            body.mode,
            _keys(request),
        )
        background.add_task(spool.close)
        return StreamingResponse(
            archive_chunks(spool),
            media_type="application/zip",
            background=background,
            headers={
                "Content-Disposition": f'attachment; filename="reviewed-batch-{batch_id}.zip"'
            },
        )

    return router
