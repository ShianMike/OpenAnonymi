"""Actual decision history, metadata isolation and bounded administrator CSV."""

import csv
import io
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, event, select
from sqlalchemy.orm import Session

from app.accounts.limits import AttemptLimiter
from app.db.models import AuditEvent, Decision, Membership, User, Workspace
from app.db.models import Session as StoredSession
from app.errors import ApiError
from app.factory import create_app
from tests.csv_support import set_rules, upload_csv
from tests.intake_support import _login
from tests.styles_support import decide, draft


def setup(site):
    owner, admin, engine, workspace, actor = site
    headers = _login(owner, "intake-owner@example.invalid")
    admin_headers = _login(admin, "intake-other@example.invalid")
    admin_id = UUID(admin.get("/api/v1/auth/session").json()["user_id"])
    with Session(engine) as session, session.begin():
        session.get(Membership, (workspace, admin_id)).role = "administrator"
    path = f"/api/v1/workspaces/{workspace}/activity/admin"
    return owner, admin, engine, workspace, actor, admin_id, headers, admin_headers, path


def history(admin, path, headers, **extra):
    response = admin.post(path, json={"days": 30, **extra}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def changes(engine, document_id):
    with Session(engine) as session:
        return session.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.document_id == UUID(document_id),
                AuditEvent.decision_version.is_not(None),
            )
            .order_by(AuditEvent.decision_version)
        ).all()


def test_real_decisions_style_changes_and_undo_are_source_free_in_admin_json_csv(intake_site):
    owner, admin, _engine, workspace, actor, _, headers, ah, path = setup(intake_site)
    base, state = draft(
        owner,
        headers,
        workspace,
        "PRIVATE SOURCE CANARY nora@example.test",
        [("nora@example.test", "email")],
        title="PRIVATE TITLE CANARY",
    )
    finding = state["findings"][0]
    for action, style, option, extra in (
        ("keep", "token", None, {"keep_reason": "intended_disclosure"}),
        ("redact", "partial_mask", "email_domain", {}),
    ):
        response = decide(owner, headers, base, state, finding, action, style, option, **extra)
        assert response.status_code == 200
        state = response.json()
    undone = owner.post(base + "/review/undo", json={"expected": state["version"]}, headers=headers)
    assert undone.status_code == 200 and undone.json()["findings"][0]["action"] == "keep"
    saved = history(admin, path, ah)
    diffs = sorted(
        (row for row in saved["events"] if row["decision_changes"]),
        key=lambda row: row["decision_version"],
    )
    assert len(diffs) == 3
    assert [row["actor_id"] for row in diffs] == [str(actor)] * 3
    assert [row["decision_changes"][0]["before_action"] for row in diffs] == [
        None,
        "keep",
        "redact",
    ]
    assert [row["decision_changes"][0]["after_action"] for row in diffs] == [
        "keep",
        "redact",
        "keep",
    ]
    assert diffs[1]["decision_changes"][0]["after_style"] == "partial_mask"
    assert diffs[1]["decision_changes"][0]["after_option"] == "email_domain"
    assert all(row["decision_change_count"] == 1 for row in diffs)
    response = admin.post(path + "/csv", json={"days": 30}, headers=ah)
    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert len(rows) == len(saved["events"])
    csv_diffs = [
        json.loads(row["decision_changes"]) for row in rows if row["decision_change_count"] != "0"
    ]
    assert len(csv_diffs) == 3
    for payload in (json.dumps(saved), response.content.decode("utf-8-sig")):
        for private in (
            "PRIVATE SOURCE CANARY",
            "PRIVATE TITLE CANARY",
            "nora@example.test",
            "intended_disclosure",
            "keep_reason",
            "group_id",
            "start_offset",
            "label",
        ):
            assert private not in payload
    allowed = {
        "finding_id",
        "category",
        "before_action",
        "before_style",
        "before_option",
        "after_action",
        "after_style",
        "after_option",
    }
    assert all(set(change) == allowed for changes_ in csv_diffs for change in changes_)
    assert all(
        not value.lstrip().startswith(("=", "+", "-", "@"))
        for row in rows
        for value in row.values()
    )
    assert admin.get(base + "/source").status_code == 404
    assert admin.get(base + "/findings").status_code == 404
    assert admin.get(f"/api/v1/workspaces/{workspace}/documents").json() == []
    personal = owner.get(f"/api/v1/workspaces/{workspace}/activity").json()
    assert "decision_changes" not in json.dumps(personal)
    assert owner.post(path, json={}, headers=headers).status_code == 404
    assert owner.post(path + "/csv", json={}, headers=headers).status_code == 404


