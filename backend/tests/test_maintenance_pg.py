"""Real PostgreSQL credential budgets, bounded passes, retry health and concurrency."""

import asyncio
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.cleanup.service import purge_unavailable_content
from app.config import Settings
from app.db.durable import AttemptEvent
from app.db.maintenance import MaintenanceRun
from app.db.models import Document
from app.maintenance.service import run_cleanup
from tests.intake_support import _draft_body, _login
from tests.maintenance_support import TOKEN, configured

PATH = "/api/v1/maintenance/cleanup"
HEADERS = {"Authorization": "Bearer " + TOKEN}


def expired_documents(site, count=1):
    owner, _, engine, workspace, _ = site
    headers = _login(owner, "intake-owner@example.invalid")
    ids = []
    for _ in range(count):
        response = owner.post(
            "/api/v1/documents",
            json=_draft_body(workspace, source="MAINTENANCE_SENTINEL private source"),
            headers=headers,
        )
        assert response.status_code == 201
        ids.append(UUID(response.json()["version"]["document_id"]))
    now = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        for document_id in ids:
            row = session.get(Document, document_id)
            row.created_at = now - timedelta(days=2)
            row.expires_at = now - timedelta(days=1)
    return ids


def test_disabled_is_first_and_schema_never_changes(maintenance_site):
    owner = maintenance_site[0]
    assert owner.post(PATH, headers={"Authorization": "Bearer " + "a" * 600}).status_code == 404
    assert owner.post(PATH, headers=HEADERS).json()["code"] == "not_found"
    with configured(maintenance_site) as client:
        assert client.app.openapi() == owner.app.openapi()
        assert PATH not in client.app.openapi()["paths"]


@pytest.mark.parametrize(
    "header", [None, "Basic ignored", "Bearer ", "Bearer " + "a" * 513, "Bearer two words"]
)
def test_malformed_credentials_are_denied_without_run_budget(maintenance_site, header):
    with configured(maintenance_site) as client:
        response = client.post(PATH, headers={} if header is None else {"Authorization": header})
        assert response.status_code == 401 and response.json()["code"] == "maintenance_denied"
    with Session(maintenance_site[2]) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(AttemptEvent)
                .where(AttemptEvent.scope == "maintenance")
            )
            == 0
        )
        assert session.scalar(select(func.count()).select_from(MaintenanceRun)) == 0


@pytest.mark.parametrize("digest", ["x" * 64, "A" * 64, "a" * 63, "a" * 65])
def test_digest_configuration_requires_lowercase_sha256(maintenance_site, digest):
    values = maintenance_site[0].app.state.settings.model_dump() | {
        "maintenance_token_sha256": digest
    }
    with pytest.raises(ValidationError):
        Settings(**values, _env_file=None)


def test_wrong_credentials_have_a_separate_durable_network_budget(maintenance_site, caplog):
    engine = maintenance_site[2]
    with configured(maintenance_site) as client:
        for _ in range(30):
            assert (
                client.post(
                    PATH, headers={"Authorization": "Bearer private-wrong-token"}
                ).status_code
                == 401
            )
    with configured(maintenance_site) as restarted:
        assert (
            restarted.post(
                PATH, headers={"Authorization": "Bearer private-wrong-token"}
            ).status_code
            == 429
        )
        success = restarted.post(PATH, headers=HEADERS)
        assert success.status_code == 200  # no cookie, Origin or CSRF required
        assert set(success.json()) == {
            "documents_purged",
            "activity_removed",
            "expired_rows_removed",
            "more_remaining",
            "duration_ms",
            "started_at",
            "finished_at",
        }
    with Session(engine) as session:
        events = session.scalars(
            select(AttemptEvent).where(
                AttemptEvent.scope.in_(["maintenance", "maintenance_denied"])
            )
        ).all()
        assert sum(row.scope == "maintenance" for row in events) == 1
        assert sum(row.scope == "maintenance_denied" for row in events) == 30
        assert all(len(row.subject_hmac) == 32 for row in events)
    assert TOKEN not in caplog.text and "private-wrong-token" not in caplog.text


def test_twelve_valid_calls_share_one_global_budget_across_instances(maintenance_site):
    engine = create_engine(maintenance_site[2].url, hide_parameters=True)
    try:
        with (
            configured(maintenance_site) as first,
            configured(maintenance_site, engine=engine) as second,
        ):
            for index in range(12):
                assert (first if index % 2 else second).post(
                    PATH, headers=HEADERS
                ).status_code == 200
            assert second.post(PATH, headers=HEADERS).status_code == 429
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(MaintenanceRun)) == 12
    finally:
        engine.dispose()


def test_global_budget_resolves_simultaneous_last_attempt(maintenance_site):
    engine = create_engine(maintenance_site[2].url, hide_parameters=True)
    try:
        with (
            configured(maintenance_site) as first,
            configured(maintenance_site, engine=engine) as second,
        ):
            for _ in range(11):
                assert first.post(PATH, headers=HEADERS).status_code == 200
            with ThreadPoolExecutor(max_workers=2) as workers:
                futures = [
                    workers.submit(client.post, PATH, headers=HEADERS) for client in (first, second)
                ]
                assert sorted(future.result().status_code for future in futures) == [200, 429]
    finally:
        engine.dispose()


