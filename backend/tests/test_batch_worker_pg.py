import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.batches.worker import (
    ScanWorker,
    claim_job,
    execute_job,
    finish_job,
    heartbeat,
)
from app.db.batches import ScanJob
from app.db.crypto import KeyRing
from app.db.models import Document, Finding, Membership, ScanRun
from tests.batch_support import batch_client, upload
from tests.intake_support import _login


def job_state(engine, document_id):
    with Session(engine) as session:
        row = session.scalar(select(ScanJob).where(ScanJob.document_id == UUID(document_id)))
        return {
            "id": row.id,
            "status": row.status,
            "attempts": row.attempts,
            "code": row.last_error_code,
            "available": row.available_at,
            "expires": row.lease_expires_at,
            "lease_owner": row.lease_owner,
        }


def test_simultaneous_workers_claim_once_and_real_scan_is_idempotent(intake_site):
    owner, headers, base = batch_client(intake_site)
    _, _, engine, _, _ = intake_site
    version = upload(owner, headers, base)
    now = datetime.now(UTC)
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = list(pool.map(lambda actor: claim_job(engine, actor, now), [uuid4(), uuid4()]))
    claims = [job for job in jobs if job is not None]
    assert len(claims) == 1 and claims[0].attempts == 1
    keys = KeyRing.from_settings(owner.app.state.settings)
    assert execute_job(engine, claims[0], keys) == ("done", None)
    assert execute_job(engine, claims[0], keys) == ("done", None)
    assert finish_job(engine, claims[0], "done", None, datetime.now(UTC))
    assert job_state(engine, version["document_id"])["status"] == "done"
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count(ScanRun.id)).where(
                    ScanRun.document_id == UUID(version["document_id"])
                )
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count(Finding.id)).where(
                    Finding.document_id == UUID(version["document_id"])
                )
            )
            == 1
        )


def test_restart_claims_expired_lease_and_old_attempt_cannot_heartbeat_or_finish(intake_site):
    owner, headers, base = batch_client(intake_site)
    _, _, engine, _, _ = intake_site
    version = upload(owner, headers, base)
    now = datetime.now(UTC)
    old = claim_job(engine, uuid4(), now)
    assert heartbeat(engine, old, now + timedelta(seconds=30))
    assert claim_job(engine, uuid4(), now + timedelta(seconds=121)) is None
    newer = claim_job(engine, uuid4(), now + timedelta(seconds=151))
    assert newer.id == old.id and newer.attempts == 2
    assert not heartbeat(engine, old, now + timedelta(seconds=151))
    assert not finish_job(engine, old, "failure", "detector_error", now + timedelta(seconds=151))
    assert execute_job(engine, newer, KeyRing.from_settings(owner.app.state.settings)) == (
        "done",
        None,
    )
    assert finish_job(engine, newer, "done", None, now + timedelta(seconds=152))
    assert job_state(engine, version["document_id"])["status"] == "done"


def test_retry_timing_error_redaction_terminal_failure_and_owner_reset(intake_site):
    owner, headers, base = batch_client(intake_site)
    _, other, engine, _, _ = intake_site
    other_headers = _login(other, "intake-other@example.invalid")
    version = upload(owner, headers, base)
    now = datetime.now(UTC)
    for attempt, delay in [(1, 30), (2, 120), (3, None)]:
        job = claim_job(engine, uuid4(), now)
        assert job.attempts == attempt
        assert finish_job(engine, job, "failure", "private source must never be stored", now)
        state = job_state(engine, version["document_id"])
        assert state["code"] is None and state["lease_owner"] is None
        if delay is not None:
            assert state["status"] == "queued" and state["available"] == now + timedelta(
                seconds=delay
            )
            assert claim_job(engine, uuid4(), now + timedelta(seconds=delay - 1)) is None
            now += timedelta(seconds=delay)
        else:
            assert state["status"] == "failed"
    retry = base + f"/documents/{version['document_id']}/retry"
    assert other.post(retry, headers=other_headers).status_code == 404
    assert owner.get(base).json()["documents"][0]["state"] == "scan_failed"
    assert owner.post(retry, headers=headers).status_code == 204
    state = job_state(engine, version["document_id"])
    assert state["status"] == "queued" and state["attempts"] == 0
    assert owner.post(retry, headers=headers).status_code == 422
    worker = ScanWorker(engine, owner.app.state.settings)
    assert asyncio.run(worker.run_one())
    assert job_state(engine, version["document_id"])["status"] == "done"


