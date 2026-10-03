"""Real PostgreSQL budgets across independent callers and concurrent requests."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine, delete, func, insert, select
from sqlalchemy.orm import Session

from app.accounts.limits import AttemptLimiter
from app.config import Settings
from app.db.durable import AttemptEvent


def clone(settings):
    return Settings(**settings.model_dump(), _env_file=None)


def test_concurrent_instances_share_one_budget_and_denials_are_not_recorded(intake_site):
    owner, _, engine, _, _ = intake_site
    scope = "concurrent_" + uuid4().hex
    settings = owner.app.state.settings
    second_engine = create_engine(settings.database_url, pool_pre_ping=True, hide_parameters=True)
    stores = [
        AttemptLimiter(engine if i % 2 else second_engine, clone(settings), scope=scope, maximum=3)
        for i in range(8)
    ]
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            allowed = list(pool.map(lambda i: stores[i % 8].take("203.0.113.9"), range(24)))
        assert sum(allowed) == 3
        restarted = AttemptLimiter(engine, clone(settings), scope=scope, maximum=3)
        assert not restarted.take("203.0.113.9")
        with Session(engine) as session:
            rows = session.scalars(select(AttemptEvent).where(AttemptEvent.scope == scope)).all()
            assert len(rows) == 3 and all(len(row.subject_hmac) == 32 for row in rows)
            assert all(b"203.0.113.9" not in row.subject_hmac for row in rows)
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(AttemptEvent).where(AttemptEvent.scope == scope))
        second_engine.dispose()


def test_sliding_window_boundary_and_scope_isolation(intake_site):
    owner, _, engine, _, _ = intake_site
    scope = "window_" + uuid4().hex
    now = datetime.now(UTC)
    store = AttemptLimiter(
        engine, owner.app.state.settings, scope=scope, maximum=2, window_seconds=300
    )
    other = AttemptLimiter(engine, owner.app.state.settings, scope=scope + "_b", maximum=1)
    try:
        assert store.take("synthetic", now=now)
        assert store.take("synthetic", now=now + timedelta(seconds=1))
        assert not store.take("synthetic", now=now + timedelta(seconds=299))
        assert store.take("synthetic", now=now + timedelta(seconds=300))
        assert not store.take("synthetic", now=now + timedelta(seconds=300))
        assert other.take("synthetic", now=now)
    finally:
        with Session(engine) as session, session.begin():
            session.execute(
                delete(AttemptEvent).where(AttemptEvent.scope.in_([scope, scope + "_b"]))
            )


def test_network_cap_does_not_apply_to_address_budgets(intake_site):
    owner, _, engine, _, _ = intake_site
    scope = "cap_" + uuid4().hex
    settings = owner.app.state.settings
    network = AttemptLimiter(engine, settings, scope=scope, maximum=2, subject_cap=2)
    addresses = AttemptLimiter(
        engine, settings, scope=scope + "_address", maximum=2, network_scope=False
    )
    now = datetime.now(UTC)
    try:
        assert network.take("network-a") and network.take("network-b")
        assert not network.take("network-c")
        assert network.take("network-a")
        with Session(engine) as session, session.begin():
            session.execute(
                insert(AttemptEvent),
                [
                    {
                        "id": uuid4(),
                        "scope": addresses.scope,
                        "subject_hmac": addresses._digest(f"synthetic-{i}"),
                        "attempted_at": now,
                    }
                    for i in range(10001)
                ],
            )
        assert addresses.take("new-account@example.test", now=now)
        with Session(engine) as session:
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(AttemptEvent)
                    .where(AttemptEvent.scope == addresses.scope)
                )
                == 10002
            )
    finally:
        with Session(engine) as session, session.begin():
            session.execute(
                delete(AttemptEvent).where(AttemptEvent.scope.in_([scope, addresses.scope]))
            )
