"""Real late authorization loss rolls back admin/account writes and withholds private JSON."""

from datetime import UTC, datetime, timedelta
from time import sleep
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session
from sqlalchemy.sql.dml import Update

from app.accounts.admin_api import MemberView, WorkspaceSettingsView
from app.accounts.api import SessionView
from app.accounts.second_factor_api import DeviceView, SecondFactorState
from app.db.models import Membership, User, Workspace
from app.db.models import Session as StoredSession
from tests.admin_access_support import (
    OPERATIONS,
    admin_case,
    after_work,
    cleanup_invitation,
    fingerprint,
    perform,
    revoke_current,
)

READS = ("members-read", "settings-read", "devices-read", "session-read", "factor-state")
WRITES = tuple(name for name in OPERATIONS if name not in READS)
ADMIN = OPERATIONS[:11]
CHANGED = ("settings-write", "role-change", "member-revoke", "member-restore", "invite",
           "factor-reset", "device-revoke", "devices-others", "password-change")
JSON = tuple(name for name in OPERATIONS if name not in (
    "factor-reset", "device-revoke", "devices-others", "password-change",
))


def deny(response, status, case):
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"].startswith("application/json")
    assert "intake-owner@example.invalid" not in response.text
    assert "intake-other@example.invalid" not in response.text
    if case["operation"] == "invite":
        assert case["body"]["email"] not in response.text


def lose_access(case, change):
    if change in ("revoked", "expired"):
        revoke_current(case, change)
    else:
        with Session(case["engine"]) as session, session.begin():
            if change == "disabled":
                session.get(User, case["actor"]).disabled_at = datetime.now(UTC)
            else:
                row = session.get(Membership, (case["workspace"], case["actor"]))
                if change == "role":
                    row.role = "member"
                else:
                    row.revoked_at = datetime.now(UTC)


def after_json(monkeypatch, case, change):
    operation = case["operation"]
    model = (SessionView if operation == "session-read" else
             DeviceView if operation == "devices-read" else
             SecondFactorState if operation == "factor-state" else
             WorkspaceSettingsView if operation.startswith("settings") else MemberView)
    original, fired = model.model_dump_json, []

    def serialized(*args, **kwargs):
        payload = original(*args, **kwargs)
        if not fired:
            fired.append(True)
            change()
        return payload

    monkeypatch.setattr(model, "model_dump_json", serialized)
    return fired


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("change", ("revoked", "expired", "membership"))
def test_prepared_admin_account_operations_recheck_current_access(intake_site, monkeypatch, operation, change):
    case = admin_case(intake_site, operation)
    try:
        before = fingerprint(case)
        fired = after_work(monkeypatch, case, lambda: lose_access(case, change))
        deny(perform(case), 401, case)
        assert fired and fingerprint(case) == before
        assert not case["mailer"].messages and not case["mailer"].notices
    finally:
        cleanup_invitation(case)


@pytest.mark.parametrize("operation", JSON)
@pytest.mark.parametrize("change", ("revoked", "expired", "disabled", "membership"))
def test_serialized_admin_account_json_rechecks_current_access(intake_site, monkeypatch, operation, change):
    case = admin_case(intake_site, operation)
    try:
        before = fingerprint(case)
        fired = after_json(monkeypatch, case, lambda: lose_access(case, change))
        deny(perform(case), 401, case)
        assert fired
        # Disabling the actor is itself an independent User change in this fingerprint.
        assert (fingerprint(case) != before) == (operation in CHANGED or change == "disabled")
        assert len(case["mailer"].messages) == int(operation == "invite")
    finally:
        cleanup_invitation(case)


@pytest.mark.parametrize("operation,phase", [(name, "prepared") for name in ADMIN] +
                         [(name, "serialized") for name in ADMIN if name in JSON])
def test_late_admin_role_loss_denies_scope_and_preserves_commit_boundary(intake_site, monkeypatch, operation, phase):
    case = admin_case(intake_site, operation)
    try:
        before = fingerprint(case)
        hook = after_json if phase == "serialized" else after_work
        fired = hook(monkeypatch, case, lambda: lose_access(case, "role"))
        deny(perform(case), 404, case)
        assert fired
        assert (fingerprint(case) != before) == (phase == "serialized" and operation in CHANGED)
        assert len(case["mailer"].messages) == int(phase == "serialized" and operation == "invite")
    finally:
        cleanup_invitation(case)


