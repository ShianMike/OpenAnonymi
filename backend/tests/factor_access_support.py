"""Actual authenticator changes with generated secrets kept in fixture memory."""

import time
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, User
from app.db.second_factor import UserBackupCode, UserSecondFactor
from tests.intake_support import PASSWORD, _login
from tests.second_factor_support import enroll, totp

OPERATIONS = ("start", "confirm", "disable")


def factor_case(site, operation):
    client, _, engine, workspace, actor = site
    headers = _login(client, "intake-owner@example.invalid")
    case = {
        "client": client,
        "engine": engine,
        "workspace": workspace,
        "actor": actor,
        "headers": headers,
        "operation": operation,
        "body": None,
    }
    base = "/api/v1/auth/second-factor"
    if operation == "start":
        case["path"] = base + "/enrollment/start"
    elif operation == "confirm":
        started = client.post(base + "/enrollment/start", headers=headers)
        assert started.status_code == 200
        case.update(
            path=base + "/enrollment/confirm", body={"code": totp(started.json()["manual_key"])}
        )
    else:
        headers, key, backups = enroll(client)
        case.update(
            headers=headers,
            path=base + "/disable",
            body={"password": PASSWORD, "code": backups[0]},
            key=key,
        )
        if operation == "regenerate":
            # Confirm consumed the current TOTP step. Wait for the real next
            # step; do not forge the server clock or substitute its verifier.
            step = int(datetime.now(UTC).timestamp()) // 30
            while int(datetime.now(UTC).timestamp()) // 30 == step:
                time.sleep(0.1)
            case.update(path=base + "/backup-codes", body={"password": PASSWORD, "code": totp(key)})
    return case


def perform(case):
    return case["client"].post(case["path"], headers=case["headers"], json=case["body"])


def fingerprint(case):
    with Session(case["engine"]) as session:
        user = session.get(User, case["actor"])
        return user.second_factor_reenroll_required, tuple(
            tuple(
                sorted(
                    [
                        tuple(getattr(row, col.name) for col in model.__table__.columns)
                        for row in session.scalars(select(model).where(condition))
                    ],
                    key=repr,
                )
            )
            for model, condition in (
                (UserSecondFactor, UserSecondFactor.user_id == case["actor"]),
                (UserBackupCode, UserBackupCode.user_id == case["actor"]),
                (AuditEvent, AuditEvent.workspace_id == case["workspace"]),
            )
        )


def after_factor_work(monkeypatch, case, change):
    from app.accounts import second_factor as service

    hook = (
        "start_locked_enrollment"
        if case["operation"] == "start"
        else ("activate_locked" if case["operation"] == "confirm" else "security_activity")
    )
    original, fired = getattr(service, hook), []

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        if not fired:
            fired.append(True)
            change()
        return result

    monkeypatch.setattr(service, hook, changed)
    return fired
