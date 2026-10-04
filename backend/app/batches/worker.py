"""One awake-process worker; persisted leases tolerate restarts and sleeping hosts."""

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import ContentUnavailable, DocumentNotFound, owned_document
from app.config import Settings
from app.db.batches import ScanJob
from app.db.crypto import ContentKeyUnavailable, KeyRing, ProtectedContentError
from app.db.models import Document
from app.db.repository import VersionConflict, _version
from app.detection.service import ScanExecutionFailed, scan_document

LOGGER = logging.getLogger(__name__)
JOB_LEASE = timedelta(seconds=120)
HEARTBEAT_SECONDS = 30
ERROR_CODES = frozenset(
    {"too_many_suggestions", "detector_error", "content_unavailable", "worker_error"}
)


@dataclass(frozen=True)
class ClaimedJob:
    id: UUID
    document_id: UUID
    source_revision_id: UUID
    settings_version: int
    attempts: int
    lease_owner: UUID


def claim_job(engine: Engine, process_id: UUID, now: datetime) -> ClaimedJob | None:
    candidate = (
        select(ScanJob.id)
        .where(
            or_(
                and_(ScanJob.status == "queued", ScanJob.available_at <= now),
                and_(ScanJob.status == "leased", ScanJob.lease_expires_at < now),
            )
        )
        .order_by(ScanJob.available_at, ScanJob.created_at, ScanJob.id)
        .with_for_update(skip_locked=True)
        .limit(1)
        .scalar_subquery()
    )
    with Session(engine) as session, session.begin():
        row = session.execute(
            update(ScanJob)
            .where(ScanJob.id == candidate)
            .values(
                status="leased",
                lease_owner=process_id,
                lease_expires_at=now + JOB_LEASE,
                attempts=ScanJob.attempts + 1,
                updated_at=now,
            )
            .returning(
                ScanJob.id,
                ScanJob.document_id,
                ScanJob.source_revision_id,
                ScanJob.settings_version,
                ScanJob.attempts,
            )
        ).first()
        return ClaimedJob(*row, process_id) if row else None


def _lease_filter(job: ClaimedJob):
    return (
        ScanJob.id == job.id,
        ScanJob.status == "leased",
        ScanJob.lease_owner == job.lease_owner,
        ScanJob.attempts == job.attempts,
    )


def heartbeat(engine: Engine, job: ClaimedJob, now: datetime) -> bool:
    with Session(engine) as session, session.begin():
        result = session.execute(
            update(ScanJob)
            .where(
                *_lease_filter(job),
                ScanJob.lease_expires_at > now,
            )
            .values(lease_expires_at=now + JOB_LEASE, updated_at=now)
        )
        return result.rowcount == 1


def execute_job(engine: Engine, job: ClaimedJob, keys: KeyRing) -> tuple[str, str | None]:
    try:
        now = datetime.now(UTC)
        with Session(engine) as session:
            document = session.get(Document, job.document_id)
            if document is None:
                return "skipped", None
            document = owned_document(session, document.id, document.owner_id, now)
            if (
                document.current_revision_id != job.source_revision_id
                or document.settings_version != job.settings_version
            ):
                return "skipped", None
            expected, actor_id = _version(document), document.owner_id
        result = scan_document(
            engine,
            document_id=job.document_id,
            actor_id=actor_id,
            expected=expected,
            keys=keys,
            now=now,
        )
        # Another ordinary scan may still hold its own lease. Do not declare an
        # incomplete run done or consume the job's failure budget while it runs.
        if result.status == "scanning":
            return "busy", None
        if result.status == "completed":
            return "done", None
        return "failure", "detector_error"
    except (DocumentNotFound, ContentUnavailable, VersionConflict):
        return "skipped", None
    except (ContentKeyUnavailable, ProtectedContentError):
        return "failure", "content_unavailable"
    except ScanExecutionFailed as exc:
        return "failure", exc.code if exc.code in ERROR_CODES else "detector_error"
    except Exception:  # noqa: BLE001 -- durable retry records never include exception text
        LOGGER.warning("Queued scan failed; its persisted retry policy applies.")
        return "failure", "worker_error"


