"""One locked, authorized transaction for a current review; no plaintext cache."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import review_document
from app.contracts import DocumentStatus
from app.db.crypto import KeyRing
from app.db.repository import LoadedSource, _version, build_current_source
from app.detection.service import ScanSnapshot, current_scan_state
from app.groups.service import FindingsSnapshot, _snapshot
from app.reviews.service import ReviewSummary, build_review_summary
from app.team_review.service import HandoffView, _view
from app.transformations.service import PreviewSnapshot, build_current_preview


@dataclass(frozen=True)
class ReviewState:
    source: LoadedSource
    scan: ScanSnapshot
    findings: FindingsSnapshot
    preview: PreviewSnapshot
    summary: ReviewSummary | None
    handoff: HandoffView


def load_review_state(
    engine: Engine, *, document_id: UUID, actor_id: UUID, keys: KeyRing, now: datetime
) -> ReviewState:
    with Session(engine) as session, session.begin():
        document = review_document(session, document_id, actor_id, now, lock=True)
        scan = current_scan_state(session, document=document, now=now)
        source = build_current_source(session, document=document, actor_id=actor_id, keys=keys)
        findings = _snapshot(session, _version(document), actor_id, now)
        preview = build_current_preview(
            session, document=document, keys=keys, source=source.text, findings=findings
        )
        summary = (
            build_review_summary(
                session, document=document, keys=keys, findings=findings, preview=preview
            )
            if document.status
            in (
                DocumentStatus.READY,
                DocumentStatus.EXPORTED,
            )
            else None
        )
        return ReviewState(
            source, scan, findings, preview, summary, _view(session, document, actor_id)
        )
