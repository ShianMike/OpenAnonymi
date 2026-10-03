"""Real reset scope, forced enrollment, policy races and post-commit notices."""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from app.accounts.memberships import update_workspace_settings
from app.accounts.recovery import RecoveryDeliveryError
from app.accounts.reset_second_factor import reset_factor
from app.accounts.second_factor import FactorError, change_factor
from app.db.models import Membership, User, Workspace
from app.db.models import Session as StoredSession
from app.db.second_factor import UserBackupCode, UserSecondFactor
from tests.intake_support import ORIGIN, PASSWORD, _login
from tests.mail_support import Mailbox
from tests.second_factor_support import enroll, invalid_code, password_step, totp


def make_admin(engine, workspace_id, user_id):
    with Session(engine) as session, session.begin():
        session.get(Membership, (workspace_id, user_id)).role = "administrator"


def target_id(engine):
    with Session(engine) as session:
        return session.scalar(select(User.id).where(User.email == "intake-other@example.invalid"))


def policy(client, headers, workspace_id, required):
    view = client.get(f"/api/v1/workspaces/{workspace_id}/settings").json()
    return client.put(
        f"/api/v1/workspaces/{workspace_id}/settings",
        headers=headers,
        json={
            "expected_version": view["settings_version"],
            "content_retention_days": 7,
            "activity_retention_days": 90,
            "require_second_factor": required,
        },
    )


def test_admin_reset_forces_real_enrollment_and_revokes_sessions(intake_site):
    owner, other, engine, workspace_id, admin_id = intake_site
    make_admin(engine, workspace_id, admin_id)
    headers = _login(owner, "intake-owner@example.invalid")
    _, old_key, old_codes = enroll(other, email="intake-other@example.invalid")
    member_id = target_id(engine)
    owner.app.state.recovery_mailer = other.app.state.recovery_mailer = mailer = Mailbox()
    response = owner.post(
        f"/api/v1/workspaces/{workspace_id}/members/{member_id}/second-factor/reset",
        headers=headers,
    )
    assert response.status_code == 204
    assert other.get("/api/v1/auth/session").status_code == 401
    with Session(engine) as session:
        assert session.get(UserSecondFactor, member_id) is None
        assert not session.scalars(
            select(UserBackupCode).where(UserBackupCode.user_id == member_id)
        ).all()
        assert session.get(User, member_id).second_factor_reenroll_required
    assert (
        password_step(other, "intake-other@example.invalid").json()["status"]
        == "enrollment_required"
    )
    assert other.get("/api/v1/auth/session").status_code == 401
    initial = other.post("/api/v1/auth/sign-in/enrollment/start", headers={"Origin": ORIGIN})
    assert initial.status_code == 200 and initial.json()["manual_key"] != old_key
    key = initial.json()["manual_key"]
    assert (
        other.post(
            "/api/v1/auth/sign-in/enrollment/confirm",
            headers={"Origin": ORIGIN},
            json={"code": invalid_code(key)},
        ).status_code
        == 400
    )
    confirmed = other.post(
        "/api/v1/auth/sign-in/enrollment/confirm",
        headers={"Origin": ORIGIN},
        json={"code": totp(key)},
    )
    assert confirmed.status_code == 200 and confirmed.json()["session"]["second_factor_enabled"]
    assert len(confirmed.json()["backup_codes"]) == 10 and not set(old_codes) & set(
        confirmed.json()["backup_codes"]
    )
    assert "Max-Age=0" in confirmed.headers["set-cookie"]
    assert other.get("/api/v1/auth/session").json()["second_factor_enabled"]
    with Session(engine) as session:
        assert not session.get(User, member_id).second_factor_reenroll_required
    assert [notice[1] for notice in mailer.notices] == [
        "second_factor_reset",
        "second_factor_enabled",
    ]