def finish_job(
    engine: Engine, job: ClaimedJob, outcome: str, code: str | None, now: datetime
) -> bool:
    if outcome not in {"done", "skipped", "busy", "failure"}:
        raise ValueError("Unknown scan job outcome.")
    with Session(engine) as session, session.begin():
        # Use the same document-before-job lock order as owner retry/deletion.
        document = session.scalar(
            select(Document)
            .where(
                Document.id == job.document_id,
            )
            .with_for_update()
        )
        row = session.scalar(select(ScanJob).where(*_lease_filter(job)).with_for_update())
        if row is None or row.lease_expires_at <= now:
            return False
        try:
            if document is None:
                outcome = "skipped"
            else:
                owned_document(session, document.id, document.owner_id, now)
                if (
                    document.current_revision_id != job.source_revision_id
                    or document.settings_version != job.settings_version
                ):
                    outcome = "skipped"
        except (DocumentNotFound, ContentUnavailable):
            outcome = "skipped"
        row.lease_owner = row.lease_expires_at = None
        row.updated_at = now
        row.last_error_code = code if outcome == "failure" and code in ERROR_CODES else None
        if outcome == "failure":
            if row.attempts < 3:
                row.status = "queued"
                row.available_at = now + timedelta(seconds=30 if row.attempts == 1 else 120)
            else:
                row.status = "failed"
        elif outcome == "busy":
            row.status = "queued"
            row.attempts -= 1
            row.available_at = now + timedelta(seconds=5)
        else:
            row.status = outcome
        return True


def has_pending_jobs(engine: Engine) -> bool:
    with Session(engine) as session:
        return bool(
            session.scalar(
                select(func.count())
                .select_from(ScanJob)
                .where(
                    ScanJob.status.in_(("queued", "leased")),
                )
            )
        )


class ScanWorker:
    def __init__(self, engine: Engine, settings: Settings):
        self.engine, self.settings = engine, settings
        self.process_id = uuid4()
        self._event = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None

    def wake(self) -> None:
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._event.set)

    async def run_one(self) -> bool:
        job = await asyncio.to_thread(claim_job, self.engine, self.process_id, datetime.now(UTC))
        if job is None:
            return False
        try:
            keys = KeyRing.from_settings(self.settings)
        except ContentKeyUnavailable:
            await asyncio.to_thread(
                finish_job, self.engine, job, "failure", "content_unavailable", datetime.now(UTC)
            )
            return True
        work = asyncio.create_task(asyncio.to_thread(execute_job, self.engine, job, keys))
        try:
            while not work.done():
                done, _ = await asyncio.wait({work}, timeout=HEARTBEAT_SECONDS)
                if not done:
                    alive = await asyncio.to_thread(heartbeat, self.engine, job, datetime.now(UTC))
                    if not alive:
                        # A reclaimed lease's attempt token prevents this task
                        # from overwriting the new worker's queue outcome.
                        work.cancel()
                        with suppress(asyncio.CancelledError):
                            await work
                        return True
            outcome, code = await work
            await asyncio.to_thread(finish_job, self.engine, job, outcome, code, datetime.now(UTC))
            return True
        finally:
            if not work.done():
                work.cancel()
                with suppress(asyncio.CancelledError):
                    await work

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        while True:
            self._event.clear()
            try:
                if await self.run_one():
                    continue
                pending = await asyncio.to_thread(has_pending_jobs, self.engine)
                delay = 5 if pending else 60
            except Exception:  # noqa: BLE001 -- connection failures must not kill the worker
                LOGGER.warning("Scan queue is temporarily unavailable; the worker will retry.")
                delay = 5
            with suppress(TimeoutError):
                await asyncio.wait_for(self._event.wait(), timeout=delay)