@pytest.mark.parametrize("operation", READS)
def test_session_ending_during_final_account_resource_queries_withholds_json(intake_site, monkeypatch, operation):
    from app.accounts import admin_api, api, second_factor_api

    case = admin_case(intake_site, operation)
    armed, fired = [], []
    after_json(monkeypatch, case, lambda: armed.append(True))
    module, name = {
        "members-read": (admin_api, "_member_view"), "settings-read": (admin_api, "_settings_view"),
        "devices-read": (second_factor_api, "list_devices"), "session-read": (api, "_view"),
        "factor-state": (second_factor_api, "security_status"),
    }[operation]
    original = getattr(module, name)

    def prepared(*args, **kwargs):
        result = original(*args, **kwargs)
        if armed and not fired:
            fired.append(True)
            revoke_current(case)
        return result

    monkeypatch.setattr(module, name, prepared)
    deny(perform(case), 401, case)
    assert fired


@pytest.mark.parametrize("operation", READS)
def test_serialized_account_metadata_changes_return_a_neutral_conflict(intake_site, monkeypatch, operation):
    case = admin_case(intake_site, operation)

    def changed():
        with Session(case["engine"]) as session, session.begin():
            if operation == "members-read":
                session.get(User, case["target"]).email = "changed-synthetic@example.invalid"
            elif operation in ("settings-read", "session-read"):
                session.get(Workspace, case["workspace"]).name = "Changed synthetic workspace"
            elif operation == "devices-read":
                session.get(StoredSession, case["target_session"]).revoked_at = datetime.now(UTC)
            else:
                from app.db.crypto import KeyRing
                from app.db.second_factor import UserSecondFactor
                protected = KeyRing.from_settings(case["client"].app.state.settings).encrypt_text("JBSWY3DPEHPK3PXP")
                session.add(UserSecondFactor(user_id=case["actor"], secret_ciphertext=protected.ciphertext,
                                            key_id=protected.key_id, status="pending", created_at=datetime.now(UTC)))

    fired = after_json(monkeypatch, case, changed)
    result = perform(case)
    deny(result, 409, case)
    assert fired


def test_unchanged_revoke_others_still_checks_access_before_commit(intake_site, monkeypatch):
    case = admin_case(intake_site, "devices-others")
    assert perform(case).status_code == 204
    case["mailer"].notices.clear()
    before, original, fired = fingerprint(case), Session.execute, []

    def executed(session, statement, *args, **kwargs):
        result = original(session, statement, *args, **kwargs)
        if isinstance(statement, Update) and statement.table.name == "sessions" and not fired:
            fired.append(True)
            assert result.rowcount == 0
            revoke_current(case)
        return result

    monkeypatch.setattr(Session, "execute", executed)
    deny(perform(case), 401, case)
    assert fired and fingerprint(case) == before and not case["mailer"].notices


def test_authorized_self_revoke_serializes_before_ending_its_own_session(intake_site):
    case = admin_case(intake_site, "member-revoke")
    with Session(case["engine"]) as session, session.begin():
        session.get(Membership, (case["workspace"], case["target"])).role = "administrator"
    case["path"] = f"/api/v1/workspaces/{case['workspace']}/members/{case['actor']}/revoke"
    result = perform(case)
    assert result.status_code == 200 and result.json()["revoked_at"]
    assert result.headers["cache-control"] == "no-store"
    assert case["client"].get("/api/v1/auth/session").status_code == 401


@pytest.mark.parametrize("operation", ("password-change", "device-revoke"))
def test_rechecks_do_not_write_last_seen_into_a_session_locked_by_the_request(intake_site, monkeypatch, operation):
    case = admin_case(intake_site, operation)
    if operation == "device-revoke":
        case["path"] = f"/api/v1/auth/sessions/{case['current_session']}/revoke"

    def bounded(connection, record, proxy):
        with connection.cursor() as cursor:
            cursor.execute("SET statement_timeout = '2s'")

    event.listen(case["engine"], "checkout", bounded)
    try:
        if operation == "password-change":
            def age():
                with Session(case["engine"]) as session, session.begin():
                    session.get(StoredSession, case["current_session"]).last_seen_at = datetime.now(UTC) - timedelta(minutes=6)
            fired = after_work(monkeypatch, case, age)
        else:
            from app.accounts import devices
            original, fired = devices.locked_user, []

            def locked(session, *args, **kwargs):
                user = original(session, *args, **kwargs)
                session.get(StoredSession, case["current_session"]).last_seen_at = datetime.now(UTC) - timedelta(minutes=6)
                session.flush()
                fired.append(True)
                return user

            monkeypatch.setattr(devices, "locked_user", locked)
        result = perform(case)
        assert fired and result.status_code == 204
        assert "Max-Age=0" in result.headers["set-cookie"]
        assert case["client"].get("/api/v1/auth/session").status_code == 401
    finally:
        event.remove(case["engine"], "checkout", bounded)