@pytest.mark.parametrize("operation", ["removed", "corrected"])
def test_removing_or_correcting_decided_finding_and_undo_record_actual_transition(
    intake_site, operation
):
    owner, _admin, engine, workspace, _, _, headers, _ah, _path = setup(intake_site)
    base, state = draft(
        owner, headers, workspace, "Nora nora@example.test", [("nora@example.test", "email")]
    )
    finding = state["findings"][0]
    state = decide(owner, headers, base, state, finding, "label").json()
    path = base + "/findings/" + finding["finding_id"]
    if operation == "removed":
        response = owner.post(
            path + "/remove", json={"expected": state["version"]}, headers=headers
        )
    else:
        response = owner.put(
            path,
            json={
                "expected": state["version"],
                "span": {"start": 0, "end": 4},
                "category": "person",
            },
            headers=headers,
        )
    assert response.status_code == 200, response.text
    undone = owner.post(
        base + "/review/undo", json={"expected": response.json()["version"]}, headers=headers
    )
    assert undone.status_code == 200
    events = changes(engine, state["version"]["document_id"])
    assert [row.event_code for row in events] == [
        "review_decision_saved",
        "finding_" + operation,
        "review_edit_undone",
    ]
    assert [
        (row.decision_changes[0]["before_action"], row.decision_changes[0]["after_action"])
        for row in events
    ] == [(None, "label"), ("label", None), (None, "label")]


def test_stale_or_repeated_identical_decision_does_not_fabricate_diff(intake_site):
    owner, _, engine, workspace, _, _, headers, _, _ = setup(intake_site)
    base, state = draft(owner, headers, workspace, "Nora", [("Nora", "person")])
    original = state
    state = decide(owner, headers, base, state, state["findings"][0], "redact").json()
    assert (
        decide(owner, headers, base, original, original["findings"][0], "label").status_code == 409
    )
    repeated = decide(owner, headers, base, state, state["findings"][0], "redact")
    assert repeated.status_code == 200
    events = changes(engine, state["version"]["document_id"])
    assert len(events) == 2 and events[0].decision_change_count == 1
    assert events[1].decision_changes == [] and events[1].decision_change_count == 0


def test_actual_column_bulk_diff_is_bounded_with_total_and_undo(intake_site):
    owner, admin, engine, workspace, _, _, headers, ah, path = setup(intake_site)
    base, _state, _source = upload_csv(
        owner,
        headers,
        workspace,
        "Name\n" + "Nora\n" * 260,
        header="true",
        delimiter=",",
        scan=False,
    )
    configured = set_rules(
        owner, headers, base, [{"column": 0, "mode": "category", "category": "person"}]
    )
    assert configured.status_code == 200
    assert (
        owner.post(
            base + "/scan", json={"expected": configured.json()["version"]}, headers=headers
        ).status_code
        == 200
    )
    state = owner.get(base + "/findings").json()
    assert len(state["findings"]) == 260
    response = owner.post(
        base + "/columns/0/decision",
        json={
            "expected": state["version"],
            "action": "redact",
            "affected_finding_ids": [row["finding_id"] for row in state["findings"]],
            "same_text_same_entity": False,
        },
        headers=headers,
    )
    assert response.status_code == 200
    recorded = changes(engine, state["version"]["document_id"])[-1]
    assert recorded.decision_change_count == 260 and len(recorded.decision_changes) == 256
    assert {item["after_action"] for item in recorded.decision_changes} == {"redact"}
    assert (
        owner.post(
            base + "/review/undo", json={"expected": response.json()["version"]}, headers=headers
        ).status_code
        == 200
    )
    saved = history(admin, path, ah, event_code="review_edit_undone")
    assert saved["events"][0]["decision_change_count"] == 260
    assert len(saved["events"][0]["decision_changes"]) == 256
    assert {change["after_action"] for change in saved["events"][0]["decision_changes"]} == {None}


def test_audit_failure_rolls_back_decision_version_and_undo(intake_site, monkeypatch):
    from app.groups import decisions

    owner, _, engine, workspace, _, _, headers, _, _ = setup(intake_site)
    base, state = draft(owner, headers, workspace, "Nora", [("Nora", "person")])

    def unavailable(*args, **kwargs):
        raise ApiError(503, "activity_unavailable", "Activity metadata is unavailable.")

    monkeypatch.setattr(decisions, "record_event", unavailable)
    response = decide(owner, headers, base, state, state["findings"][0], "redact")
    assert response.status_code == 503
    assert owner.get(base + "/findings").json() == state
    with Session(engine) as session:
        assert session.get(Decision, UUID(state["findings"][0]["finding_id"])) is None
        assert not changes(engine, state["version"]["document_id"])


