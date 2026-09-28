"""Explicit, version-bound confirmation of one saved reviewed output."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import owned_document
from app.contracts import DocumentStatus, VersionRef
from app.db.crypto import KeyRing
from app.db.models import Document, ExportEvent, ReviewCompletion, ScanRun
from app.db.repository import VersionConflict
from app.groups.service import _snapshot, _version
from app.lifecycle import require_transition
from app.transformations.service import build_current_preview


class CompletionRejected(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class CompletionSnapshot:
    version: VersionRef
    completion_id: UUID
    confirmed_at: datetime


@dataclass(frozen=True)
class ReviewSummary:
    version: VersionRef
    confirmed_at: datetime
    last_output_generated_at: datetime | None
    finding_count: int
    counts_by_category: dict[str, int]
    counts_by_action: dict[str, int]


def current_completion(session: Session, document: Document) -> ReviewCompletion:
    version = _version(document)
    completion = session.scalar(
        select(ReviewCompletion).where(
            ReviewCompletion.document_id == document.id,
            ReviewCompletion.source_revision_id == version.source_revision_id,
            ReviewCompletion.decision_version == version.decision_version,
            ReviewCompletion.settings_version == version.settings_version,
        )
    )
    if completion is None or document.status not in (
        DocumentStatus.READY,
        DocumentStatus.EXPORTED,
    ):
        raise CompletionRejected(
            "review_not_completed", "Confirm the current preview before exporting."
        )
    return completion


def confirm_review(
    engine: Engine,
    *,
    document_id: UUID,
    actor_id: UUID,
    expected: VersionRef,
    confirmed_preview: bool,
    keys: KeyRing,
    now: datetime,
) -> CompletionSnapshot:
    if not confirmed_preview:
        raise CompletionRejected(
            "confirmation_required", "Confirm that you reviewed the full output."
        )
    with Session(engine) as session, session.begin():
        document = owned_document(session, document_id, actor_id, now, lock=True)
        version = _version(document)
        if version != expected:
            raise VersionConflict(version)
        if document.status in (DocumentStatus.READY, DocumentStatus.EXPORTED):
            completion = current_completion(session, document)
            return CompletionSnapshot(version, completion.id, completion.confirmed_at)
        scan = session.scalar(
            select(ScanRun.id).where(
                ScanRun.document_id == document_id,
                ScanRun.source_revision_id == version.source_revision_id,
                ScanRun.settings_version == version.settings_version,
                ScanRun.status == "completed",
            )
        )
        if scan is None:
            raise CompletionRejected(
                "scan_required", "Run the current suggestion scan before confirming the review."
            )
        if document.status != DocumentStatus.NEEDS_REVIEW:
            raise CompletionRejected(
                "review_not_ready", "The current review is not ready for confirmation."
            )
        preview = build_current_preview(session, document=document, keys=keys)
        if preview.status == "conflict":
            raise CompletionRejected(
                "overlapping_findings", "Resolve overlapping findings before confirmation."
            )
        if preview.status != "complete":
            raise CompletionRejected(
                "pending_findings", "Give every current finding a decision before confirmation."
            )
        completion = ReviewCompletion(
            id=uuid4(),
            document_id=document_id,
            source_revision_id=version.source_revision_id,
            decision_version=version.decision_version,
            settings_version=version.settings_version,
            confirmed_by=actor_id,
            confirmed_at=now,
        )
        session.add(completion)
        require_transition(DocumentStatus(document.status), DocumentStatus.READY)
        document.status = DocumentStatus.READY
        document.updated_at = now
        session.flush()
        return CompletionSnapshot(version, completion.id, completion.confirmed_at)


def load_review_summary(
    engine: Engine, *, document_id: UUID, actor_id: UUID, now: datetime
) -> ReviewSummary:
    with Session(engine) as session, session.begin():
        document = owned_document(session, document_id, actor_id, now, lock=True)
        completion = current_completion(session, document)
        findings = _snapshot(session, _version(document))
        category_counts = Counter(item.category.value for item in findings.findings)
        action_counts = Counter(item.action for item in findings.findings if item.action)
        last_generated = session.scalar(
            select(func.max(ExportEvent.occurred_at)).where(
                ExportEvent.document_id == document_id,
                ExportEvent.completion_id == completion.id,
            )
        )
        return ReviewSummary(
            version=_version(document),
            confirmed_at=completion.confirmed_at,
            last_output_generated_at=last_generated,
            finding_count=len(findings.findings),
            counts_by_category=dict(category_counts),
            counts_by_action=dict(action_counts),
        )