def test_reset_all_membership_rule_self_denial_and_actor_revalidation(intake_site):
    owner, other, engine, workspace_id, admin_id = intake_site
    make_admin(engine, workspace_id, admin_id)
    headers = _login(owner, "intake-owner@example.invalid")
    enroll(other, email="intake-other@example.invalid")
    member_id, additional = target_id(engine), uuid4()
    route = f"/api/v1/workspaces/{workspace_id}/members/{member_id}/second-factor/reset"
    with Session(engine) as session, session.begin():
        session.add(Workspace(id=additional, name="Synthetic second workspace"))
        session.flush()
        session.add(Membership(workspace_id=additional, user_id=member_id, role="member"))
    try:
        assert owner.post(route, headers=headers).json()["code"] == "reset_requires_operator"
        assert (
            owner.post(
                f"/api/v1/workspaces/{workspace_id}/members/{admin_id}/second-factor/reset",
                headers=headers,
            ).status_code
            == 403
        )
        assert other.post(route, headers=_login_for_existing(other)).status_code == 404
        with Session(engine) as session, session.begin():
            session.add(Membership(workspace_id=additional, user_id=admin_id, role="administrator"))
        assert owner.post(route, headers=headers).status_code == 204
        with Session(engine) as session, session.begin():
            row = session.scalar(
                select(StoredSession).where(
                    StoredSession.user_id == admin_id, StoredSession.revoked_at.is_(None)
                )
            )
            row.revoked_at, revoked_id = datetime.now(UTC), row.id
        with pytest.raises(FactorError) as denied:
            reset_factor(
                engine,
                member_id,
                datetime.now(UTC),
                actor_id=admin_id,
                workspace_id=workspace_id,
                actor_session_id=revoked_id,
            )
        assert denied.value.status == 401
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(Membership).where(Membership.workspace_id == additional))
            session.execute(delete(Workspace).where(Workspace.id == additional))


def _login_for_existing(client):
    return {
        "Origin": ORIGIN,
        "X-CSRF-Token": client.get("/api/v1/auth/session").json()["csrf_token"],
    }


def test_workspace_policy_keeps_current_session_and_requires_next_enrollment(intake_site):
    owner, other, engine, workspace_id, admin_id = intake_site
    make_admin(engine, workspace_id, admin_id)
    headers = _login(owner, "intake-owner@example.invalid")
    assert policy(owner, headers, workspace_id, True).json()["code"] == "enable_second_factor_first"
    headers, _, backups = enroll(owner)
    _login(other, "intake-other@example.invalid")
    enabled = policy(owner, headers, workspace_id, True)
    assert enabled.status_code == 200 and enabled.json()["members_without_second_factor"] == 1
    existing = other.get("/api/v1/auth/session")
    assert existing.status_code == 200 and existing.json()["second_factor_setup_required"]
    assert (
        owner.post(
            "/api/v1/auth/second-factor/disable",
            headers=headers,
            json={"password": PASSWORD, "code": backups[0]},
        ).json()["code"]
        == "second_factor_required_by_workspace"
    )
    assert (
        password_step(other, "intake-other@example.invalid").json()["status"]
        == "enrollment_required"
    )
    assert other.get("/api/v1/auth/session").status_code == 401


def test_concurrent_policy_enable_and_factor_disable_keep_the_requirement_atomic(intake_site):
    owner, _, engine, workspace_id, admin_id = intake_site
    make_admin(engine, workspace_id, admin_id)
    _, _, backups = enroll(owner)
    settings = owner.app.state.settings
    second = create_engine(
        settings.database_url,
        hide_parameters=True,
        connect_args={"options": "-c statement_timeout=5000"},
    )
    with Session(engine) as session:
        current = session.scalar(
            select(StoredSession.id).where(
                StoredSession.user_id == admin_id, StoredSession.revoked_at.is_(None)
            )
        )

    def enable():
        try:
            with Session(second) as session:
                update_workspace_settings(
                    session,
                    workspace_id=workspace_id,
                    actor_id=admin_id,
                    expected_version=1,
                    content_retention_days=7,
                    activity_retention_days=90,
                    require_second_factor=True,
                )
            return "enabled"
        except FactorError:
            return "denied"

    def disable():
        try:
            change_factor(
                engine,
                settings,
                admin_id,
                current,
                PASSWORD,
                backups[0],
                datetime.now(UTC),
                disable=True,
            )
            return "disabled"
        except FactorError:
            return "denied"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = [
                future.result(timeout=10)
                for future in (executor.submit(enable), executor.submit(disable))
            ]
        assert outcomes.count("denied") == 1
        with Session(engine) as session:
            assert (
                not session.get(Workspace, workspace_id).require_second_factor
                or session.get(UserSecondFactor, admin_id) is not None
            )
    finally:
        second.dispose()


