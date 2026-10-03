"""Persist a bounded pass separately from its independently committed batches."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import case, delete, func, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.accounts.access import require_administrator
from app.cleanup.service import (
    CleanupResult,
    cleanup_remaining,
    purge_unavailable_content,
    unavailable_content,
)
from app.db.maintenance import MaintenanceRun
from app.db.models import Document
from app.maintenance.schedule import CLEANUP_OVERDUE_AFTER

LOGGER = logging.getLogger(__name__)
Trigger = Literal["startup", "periodic", "cli", "endpoint"]
RUN_RECORD_LOCK = 0x4F414D41494E54
MAX_PASS_SECONDS = 25


@dataclass(frozen=True)
class MaintenanceResult:
    documents_purged: int
    activity_removed: int
    expired_rows_removed: int
    more_remaining: bool
    duration_ms: int
    started_at: datetime
    finished_at: datetime


@dataclass(frozen=True)
class CleanupHealth:
    last_success_at: datetime | None
    last_failure_at: datetime | None
    overdue: bool
    documents_awaiting_purge: int
    checked_at: datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def _retain_runs(session: Session) -> None:
    session.execute(
        delete(MaintenanceRun).where(
            MaintenanceRun.id.in_(
                select(MaintenanceRun.id)
                .order_by(MaintenanceRun.started_at.desc(), MaintenanceRun.id.desc())
                .offset(200)
            )
        )
    )


def _start_run(engine: Engine, trigger: Trigger, started: datetime) -> UUID:
    run_id = uuid4()
    with Session(engine) as session, session.begin():
        session.execute(text("SET LOCAL statement_timeout = '2s'"))
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": RUN_RECORD_LOCK})
        session.execute(
            update(MaintenanceRun)
            .where(
                MaintenanceRun.status == "running",
                MaintenanceRun.started_at < started - timedelta(hours=1),
            )
            .values(status="failed", failure_code="abandoned", finished_at=started)
        )
        session.add(
            MaintenanceRun(id=run_id, trigger=trigger, started_at=started, status="running")
        )
        session.flush()
        _retain_runs(session)
    return run_id


def _finish_run(
    engine: Engine, run_id: UUID, finished: datetime, totals: CleanupResult, *, failed: bool
) -> None:
    with Session(engine) as session, session.begin():
        session.execute(text("SET LOCAL statement_timeout = '2s'"))
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": RUN_RECORD_LOCK})
        session.execute(
            update(MaintenanceRun)
            .where(MaintenanceRun.id == run_id)
            .values(
                status="failed" if failed else "ok",
                failure_code="cleanup_failed" if failed else None,
                finished_at=finished,
                documents_purged=totals.documents_purged,
                activity_removed=totals.activity_removed,
                expired_rows_removed=totals.expired_rows_removed,
            )
        )
        _retain_runs(session)


def run_cleanup(
    engine: Engine,
    *,
    trigger: Trigger,
    clock: Callable[[], datetime] = utc_now,
    timer: Callable[[], float] = monotonic,
    max_seconds: float = MAX_PASS_SECONDS,
    batch_size: int = 100,
) -> MaintenanceResult:
    if (
        trigger not in {"startup", "periodic", "cli", "endpoint"}
        or not 0 < max_seconds <= MAX_PASS_SECONDS
    ):
        raise ValueError("Invalid cleanup pass configuration.")
    started = clock()
    if started.tzinfo is None:
        raise ValueError("A timezone-aware cleanup clock is required.")
    began = timer()
    run_id = _start_run(engine, trigger, started)
    totals = CleanupResult(0, 0, 0)
    more = True
    try:
        while (remaining := max_seconds - (timer() - began)) > 0:
            try:
                batch = purge_unavailable_content(
                    engine,
                    now=clock(),
                    batch_size=batch_size,
                    statement_timeout_ms=max(1, int(remaining * 1000)),
                )
            except DBAPIError as exc:
                # PostgreSQL 17 bounds the entire batch transaction, including
                # many short statements; rolled-back work contributes no counts.
                if getattr(exc.orig, "sqlstate", None) in {"57014", "25P04", "55P03"}:
                    break
                raise
            totals = CleanupResult(
                totals.documents_purged + batch.documents_purged,
                totals.activity_removed + batch.activity_removed,
                totals.expired_rows_removed + batch.expired_rows_removed,
            )
            with Session(engine) as session:
                session.execute(text("SET LOCAL statement_timeout = '500ms'"))
                more = cleanup_remaining(session, clock())
            if not more or not (
                batch.documents_purged or batch.activity_removed or batch.expired_rows_removed
            ):
                break
    except Exception:
        _finish_run(engine, run_id, max(started, clock()), totals, failed=True)
        LOGGER.warning("Maintenance cleanup failed; the next pass will retry.")
        raise
    finished = max(started, clock())
    _finish_run(engine, run_id, finished, totals, failed=False)
    return MaintenanceResult(
        totals.documents_purged,
        totals.activity_removed,
        totals.expired_rows_removed,
        more,
        max(0, int((timer() - began) * 1000)),
        started,
        finished,
    )


def load_cleanup_health(
    engine: Engine, *, workspace_id: UUID, actor_id: UUID, now: datetime
) -> CleanupHealth:
    with Session(engine) as session:
        require_administrator(session, workspace_id=workspace_id, actor_id=actor_id)
        last_success = session.scalar(
            select(func.max(MaintenanceRun.finished_at)).where(MaintenanceRun.status == "ok")
        )
        last_failure = session.scalar(
            select(
                func.max(
                    case(
                        (MaintenanceRun.status == "failed", MaintenanceRun.finished_at),
                        (
                            MaintenanceRun.started_at < now - timedelta(hours=1),
                            MaintenanceRun.started_at + timedelta(hours=1),
                        ),
                        else_=None,
                    )
                )
            ).where(MaintenanceRun.status.in_(["failed", "running"]))
        )
        awaiting = session.scalar(
            select(func.count())
            .select_from(Document)
            .where(
                Document.workspace_id == workspace_id,
                unavailable_content(now),
            )
        )
    return CleanupHealth(
        last_success,
        last_failure,
        last_success is None or last_success < now - CLEANUP_OVERDUE_AFTER,
        awaiting,
        now,
    )