@pytest.mark.parametrize("operation", WRITES)
def test_admin_account_writes_recheck_access_after_the_actual_lock(intake_site, monkeypatch, operation):
    from app.accounts import devices, memberships, reset_second_factor, security

    case = admin_case(intake_site, operation)
    try:
        before = fingerprint(case)
        module, name = ((security, "_verify_password") if operation == "password-change" else
                        (reset_second_factor, "locked_user") if operation == "factor-reset" else
                        (devices, "locked_user") if operation.startswith("device") else
                        (memberships, "require_administrator"))
        original, fired = getattr(module, name), []

        def locked(*args, **kwargs):
            result = original(*args, **kwargs)
            if (name != "require_administrator" or kwargs.get("lock")) and not fired:
                fired.append(True)
                revoke_current(case)
            return result

        monkeypatch.setattr(module, name, locked)
        deny(perform(case), 401, case)
        assert fired and fingerprint(case) == before
        assert not case["mailer"].messages and not case["mailer"].notices
    finally:
        cleanup_invitation(case)


@pytest.mark.parametrize("operation,phase", [(name, phase) for name in (
    "members-read", "settings-write", "role-change", "member-revoke", "invite", "factor-reset",
) for phase in ("prepared", "serialized") if phase == "prepared" or name in JSON])
def test_admin_grant_loss_is_denied_with_another_active_workspace(intake_site, monkeypatch, operation, phase):
    case = admin_case(intake_site, operation)
    additional = uuid4()
    with Session(case["engine"]) as session, session.begin():
        session.add(Workspace(id=additional, name="Another synthetic account workspace"))
        session.flush()
        session.add(Membership(workspace_id=additional, user_id=case["actor"], role="administrator"))
    try:
        before = fingerprint(case)
        hook = after_json if phase == "serialized" else after_work
        fired = hook(monkeypatch, case, lambda: lose_access(case, "membership"))
        deny(perform(case), 404, case)
        assert fired and case["client"].get("/api/v1/auth/session").status_code == 200
        assert (fingerprint(case) != before) == (phase == "serialized" and operation in CHANGED)
    finally:
        cleanup_invitation(case)
        with Session(case["engine"]) as session, session.begin():
            session.delete(session.get(Membership, (additional, case["actor"])))
            session.delete(session.get(Workspace, additional))


@pytest.mark.parametrize("change", ("other-admin-role", "new-target-membership"))
def test_reset_rechecks_all_current_target_workspaces_before_commit(intake_site, monkeypatch, change):
    case = admin_case(intake_site, "factor-reset")
    additional = uuid4()
    with Session(case["engine"]) as session, session.begin():
        session.add(Workspace(id=additional, name="Additional synthetic reset scope"))
        session.flush()
        if change == "other-admin-role":
            session.add_all([
                Membership(workspace_id=additional, user_id=case["actor"], role="administrator"),
                Membership(workspace_id=additional, user_id=case["target"], role="member"),
            ])
    try:
        before = fingerprint(case)

        def changed():
            with Session(case["engine"]) as session, session.begin():
                if change == "other-admin-role":
                    session.get(Membership, (additional, case["actor"])).role = "member"
                else:
                    session.add(Membership(workspace_id=additional, user_id=case["target"], role="member"))

        fired = after_work(monkeypatch, case, changed)
        response = perform(case)
        deny(response, 403, case)
        assert fired and response.json()["code"] == "reset_requires_operator"
        assert fingerprint(case) == before and not case["mailer"].notices
    finally:
        with Session(case["engine"]) as session, session.begin():
            for row in session.query(Membership).filter(Membership.workspace_id == additional):
                session.delete(row)
            session.flush()
            session.delete(session.get(Workspace, additional))


def test_self_revoke_rolls_back_if_real_session_expiry_passes_during_serialization(intake_site, monkeypatch):
    case = admin_case(intake_site, "member-revoke")
    expiry = datetime.now(UTC) + timedelta(seconds=2)
    with Session(case["engine"]) as session, session.begin():
        session.get(Membership, (case["workspace"], case["target"])).role = "administrator"
        session.get(StoredSession, case["current_session"]).expires_at = expiry
    case["path"] = f"/api/v1/workspaces/{case['workspace']}/members/{case['actor']}/revoke"
    before = fingerprint(case)
    fired = after_json(monkeypatch, case, lambda: sleep(max(0, (expiry - datetime.now(UTC)).total_seconds()) + 0.02))
    deny(perform(case), 401, case)
    assert fired and fingerprint(case) == before
    with Session(case["engine"]) as session:
        assert session.get(Membership, (case["workspace"], case["actor"])).revoked_at is None
        assert session.get(StoredSession, case["current_session"]).revoked_at is None
