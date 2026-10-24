"""Authorized source/output layouts, with a fresh access and version check before release."""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.accounts.access import ContentUnavailable, DocumentNotFound, review_document
from app.accounts.api import current_identity
from app.accounts.response_boundary import protected_json_response
from app.accounts.security import SessionIdentity
from app.db.crypto import ContentKeyUnavailable, KeyRing, ProtectedContentError, ProtectedValue
from app.db.models import SourceRevision
from app.db.repository import _version
from app.db.source_structures import load_file_layout
from app.errors import ApiError
from app.exports.errors import PdfUnavailable
from app.intake.file_layout import review_file_layout
from app.intake.layout_contracts import FileLayoutView
from app.transformations.engine import InvalidTransformation
from app.transformations.service import build_current_preview
from app.workloads import render_slot


def create_layout_router(engine):
    router = APIRouter(prefix="/api/v1/documents", tags=["file layouts"])

    @router.get("/{document_id}/layout", response_model=FileLayoutView)
    def layout_route(
        document_id: UUID,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
        variant: Literal["original", "preview"] = "original",
    ):
        if not render_slot.acquire(timeout=3):
            raise ApiError(409, "layout_busy", "A file is being processed. Try again shortly.")
        try:
            keys = KeyRing.from_settings(request.app.state.settings)
            with Session(engine) as session, session.begin():
                document = review_document(
                    session, document_id, identity.user_id, datetime.now(UTC), lock=True
                )
                version = _version(document)
                revision = session.get(SourceRevision, version.source_revision_id)
                source = keys.decrypt_text(
                    ProtectedValue(revision.source_ciphertext, revision.source_key_id)
                )
                layout = load_file_layout(session, revision.id, keys, source)
                preview = build_current_preview(session, document=document, keys=keys)
                if variant == "preview" and preview.text is None:
                    raise InvalidTransformation(
                        "Resolve overlapping findings before reading output."
                    )
                value = review_file_layout(
                    layout, source, preview.text if variant == "preview" else None, preview.mappings
                )
                view = FileLayoutView(version=version, layout=value)

            def authorize(fresh):
                with Session(engine) as current_session:
                    current = review_document(
                        current_session, document_id, fresh.user_id, datetime.now(UTC)
                    )
                    if _version(current) != version:
                        raise ApiError(
                            409, "invalid_review_state", "The review changed while loading. Retry."
                        )

            return protected_json_response(view, request, identity, authorize)
        except DocumentNotFound:
            raise ApiError(404, "document_not_found", "Document not found.") from None
        except ContentUnavailable:
            raise ApiError(410, "content_expired", "Document content is unavailable.") from None
        except (ContentKeyUnavailable, ProtectedContentError):
            raise ApiError(503, "content_unavailable", "Content access is unavailable.") from None
        except (InvalidTransformation, PdfUnavailable) as error:
            raise ApiError(409, "layout_unavailable", str(error)) from None
        finally:
            render_slot.release()

    return router