@pytest.mark.parametrize(
    "failure",
    [RecoveryDeliveryError("synthetic delivery failure"), ValueError("synthetic delivery failure")],
)
def test_notice_failure_never_rolls_back_a_committed_security_change(intake_site, caplog, failure):
    owner, _, engine, _, user_id = intake_site

    class BrokenMailer:
        def send_security_notice(self, recipient, event, body):
            raise failure

    owner.app.state.recovery_mailer = BrokenMailer()
    _, key, _ = enroll(owner)
    with Session(engine) as session:
        assert session.get(UserSecondFactor, user_id).status == "active"
    assert "second_factor_enabled" in caplog.text
    assert "synthetic delivery failure" not in caplog.text and key not in caplog.text


def test_operator_cli_requires_typed_confirmation_and_forces_new_enrollment(intake_site):
    owner, _, engine, _, user_id = intake_site
    enroll(owner)
    settings = owner.app.state.settings
    env = {
        **os.environ,
        "PRIVACY_REVIEW_DATABASE_URL": settings.database_url,
        "PRIVACY_REVIEW_ENVIRONMENT": "test",
        "PRIVACY_REVIEW_ALLOWED_ORIGINS": json.dumps([ORIGIN]),
        "PRIVACY_REVIEW_ACTIVE_KEY_ID": settings.active_key_id,
        "PRIVACY_REVIEW_CONTENT_KEYS": json.dumps(
            {key: value.get_secret_value() for key, value in settings.content_keys.items()}
        ),
        "PRIVACY_REVIEW_SMTP_HOST": "",
        "PGCONNECT_TIMEOUT": "3",
    }
    command = [sys.executable, "-m", "app.accounts.reset_second_factor", "--user-id", str(user_id)]
    canceled = subprocess.run(
        command, input="cancel\n", capture_output=True, text=True, env=env, timeout=15, check=False
    )
    assert canceled.returncode != 0
    with Session(engine) as session:
        assert session.get(UserSecondFactor, user_id).status == "active"
    completed = subprocess.run(
        command,
        input=str(user_id) + "\n",
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
        check=False,
    )
    assert completed.returncode == 0 and "New enrollment is required" in completed.stdout
    assert owner.get("/api/v1/auth/session").status_code == 401
    assert password_step(owner).json()["status"] == "enrollment_required"


def test_membership_revocation_consumes_a_password_authenticated_challenge(intake_site):
    owner, member, engine, workspace_id, actor_id = intake_site
    make_admin(engine, workspace_id, actor_id)
    headers = _login(owner, "intake-owner@example.invalid")
    _, _, backups = enroll(member, email="intake-other@example.invalid")
    password_step(member, "intake-other@example.invalid")
    assert (
        owner.post(
            f"/api/v1/workspaces/{workspace_id}/members/{target_id(engine)}/revoke", headers=headers
        ).status_code
        == 200
    )
    denied = member.post(
        "/api/v1/auth/sign-in/second-factor", headers={"Origin": ORIGIN}, json={"code": backups[0]}
    )
    assert denied.status_code == 401 and "Max-Age=0" in denied.headers["set-cookie"]
    assert member.get("/api/v1/auth/session").status_code == 401