def test_actual_detection_limit_fails_without_auto_decisions_then_retries(intake_site):
    owner, headers, base = batch_client(intake_site)
    _, _, engine, _, _ = intake_site
    version = upload(owner, headers, base, b" ".join([b"nora@example.test"] * 1001))
    worker = ScanWorker(engine, owner.app.state.settings)
    assert asyncio.run(worker.run_one())
    state = job_state(engine, version["document_id"])
    assert state["status"] == "queued" and state["attempts"] == 1
    assert state["code"] == "too_many_suggestions"
    for _ in range(2):
        with Session(engine) as session, session.begin():
            session.get(ScanJob, state["id"]).available_at = datetime.now(UTC)
        assert asyncio.run(worker.run_one())
    state = job_state(engine, version["document_id"])
    assert state["status"] == "failed" and state["attempts"] == 3
    scan = owner.get(f"/api/v1/documents/{version['document_id']}/scan").json()
    assert scan["status"] == "failed" and scan["suggestions"] == []
    assert owner.get(base).json()["documents"][0]["last_error_code"] == "too_many_suggestions"


@pytest.mark.parametrize(
    "mutation", ["revised", "settings_changed", "expired", "deleted", "revoked"]
)
def test_unavailable_or_changed_inputs_are_skipped_before_detection(intake_site, mutation):
    owner, headers, base = batch_client(intake_site)
    _, _, engine, workspace, actor = intake_site
    version = upload(owner, headers, base)
    document_base = f"/api/v1/documents/{version['document_id']}"
    if mutation == "revised":
        assert (
            owner.put(
                document_base + "/source",
                json={"expected": version, "source": "Revised fictional"},
                headers=headers,
            ).status_code
            == 200
        )
    elif mutation == "settings_changed":
        assert (
            owner.put(
                document_base + "/scan-settings",
                json={"expected": version, "categories": [], "phone_region": "GB"},
                headers=headers,
            ).status_code
            == 200
        )
    else:
        with Session(engine) as session, session.begin():
            document = session.get(Document, UUID(version["document_id"]))
            if mutation == "expired":
                document.created_at = datetime.now(UTC) - timedelta(days=2)
                document.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            elif mutation == "deleted":
                document.deleted_at = datetime.now(UTC)
            else:
                session.get(Membership, (workspace, actor)).revoked_at = datetime.now(UTC)
    worker = ScanWorker(engine, owner.app.state.settings)
    assert asyncio.run(worker.run_one())
    assert job_state(engine, version["document_id"])["status"] == "skipped"
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count(ScanRun.id)).where(
                    ScanRun.document_id == UUID(version["document_id"])
                )
            )
            == 0
        )


def test_busy_scan_defers_without_using_failure_budget(intake_site):
    owner, headers, base = batch_client(intake_site)
    _, _, engine, _, _ = intake_site
    version = upload(owner, headers, base)
    now = datetime.now(UTC)
    job = claim_job(engine, uuid4(), now)
    with Session(engine) as session, session.begin():
        document = session.get(Document, UUID(version["document_id"]))
        document.status = "scanning"
        session.add(
            ScanRun(
                document_id=document.id,
                source_revision_id=document.current_revision_id,
                settings_version=1,
                detector_version="2",
                status="scanning",
                started_at=now,
                attempt_count=1,
            )
        )
    assert execute_job(engine, job, KeyRing.from_settings(owner.app.state.settings)) == (
        "busy",
        None,
    )
    assert finish_job(engine, job, "busy", None, now)
    state = job_state(engine, version["document_id"])
    assert state["attempts"] == 0 and state["status"] == "queued" and state["code"] is None
    assert state["available"] == now + timedelta(seconds=5)


def test_awake_idle_worker_wakes_for_real_upload_before_idle_poll(intake_site):
    owner, headers, base = batch_client(intake_site)
    _, _, engine, _, _ = intake_site

    async def exercise():
        worker = owner.app.state.scan_worker
        running = asyncio.create_task(worker.run())
        try:
            await asyncio.sleep(0.1)
            started = asyncio.get_running_loop().time()
            version = await asyncio.to_thread(upload, owner, headers, base)
            deadline = started + 10
            while asyncio.get_running_loop().time() < deadline:
                state = await asyncio.to_thread(job_state, engine, version["document_id"])
                if state["status"] == "done":
                    assert asyncio.get_running_loop().time() - started < 5
                    return
                await asyncio.sleep(0.05)
            pytest.fail("Awake worker did not resume immediately after upload.")
        finally:
            running.cancel()
            with pytest.raises(asyncio.CancelledError):
                await running

    asyncio.run(exercise())
