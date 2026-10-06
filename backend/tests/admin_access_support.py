"""Real administration/password/device cases, used only with the owned local fixture."""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.security import _digest
from app.db.models import AuditEvent, Membership, RecoveryToken, User, Workspace
from app.db.models import Session as StoredSession
from app.db.second_factor import AuthChallenge, UserBackupCode, UserSecondFactor
from tests.intake_support import PASSWORD, _login
from tests.mail_support import Mailbox
from tests.second_factor_support import enroll
from tests.test_custom_rules_pg import admin_headers

OPERATIONS = ("members-read", "settings-read", "settings-write", "role-change", "role-unchanged",
    "member-revoke", "member-revoke-unchanged", "member-restore", "member-restore-unchanged",
    "invite", "factor-reset", "devices-read", "device-revoke", "devices-others", "password-change",
    "session-read", "factor-state")

def admin_case(site, operation):
    client, other, engine, workspace, actor = site
    headers = admin_headers(site)
    with Session(engine) as session:
        target = session.scalar(select(User.id).where(User.email == "intake-other@example.invalid"))
        current = session.scalar(select(StoredSession.id).where(
            StoredSession.token_hash == _digest(client.cookies.get("openanonymi_session"))))
    case = {"client": client, "other": other, "engine": engine, "workspace": workspace,
        "actor": actor, "target": target, "current_session": current, "headers": headers,
        "operation": operation, "method": "POST"}
    base = f"/api/v1/workspaces/{workspace}"
    members = base + "/members"
    if operation == "members-read":
        case.update(method="GET", path=members)
    elif operation == "settings-read":
        case.update(method="GET", path=base + "/settings")
    elif operation == "settings-write":
        record = client.get(base + "/settings").json()
        case.update(method="PUT", path=base + "/settings", body={
            "expected_version": record["settings_version"], "content_retention_days": 3,
            "activity_retention_days": 90, "approval_policy": "always"})
    elif operation.startswith("role"):
        case.update(method="PATCH", path=members + f"/{target}/role",
            body={"role": "administrator" if operation == "role-change" else "member"})
    elif operation.startswith("member"):
        revoke = operation.startswith("member-revoke")
        if operation in ("member-revoke-unchanged", "member-restore"):
            assert client.post(members + f"/{target}/revoke", headers=headers).status_code == 200
        case.update(path=members + f"/{target}/" + ("revoke" if revoke else "restore"))
    elif operation == "invite":
        case.update(path=members + "/invitations", body={"email": f"audit-{uuid4().hex}@openanonymi.test"})
        # The fixture prohibits external SMTP; the real service still prepares and
        # persists its genuine token, captured only at the mail transport boundary.
        client.app.state.settings = client.app.state.settings.model_copy(update={"email_allow_test_domains": True})
    elif operation == "factor-reset":
        enroll(other, email="intake-other@example.invalid")
        case.update(path=members + f"/{target}/second-factor/reset")
    elif operation in ("devices-read", "device-revoke", "devices-others"):
        _login(other, "intake-owner@example.invalid")
        rows = client.get("/api/v1/auth/sessions").json()
        row = next(item for item in rows if not item["current"])
        case["target_session"] = row["id"]
        case.update(path="/api/v1/auth/sessions" if operation == "devices-read" else
            "/api/v1/auth/sessions/revoke-others" if operation == "devices-others" else
            f"/api/v1/auth/sessions/{row['id']}/revoke",
            method="GET" if operation == "devices-read" else "POST")
    elif operation == "password-change":
        case.update(path="/api/v1/auth/change-password", body={"current_password": PASSWORD,
            "new_password": "synthetic-replacement-password"})
    elif operation == "session-read":
        case.update(method="GET", path="/api/v1/auth/session")
    else:
        case.update(method="GET", path="/api/v1/auth/second-factor")
    client.app.state.recovery_mailer = case["mailer"] = Mailbox()
    return case

def perform(case):
    return case["client"].request(case["method"], case["path"], headers=case["headers"],
        json=case.get("body"))

def revoke_current(case, change="revoked"):
    with Session(case["engine"]) as session, session.begin():
        row = session.get(StoredSession, case["current_session"])
        now = datetime.now(UTC)
        if change == "revoked":
            row.revoked_at = now
        else:
            row.created_at, row.expires_at = now - timedelta(days=1), now - timedelta(seconds=1)

def fingerprint(case):
    with Session(case["engine"]) as session:
        ids = session.scalars(select(Membership.user_id).where(Membership.workspace_id == case["workspace"])).all()
        queries = ((Workspace, Workspace.id == case["workspace"]),
            (Membership, (Membership.workspace_id == case["workspace"]) & (Membership.user_id != case["actor"])),
            (User, User.id.in_(ids)), (RecoveryToken, RecoveryToken.user_id.in_(ids)),
            (StoredSession, StoredSession.user_id.in_(ids) & (StoredSession.id != case["current_session"])),
            (UserSecondFactor, UserSecondFactor.user_id.in_(ids)),
            (UserBackupCode, UserBackupCode.user_id.in_(ids)),
            (AuthChallenge, AuthChallenge.user_id.in_(ids)),
            (AuditEvent, AuditEvent.workspace_id == case["workspace"]))
        return tuple(tuple(sorted([tuple(getattr(row, c.name) for c in model.__table__.columns)
            for row in session.scalars(select(model).where(condition))], key=repr)) for model, condition in queries)

def after_work(monkeypatch, case, change):
    from app.accounts import (
        admin_api,
        api,
        devices,
        memberships,
        reset_second_factor,
        second_factor_api,
        security,
    )
    operation = case["operation"]
    if operation == "members-read":
        module, hook = admin_api, "_member_view"
    elif operation == "settings-read":
        module, hook = admin_api, "_settings_view"
    elif operation == "settings-write":
        module, hook = memberships, "_workspace_record"
    elif operation in ("invite", "role-change", "role-unchanged") or operation.startswith("member"):
        module, hook = memberships, "_member_record"
    elif operation == "factor-reset":
        module, hook = reset_second_factor, "record_event"
    elif operation == "devices-read":
        module, hook = second_factor_api, "list_devices"
    elif operation in ("device-revoke", "devices-others"):
        module, hook = devices, "security_activity"
    elif operation == "password-change":
        module, hook = security, "hash_password"
    elif operation == "session-read":
        module, hook = api, "_view"
    else:
        module, hook = second_factor_api, "security_status"
    original, fired = getattr(module, hook), []
    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        if not fired:
            fired.append(True)
            change()
        return result
    monkeypatch.setattr(module, hook, changed)
    return fired

def cleanup_invitation(case):
    if case["operation"] != "invite":
        return
    with Session(case["engine"]) as session, session.begin():
        user = session.scalar(select(User).where(User.email == case["body"]["email"]))
        if user is not None:
            membership = session.get(Membership, (case["workspace"], user.id))
            if membership is not None:
                session.delete(membership)
                session.flush()
            session.delete(user)