def test_filters_cursor_time_retention_legacy_and_workspace_isolation(intake_site):
    _owner, admin, engine, workspace, actor, _, _headers, ah, path = setup(intake_site)
    now = datetime.now(UTC)
    ids = sorted(uuid4() for _ in range(5))
    alternate = uuid4()
    try:
        with Session(engine) as session, session.begin():
            session.get(Workspace, workspace).activity_retention_days = 7
            session.add(Workspace(id=alternate, name="Outside activity scope"))
            session.flush()
            for id_ in ids:
                session.add(
                    AuditEvent(
                        id=id_,
                        workspace_id=workspace,
                        actor_id=actor,
                        event_code="review_decision_saved",
                        outcome="completed",
                        occurred_at=now - timedelta(hours=1),
                    )
                )
            for ws, age, code in (
                (workspace, 8, "review_decision_saved"),
                (workspace, -1, "review_decision_saved"),
                (workspace, 1, "document_deleted"),
                (alternate, 1, "review_decision_saved"),
            ):
                session.add(
                    AuditEvent(
                        id=uuid4(),
                        workspace_id=ws,
                        actor_id=actor,
                        event_code=code,
                        outcome="completed",
                        occurred_at=now - timedelta(days=age),
                    )
                )
        value = history(admin, path, ah, days=90, event_code="review_decision_saved", limit=2)
        assert (
            6.99
            < (
                datetime.fromisoformat(value["as_of"]) - datetime.fromisoformat(value["since"])
            ).total_seconds()
            / 86400
            < 7.01
        )
        seen = value["events"]
        while value["next_cursor"]:
            value = history(
                admin,
                path,
                ah,
                days=90,
                event_code="review_decision_saved",
                limit=2,
                cursor=value["next_cursor"],
            )
            seen.extend(value["events"])
        assert [row["id"] for row in seen] == [str(id_) for id_ in reversed(ids)]
        assert all(
            row["decision_changes"] == [] and row["decision_version"] is None for row in seen
        )
        outside = admin.post(f"/api/v1/workspaces/{alternate}/activity/admin", json={}, headers=ah)
        assert outside.status_code == 404
        csv_response = admin.post(
            path + "/csv",
            json={
                "days": 90,
                "event_code": "review_decision_saved",
                "limit": 1,
                "cursor": {"occurred_at": now.isoformat(), "id": str(uuid4())},
            },
            headers=ah,
        )
        assert csv_response.status_code == 200
        assert len(list(csv.DictReader(io.StringIO(csv_response.content.decode("utf-8-sig"))))) == 5
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(Workspace).where(Workspace.id == alternate))


@pytest.mark.parametrize(
    "body",
    [
        {"days": 0},
        {"days": 91},
        {"days": True},
        {"limit": 51},
        {"event_code": "PRIVATE CANARY"},
        {"source": "PRIVATE CANARY"},
        {"cursor": {"occurred_at": "2026-10-04T00:00:00", "id": str(uuid4())}},
    ],
)
def test_strict_bounded_activity_requests_never_echo_private_input(intake_site, body):
    _, admin, _, _, _, _, _, ah, path = setup(intake_site)
    for endpoint in (path, path + "/csv"):
        response = admin.post(endpoint, json=body, headers=ah)
        assert response.status_code == 422 and "PRIVATE CANARY" not in response.text


def test_exact_origin_csrf_and_member_access(intake_site):
    owner, admin, _, _, _, _, headers, ah, path = setup(intake_site)
    for endpoint in (path, path + "/csv"):
        for bad in (
            {},
            {"Origin": ah["Origin"]},
            {**ah, "Origin": "https://attacker.invalid"},
            {**ah, "X-CSRF-Token": "wrong"},
        ):
            assert admin.post(endpoint, json={}, headers=bad).status_code == 403
        assert owner.post(endpoint, json={}, headers=headers).status_code == 404


@pytest.mark.parametrize("change", ["role", "membership", "disabled", "session"])
@pytest.mark.parametrize("endpoint", ["list", "csv"])
def test_late_access_change_after_list_or_csv_render_refuses_metadata(
    intake_site, monkeypatch, change, endpoint
):
    from app.workspace import admin_activity

    _owner, admin, engine, workspace, _actor, admin_id, _, ah, path = setup(intake_site)

    def revoke():
        with Session(engine) as session, session.begin():
            if change == "role":
                session.get(Membership, (workspace, admin_id)).role = "member"
            elif change == "membership":
                session.get(Membership, (workspace, admin_id)).revoked_at = datetime.now(UTC)
            elif change == "disabled":
                session.get(User, admin_id).disabled_at = datetime.now(UTC)
            else:
                for row in session.scalars(
                    select(StoredSession).where(StoredSession.user_id == admin_id)
                ):
                    row.revoked_at = datetime.now(UTC)

    name = "read_admin_activity" if endpoint == "list" else "activity_csv"
    original = getattr(admin_activity, name)

    def finish_then_revoke(*args, **kwargs):
        value = original(*args, **kwargs)
        revoke()
        return value

    monkeypatch.setattr(admin_activity, name, finish_then_revoke)
    response = admin.post(path + ("/csv" if endpoint == "csv" else ""), json={}, headers=ah)
    assert response.status_code == (404 if change == "role" else 401)
    assert "events" not in response.text and "occurred_at" not in response.text


