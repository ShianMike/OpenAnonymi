"""Each ZIP entry uses the ordinary authorized-output transaction and version locks."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from tempfile import SpooledTemporaryFile
from uuid import UUID, uuid5
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import ContentUnavailable
from app.batches.contracts import BatchEligibility, OutputExclusion
from app.batches.service import owned_batch
from app.contracts import DocumentStatus, VersionRef
from app.db.batches import ScanJob
from app.db.crypto import KeyRing
from app.db.models import Document, ReviewCompletion
from app.db.repository import VersionConflict, _version
from app.db.source_structures import SourceStructure
from app.exports.service import ExportConflict, OutputTooLarge, generate_output
from app.reviews.service import CompletionRejected, current_completion
from app.team_review.service import require_second_approval

MAX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MEMORY_SPOOL_BYTES = 8 * 1024 * 1024


class BatchOutputRejected(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class OutputCandidate:
    document_id: UUID
    position: int
    version: VersionRef | None
    format: str
    reason: str | None


def exclusion_reason(session: Session, document: Document, now: datetime) -> str | None:
    if document.deleted_at is not None or document.status == DocumentStatus.DELETED:
        return "deleted"
    if document.expires_at <= now or document.status == DocumentStatus.EXPIRED:
        return "expired"
    if document.status == DocumentStatus.FAILED:
        return "scan_failed"
    failed = session.scalar(
        select(ScanJob.id)
        .where(
            ScanJob.document_id == document.id,
            ScanJob.source_revision_id == document.current_revision_id,
            ScanJob.settings_version == document.settings_version,
            ScanJob.status == "failed",
        )
        .limit(1)
    )
    if failed is not None and document.status not in (
        DocumentStatus.READY,
        DocumentStatus.EXPORTED,
    ):
        return "scan_failed"
    try:
        current_completion(session, document)
    except (CompletionRejected, ContentUnavailable):
        previous = session.scalar(
            select(ReviewCompletion.id)
            .where(
                ReviewCompletion.document_id == document.id,
            )
            .limit(1)
        )
        return "stale_confirmation" if previous is not None else "not_confirmed"
    try:
        require_second_approval(session, document)
    except CompletionRejected:
        return "approval_required"
    return None


def _candidates(
    engine: Engine, batch_id: UUID, actor_id: UUID, mode: str, now: datetime
) -> list[OutputCandidate]:
    with Session(engine) as session:
        owned_batch(session, batch_id, actor_id)
        result = []
        for document in session.scalars(
            select(Document)
            .where(
                Document.batch_id == batch_id,
            )
            .order_by(Document.batch_position)
        ):
            reason = exclusion_reason(session, document, now)
            format = "txt"
            if mode == "original":
                layout = (
                    session.get(SourceStructure, document.current_revision_id)
                    if document.current_revision_id
                    else None
                )
                if document.csv_delimiter is not None:
                    format = "csv"
                elif layout and layout.kind == "docx":
                    format = "docx"
            result.append(
                OutputCandidate(
                    document.id,
                    document.batch_position,
                    _version(document) if document.current_revision_id else None,
                    format,
                    reason,
                )
            )
        return result


def eligibility(engine: Engine, batch_id: UUID, actor_id: UUID, now: datetime):
    candidates = _candidates(engine, batch_id, actor_id, "original", now)
    return BatchEligibility(
        total_count=len(candidates),
        included_count=sum(row.reason is None for row in candidates),
        excluded=[
            OutputExclusion(document_id=row.document_id, reason=row.reason)
            for row in candidates
            if row.reason is not None
        ],
    )


def _authorize(engine: Engine, batch_id: UUID, actor_id: UUID, reauthorize=None):
    if reauthorize is not None:
        reauthorize()
    with Session(engine) as session:
        owned_batch(session, batch_id, actor_id)


def build_zip(
    engine: Engine,
    batch_id: UUID,
    actor_id: UUID,
    request_id: UUID,
    mode: str,
    keys: KeyRing,
    *,
    maximum_bytes: int = MAX_UNCOMPRESSED_BYTES,
    reauthorize=None,
):
    if mode not in {"original", "txt"}:
        raise BatchOutputRejected("invalid_output_mode", "Choose Original or TXT output.")
    _authorize(engine, batch_id, actor_id, reauthorize)
    candidates = _candidates(engine, batch_id, actor_id, mode, datetime.now(UTC))
    if not any(row.reason is None for row in candidates):
        raise BatchOutputRejected(
            "no_reviewed_outputs", "No documents currently have eligible reviewed outputs."
        )
    manifest = {"included": [], "excluded": []}
    # Ownership transfers to the streaming response; errors close it below.
    spool = SpooledTemporaryFile(max_size=MEMORY_SPOOL_BYTES, mode="w+b")  # noqa: SIM115
    total = 0
    try:
        with ZipFile(spool, "w", compression=ZIP_DEFLATED) as archive:
            for row in candidates:
                _authorize(engine, batch_id, actor_id, reauthorize)
                reason = row.reason
                if reason is None:
                    try:
                        payload, output = generate_output(
                            engine,
                            document_id=row.document_id,
                            actor_id=actor_id,
                            expected=row.version,
                            event_id=uuid5(request_id, str(row.document_id)),
                            keys=keys,
                            now=datetime.now(UTC),
                            format=row.format,
                            variant="spreadsheet_safe",
                            maximum_bytes=maximum_bytes - total,
                            reauthorize=reauthorize,
                        )
                    except VersionConflict:
                        reason = "stale_confirmation"
                    except ContentUnavailable:
                        # Distinguish expiry/deletion without decrypting anything.
                        with Session(engine) as session:
                            document = session.get(Document, row.document_id)
                            reason = (
                                "deleted"
                                if document is None or document.deleted_at is not None
                                else "expired"
                            )
                    except CompletionRejected as exc:
                        reason = (
                            "approval_required"
                            if exc.code
                            in {
                                "second_approval_required",
                                "approval_required_by_policy",
                            }
                            else "stale_confirmation"
                        )
                    except OutputTooLarge:
                        raise BatchOutputRejected(
                            "outputs_too_large", "Reviewed outputs exceed the 64 MiB archive limit."
                        ) from None
                    except ExportConflict:
                        raise BatchOutputRejected(
                            "output_request_conflict",
                            "This archive request ID belongs to another output operation. Start a new download.",
                        ) from None
                    else:
                        filename = f"reviewed-{row.position:02d}-{row.document_id}.{row.format}"
                        total += len(payload)
                        archive.writestr(filename, payload)
                        manifest["included"].append(
                            {
                                "file": filename,
                                "document_id": str(row.document_id),
                                "source_revision_id": str(output.version.source_revision_id),
                                "decision_version": output.version.decision_version,
                                "settings_version": output.version.settings_version,
                                "confirmed_at": output.confirmed_at.isoformat(),
                                "format": row.format,
                            }
                        )
                        del payload, output
                if reason is not None:
                    manifest["excluded"].append(
                        {"document_id": str(row.document_id), "reason": reason}
                    )
            if not manifest["included"]:
                raise BatchOutputRejected(
                    "no_reviewed_outputs", "No documents currently have eligible reviewed outputs."
                )
            metadata = json.dumps(manifest, ensure_ascii=True, separators=(",", ":")).encode()
            if total + len(metadata) > maximum_bytes:
                raise BatchOutputRejected(
                    "outputs_too_large", "Reviewed outputs exceed the 64 MiB archive limit."
                )
            archive.writestr("manifest.json", metadata)
        # A mid-build owner revocation or batch deletion must stop the entire download.
        _authorize(engine, batch_id, actor_id, reauthorize)
        spool.seek(0)
        return spool
    except BaseException:
        spool.close()
        raise


def archive_chunks(spool):
    try:
        while chunk := spool.read(64 * 1024):
            yield chunk
    finally:
        spool.close()