def test_concurrent_cleanup_purges_each_document_once_and_records_counts(maintenance_site, caplog):
    ids = expired_documents(maintenance_site, count=5)
    engine = create_engine(maintenance_site[2].url, hide_parameters=True)
    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            futures = [
                workers.submit(run_cleanup, target, trigger="endpoint", batch_size=1)
                for target in (maintenance_site[2], engine)
            ]
            results = [future.result() for future in futures]
        assert sum(result.documents_purged for result in results) == 5
        assert purge_unavailable_content(engine, now=datetime.now(UTC)).documents_purged == 0
        with Session(engine) as session:
            assert all(session.get(Document, doc).current_revision_id is None for doc in ids)
            rows = session.scalars(select(MaintenanceRun)).all()
            assert len(rows) == 2 and all(row.status == "ok" for row in rows)
            assert sum(row.documents_purged for row in rows) == 5
            assert "MAINTENANCE_SENTINEL" not in str([row.__dict__ for row in rows])
        assert "MAINTENANCE_SENTINEL" not in caplog.text
    finally:
        engine.dispose()


def test_deadline_returns_committed_counts_and_continuation(maintenance_site):
    expired_documents(maintenance_site, count=2)
    ticks = iter([0, 0, 25, 25])
    result = run_cleanup(
        maintenance_site[2], trigger="endpoint", batch_size=1, timer=lambda: next(ticks)
    )
    assert result.documents_purged == 1 and result.more_remaining and result.duration_ms == 25000
    following = run_cleanup(maintenance_site[2], trigger="cli")
    assert following.documents_purged == 1 and not following.more_remaining


def test_postgres_transaction_timeout_caps_many_short_statements(maintenance_site):
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError) as failure, maintenance_site[2].begin() as connection:
        connection.execute(text("SET LOCAL transaction_timeout = '60ms'"))
        for _ in range(6):
            connection.execute(text("SELECT pg_sleep(0.02)"))
    assert failure.value.orig.sqlstate == "25P04"
    with maintenance_site[2].connect() as connection:
        assert connection.scalar(text("SELECT 1")) == 1


def test_failure_is_content_free_and_next_run_can_retry(maintenance_site, monkeypatch, caplog):
    from app.maintenance import service

    original = service.purge_unavailable_content

    def fail(*_args, **_kwargs):
        raise RuntimeError("PRIVATE_ERROR_SENTINEL")

    monkeypatch.setattr(service, "purge_unavailable_content", fail)
    with pytest.raises(RuntimeError):
        run_cleanup(maintenance_site[2], trigger="periodic")
    with Session(maintenance_site[2]) as session:
        row = session.scalar(select(MaintenanceRun))
        assert row.status == "failed" and row.failure_code == "cleanup_failed"
        assert row.finished_at >= row.started_at
    assert "PRIVATE_ERROR_SENTINEL" not in caplog.text
    monkeypatch.setattr(service, "purge_unavailable_content", original)
    assert not run_cleanup(maintenance_site[2], trigger="periodic").more_remaining


def test_abandoned_records_and_latest_two_hundred_retention(maintenance_site):
    now = datetime.now(UTC)
    abandoned = uuid4()
    with Session(maintenance_site[2]) as session, session.begin():
        session.add_all(
            [
                MaintenanceRun(
                    id=uuid4(),
                    trigger="cli",
                    started_at=now - timedelta(hours=2, seconds=index),
                    finished_at=now - timedelta(hours=2, seconds=index),
                    status="ok",
                )
                for index in range(205)
            ]
        )
        session.add(
            MaintenanceRun(
                id=abandoned,
                trigger="startup",
                started_at=now - timedelta(hours=1, seconds=1),
                status="running",
            )
        )
    run_cleanup(maintenance_site[2], trigger="periodic", clock=lambda: now)
    with Session(maintenance_site[2]) as session:
        assert session.scalar(select(func.count()).select_from(MaintenanceRun)) == 200
        row = session.get(MaintenanceRun, abandoned)
        assert row.status == "failed" and row.failure_code == "abandoned" and row.finished_at == now


def test_real_operator_cli_leaves_its_run_record(maintenance_site):
    settings = maintenance_site[0].app.state.settings
    env = {
        **os.environ,
        "PGCONNECT_TIMEOUT": "3",
        "PRIVACY_REVIEW_DATABASE_URL": settings.database_url,
        "PRIVACY_REVIEW_ALLOWED_ORIGINS": json.dumps(settings.allowed_origins),
        "PRIVACY_REVIEW_ENVIRONMENT": "test",
        "PRIVACY_REVIEW_ACTIVE_KEY_ID": settings.active_key_id,
        "PRIVACY_REVIEW_CONTENT_KEYS": json.dumps(
            {key: value.get_secret_value() for key, value in settings.content_keys.items()}
        ),
    }
    response = subprocess.run(
        [sys.executable, "-m", "app.cleanup.runner"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert response.returncode == 0 and "Cleanup complete:" in response.stdout
    with Session(maintenance_site[2]) as session:
        assert session.scalar(select(MaintenanceRun)).trigger == "cli"


def test_periodic_loop_records_startup_then_periodic(maintenance_site, monkeypatch):
    from app.cleanup import runner

    sleeps = 0

    async def stop_after_two(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(runner.asyncio, "sleep", stop_after_two)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(runner.periodic_cleanup(maintenance_site[2]))
    with Session(maintenance_site[2]) as session:
        runs = session.scalars(select(MaintenanceRun).order_by(MaintenanceRun.started_at)).all()
        assert [row.trigger for row in runs] == ["startup", "periodic"]
        assert all(row.status == "ok" for row in runs)