def test_role_change_during_database_load_is_freshly_checked(intake_site):
    _, admin, engine, workspace, _, admin_id, _, ah, path = setup(intake_site)
    changed = False

    def demote_after_query(connection, cursor, statement, parameters, context, executemany):
        nonlocal changed
        if not changed and statement.startswith("SELECT audit_events."):
            changed = True
            with Session(engine) as session, session.begin():
                session.get(Membership, (workspace, admin_id)).role = "member"

    event.listen(engine, "after_cursor_execute", demote_after_query)
    try:
        assert admin.post(path, json={}, headers=ah).status_code == 404
        assert changed
    finally:
        event.remove(engine, "after_cursor_execute", demote_after_query)


def test_invalid_stored_diff_fails_closed_without_serializing_extra_content(intake_site):
    _, admin, engine, workspace, actor, _, _, ah, path = setup(intake_site)
    with Session(engine) as session, session.begin():
        session.add(
            AuditEvent(
                id=uuid4(),
                workspace_id=workspace,
                actor_id=actor,
                event_code="review_decision_saved",
                outcome="completed",
                occurred_at=datetime.now(UTC),
                decision_change_count=1,
                decision_changes=[{"source": "STORED PRIVATE CANARY"}],
            )
        )
    for endpoint in (path, path + "/csv"):
        response = admin.post(endpoint, json={}, headers=ah)
        assert response.status_code == 503 and "STORED PRIVATE CANARY" not in response.text


def test_csv_event_bound_refuses_partial_export_and_persistent_limit(intake_site):
    _, admin, engine, workspace, actor, admin_id, _, ah, path = setup(intake_site)
    now = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        session.add_all(
            AuditEvent(
                id=uuid4(),
                workspace_id=workspace,
                actor_id=actor,
                event_code="review_decision_saved",
                outcome="completed",
                occurred_at=now,
            )
            for _ in range(1001)
        )
    response = admin.post(path + "/csv", json={}, headers=ah)
    assert response.status_code == 413 and response.json()["code"] == "activity_export_limit"
    narrowed = admin.post(path + "/csv", json={"event_code": "document_deleted"}, headers=ah)
    assert narrowed.status_code == 200 and len(narrowed.content.splitlines()) == 1
    limiter = AttemptLimiter(
        engine,
        admin.app.state.settings,
        scope="admin_activity_export",
        maximum=10,
        window_seconds=60,
        network_scope=False,
    )
    assert all(limiter.take(str(admin_id)) for _ in range(8))
    with TestClient(create_app(admin.app.state.settings, engine=engine)) as restarted:
        restarted.cookies.update(admin.cookies)
        assert (
            restarted.post(
                path + "/csv", json={"event_code": "document_deleted"}, headers=ah
            ).status_code
            == 429
        )


def test_csv_byte_bound_refuses_before_loading_large_diff_payloads(intake_site):
    _, admin, engine, workspace, actor, _, _, ah, path = setup(intake_site)
    change = {
        "finding_id": str(uuid4()),
        "category": "email",
        "before_action": "redact",
        "before_style": "partial_mask",
        "before_option": "email_domain",
        "after_action": "redact",
        "after_style": "partial_mask",
        "after_option": "email_first",
    }
    with Session(engine) as session, session.begin():
        session.add_all(
            AuditEvent(
                id=uuid4(),
                workspace_id=workspace,
                actor_id=actor,
                event_code="review_decision_saved",
                outcome="completed",
                occurred_at=datetime.now(UTC),
                decision_change_count=256,
                decision_changes=[change] * 256,
            )
            for _ in range(140)
        )
    loaded = []

    def observe(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("SELECT audit_events.id, audit_events.workspace_id"):
            loaded.append(True)

    event.listen(engine, "before_cursor_execute", observe)
    try:
        response = admin.post(path + "/csv", json={}, headers=ah)
        assert response.status_code == 413 and response.json()["code"] == "activity_export_limit"
        assert not loaded
    finally:
        event.remove(engine, "before_cursor_execute", observe)
