"""Aggregate response retains the existing child contracts and access controls."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import ContentUnavailable, DocumentNotFound, review_document
from app.accounts.api import current_identity
from app.accounts.security import SessionIdentity
from app.contracts import ErrorResponse
from app.db.crypto import ContentKeyUnavailable, KeyRing, ProtectedContentError
from app.db.repository import _version
from app.detection.api import ScanView
from app.detection.api import _view as scan_view
from app.errors import ApiError
from app.groups.api import FindingsView
from app.groups.api import _view as findings_view
from app.intake.api import SourceView, _source_view
from app.reviews.api import ReviewSummaryView
from app.reviews.service import CompletionRejected
from app.reviews.state import load_review_state
from app.team_review.service import HandoffView
from app.team_review.service import _view as handoff_view
from app.transformations.api import PreviewView, preview_view
from app.transformations.engine import InvalidTransformation


class ReviewStateView(BaseModel):
    source: SourceView
    scan: ScanView
    findings: FindingsView
    preview: PreviewView
    summary: ReviewSummaryView | None
    handoff: HandoffView


def create_review_state_router(engine: Engine) -> APIRouter:
    router = APIRouter(prefix="/api/v1/documents", tags=["review state"])
    # Opaque validators, not plaintext fingerprints or a server content cache.
    validator_key = secrets.token_bytes(32)

    @router.get(
        "/{document_id}/review-state",
        response_model=ReviewStateView,
        responses={
            304: {"description": "Current authorized snapshot is unchanged; no body."},
            **{code: {"model": ErrorResponse} for code in (404, 409, 410, 503)},
        },
    )
    def review_state_route(
        document_id: UUID,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(current_identity)],
    ) -> Response:
        try:
            result = load_review_state(
                engine,
                document_id=document_id,
                actor_id=identity.user_id,
                keys=KeyRing.from_settings(request.app.state.settings),
                now=datetime.now(UTC),
            )
            view = ReviewStateView(
                source=_source_view(result.source),
                scan=scan_view(result.scan),
                findings=findings_view(result.findings),
                preview=preview_view(result.preview),
                summary=ReviewSummaryView(**vars(result.summary)) if result.summary else None,
                handoff=result.handoff,
            )
            payload = view.model_dump_json().encode("utf-8")
            digest = hmac.new(
                validator_key, identity.session_id.bytes + payload, hashlib.sha256
            ).hexdigest()
            tag = f'"rs1-{digest}"'
            # A validator is never an access grant. Recheck after serialization,
            # including the no-body path, using fresh session/membership/expiry.
            fresh = current_identity(request)
            if fresh.session_id != identity.session_id:
                raise ApiError(401, "sign_in_required", "Sign in to continue.")
            with Session(engine) as session:
                current = review_document(session, document_id, fresh.user_id, datetime.now(UTC))
                if (
                    _version(current) != result.source.version
                    or current.status != result.source.status
                    or current.expires_at != result.source.expires_at
                    or handoff_view(session, current, fresh.user_id) != result.handoff
                ):
                    raise ApiError(
                        409, "invalid_review_state", "The review changed while loading. Retry."
                    )
            headers = {"ETag": tag, "Cache-Control": "no-store", "Vary": "Cookie, Origin"}
            candidate = request.headers.get("if-none-match", "")
            candidates = candidate.split(",") if len(candidate) <= 4096 else []
            matches = len(candidates) <= 16 and any(
                item.strip() == "*"
                or hmac.compare_digest(
                    item.strip().removeprefix("W/").encode("utf-8"), tag.encode("ascii")
                )
                for item in candidates
            )
            if matches:
                return Response(status_code=304, headers=headers)
            return Response(payload, media_type="application/json", headers=headers)
        except DocumentNotFound:
            raise ApiError(404, "document_not_found", "Document not found.") from None
        except ContentUnavailable:
            raise ApiError(410, "content_expired", "Document content is unavailable.") from None
        except (ContentKeyUnavailable, ProtectedContentError):
            raise ApiError(503, "content_unavailable", "Content access is unavailable.") from None
        except (CompletionRejected, InvalidTransformation):
            raise ApiError(
                409, "invalid_review_state", "The current review cannot be loaded."
            ) from None

    return router
