"""Administrator scope is current at the actual SQL read and after a lock wait."""

import inspect
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from queue import Queue
from time import monotonic, sleep

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from app.accounts.access import WorkspaceAccessDenied, require_administrator
from app.db.models import Membership, User, Workspace
from tests.admin_access_support import admin_case, perform
from tests.reporting_access_support import make_case
from tests.test_custom_rules_pg import admin_headers

READS = ("overview", "activity", "admin-activity", "admin-csv", "members-read", "settings-read")


def scope_case(site, operation):
    if operation in ("members-read", "settings-read"):
        return admin_case(site, operation)
    case = make_case(site, "admin-activity" if operation == "admin-csv" else operation)
    if operation == "admin-csv":
        case["path"] += "/csv"
    return case


def watch_final_scope_read(case):
    """Commit a genuine demotion just before the final guard reads User."""
    fired = []

    def before(connection, cursor, statement, parameters, context, executemany):
        clause = getattr(getattr(context, "compiled", None), "statement", None)
        if fired or not getattr(clause, "is_select", False) or "users" not in statement.lower():
            return
        frame = inspect.currentframe()
        try:
            while frame is not None and frame.f_code.co_name != "require_administrator":
                frame = frame.f_back
            if frame is None:
                return
            caller = frame.f_back
            if caller is None or not (
                caller.f_code.co_name == "require_current_admin"
                or caller.f_code.co_name == "authorize"
                and Path(caller.f_code.co_filename).name in ("admin_api.py", "api.py")
            ):
                return
            fired.append(True)
            with Session(case["engine"]) as session, session.begin():
                session.get(Membership, (case["workspace"], case["actor"])).role = "member"
        finally:
            del frame

    event.listen(case["engine"], "before_cursor_execute", before)
    return fired, lambda: event.remove(case["engine"], "before_cursor_execute", before)


@pytest.mark.parametrize("operation", READS)
def test_final_administrator_read_denies_committed_demotion(intake_site, operation):
    case = scope_case(intake_site, operation)
    fired, remove = watch_final_scope_read(case)
    try:
        response = perform(case)
    finally:
        remove()
    assert fired and response.status_code == 404
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"code": "workspace_not_found", "message": "Workspace not found.", "details": []}
    assert case["client"].get("/api/v1/auth/session").status_code == 200
    with Session(case["engine"]) as session:
        assert session.get(Membership, (case["workspace"], case["actor"])).role == "member"


@pytest.mark.parametrize("change", ("role", "membership", "disabled"))
def test_locked_administrator_scope_is_read_after_actual_lock_wait(intake_site, change):
    _, _, engine, workspace, actor = intake_site
    admin_headers(intake_site)
    reader_pid = Queue()

    def read_scope():
        with Session(engine) as session, session.begin():
            reader_pid.put(session.scalar(text("SELECT pg_backend_pid()")))
            with pytest.raises(WorkspaceAccessDenied):
                require_administrator(session, workspace_id=workspace, actor_id=actor, lock=True)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with Session(engine) as writer, writer.begin():
            writer.scalar(select(Workspace.id).where(Workspace.id == workspace).with_for_update(key_share=True))
            member = writer.get(Membership, (workspace, actor))
            if change == "role":
                member.role = "member"
            elif change == "membership":
                member.revoked_at = datetime.now(UTC)
            else:
                writer.get(User, actor).disabled_at = datetime.now(UTC)
            writer.flush()
            task = pool.submit(read_scope)
            pid = reader_pid.get(timeout=10)
            blocked, deadline = False, monotonic() + 10
            with Session(engine) as observer:
                while monotonic() < deadline:
                    # Query PostgreSQL, rather than assuming a thread reached its lock.
                    observer.commit()
                    blocked = observer.scalar(text(
                        "SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"
                    ), {"pid": pid})
                    if blocked:
                        break
                    sleep(0.01)
            # Commit/unlock even on a failed observation so the worker can finish.
        task.result(timeout=10)
    assert blocked
