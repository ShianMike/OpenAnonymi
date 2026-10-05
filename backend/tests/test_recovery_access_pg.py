"""Actual recovery proof expiry, atomic rollback and concurrent account resets."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, get_ident
from time import sleep

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, event, select
from sqlalchemy.orm import Session

from app.accounts import recovery
from app.db.models import Membership, RecoveryToken, User
from app.db.models import Session as StoredSession
from app.db.second_factor import AuthChallenge, UserBackupCode, UserSecondFactor
from tests.intake_support import ORIGIN, PASSWORD, _login
from tests.mail_support import Mailbox
from tests.second_factor_support import enroll, password_step

EMAIL = "intake-owner@example.invalid"
NEW_PASSWORD = "new-synthetic-recovery-password"


def recovery_case(site, count=1):
    client, _, engine, workspace, actor = site
    _login(client, EMAIL)
    client.app.state.recovery_mailer = mailer = Mailbox()
    codes = []
    for _ in range(count):
        response = client.post("/api/v1/auth/recovery/request", headers={"Origin": ORIGIN}, json={"email": EMAIL})
        assert response.status_code == 202
        codes.append(mailer.latest(EMAIL))
    return {"client": client, "engine": engine, "actor": actor, "workspace": workspace, "mailer": mailer, "codes": codes}


def complete(case, *, client=None, code=None):
    return (client or case["client"]).post("/api/v1/auth/recovery/complete", headers={"Origin": ORIGIN}, json={
        "email": EMAIL, "code": code or case["codes"][0], "new_password": NEW_PASSWORD})


def account_state(case):
    with Session(case["engine"]) as session:
        user = session.get(User, case["actor"])
        return (user.password_hash, user.email_verified_at, *[
            tuple(sorted((tuple(getattr(row, column.name) for column in model.__table__.columns)
                          for row in session.scalars(select(model).where(condition))), key=repr))
            for model, condition in (
                (RecoveryToken, RecoveryToken.user_id == user.id),
                (StoredSession, StoredSession.user_id == user.id),
                (AuthChallenge, AuthChallenge.user_id == user.id),
                (UserSecondFactor, UserSecondFactor.user_id == user.id),
                (UserBackupCode, UserBackupCode.user_id == user.id))])


def expire_during_completion(case, phase, monkeypatch):
    with Session(case["engine"]) as session, session.begin():
        token = session.scalar(select(RecoveryToken).where(RecoveryToken.token_hash == recovery._digest(case["codes"][0])))
        token.expires_at = datetime.now(UTC) + timedelta(seconds=1)
    fired = []
    if phase == "hash":
        original = recovery.hash_password

        def hashed(*args, **kwargs):
            result = original(*args, **kwargs)
            fired.append(True)
            sleep(2)
            return result

        monkeypatch.setattr(recovery, "hash_password", hashed)
        return fired, lambda: None

    def after(connection, cursor, statement, parameters, context, executemany):
        clause = getattr(getattr(context, "compiled", None), "statement", None)
        if not fired and getattr(clause, "is_update", False) and getattr(getattr(clause, "table", None), "name", None) == "users":
            fired.append(True)
            sleep(2)

    event.listen(case["engine"], "after_cursor_execute", after)
    return fired, lambda: event.remove(case["engine"], "after_cursor_execute", after)


def concurrent_completions(case):
    barrier, seen, failures = Barrier(2, timeout=15), set(), []

    def before(connection, cursor, statement, parameters, context, executemany):
        current = get_ident()
        if current not in seen and "from users" in statement.lower() and "for update" in statement.lower():
            seen.add(current)
            barrier.wait()

    def failed(context):
        failures.append(getattr(context.original_exception, "sqlstate", None))

    peers = [TestClient(case["client"].app, raise_server_exceptions=False) for _ in range(2)]
    event.listen(case["engine"], "before_cursor_execute", before)
    event.listen(case["engine"], "handle_error", failed)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(complete, case, client=peer, code=code) for peer, code in zip(peers, case["codes"], strict=True)]
            responses = [future.result(timeout=40) for future in futures]
    finally:
        event.remove(case["engine"], "before_cursor_execute", before)
        event.remove(case["engine"], "handle_error", failed)
        for peer in peers:
            peer.close()
    assert len(seen) == 2
    return responses, failures


@pytest.mark.parametrize("phase", ("hash", "prepared-write"))
def test_real_recovery_expiry_during_work_rolls_back_every_security_change(intake_site, monkeypatch, phase):
    case = recovery_case(intake_site)
    if phase == "prepared-write":
        enroll(case["client"])
        password_step(intake_site[1])
        with Session(case["engine"]) as session, session.begin():
            session.get(UserSecondFactor, case["actor"]).failed_attempts = 3
        case["mailer"].notices.clear()
    fired, remove = expire_during_completion(case, phase, monkeypatch)
    before = account_state(case)
    try:
        response = complete(case)
    finally:
        remove()
    assert fired and response.status_code == 400 and response.json()["code"] == "invalid_recovery_code"
    assert response.headers["cache-control"] == "no-store" and "set-cookie" not in response.headers
    assert account_state(case) == before and not case["mailer"].notices
    assert case["client"].get("/api/v1/auth/session").status_code == 200


def test_two_real_codes_serialize_on_account_lock_without_deadlock(intake_site):
    case = recovery_case(intake_site, count=2)
    responses, failures = concurrent_completions(case)
    assert sorted(response.status_code for response in responses) == [204, 400] and not failures
    assert len(case["mailer"].notices) == 1 and case["mailer"].notices[0][1] == "password_changed"
    assert case["client"].get("/api/v1/auth/session").status_code == 401
    assert all(complete(case, code=code).status_code == 400 for code in case["codes"])


def test_mailbox_proof_can_recover_an_account_without_an_active_workspace(intake_site):
    case = recovery_case(intake_site)
    with Session(case["engine"]) as session, session.begin():
        session.execute(delete(Membership).where(Membership.user_id == case["actor"]))
    assert complete(case).status_code == 204
    with Session(case["engine"]) as session:
        assert session.get(User, case["actor"]).email_verified_at is not None
    assert len(case["mailer"].notices) == 1


def test_successful_recovery_keeps_real_factor_and_backup_codes(intake_site):
    case = recovery_case(intake_site)
    _, _, backups = enroll(case["client"])
    password_step(case["client"])
    with Session(case["engine"]) as session, session.begin():
        factor = session.get(UserSecondFactor, case["actor"])
        ciphertext = factor.secret_ciphertext
        factor.failed_attempts = 3
    case["mailer"].notices.clear()
    assert complete(case).status_code == 204
    with Session(case["engine"]) as session:
        factor = session.get(UserSecondFactor, case["actor"])
        assert factor.status == "active" and factor.secret_ciphertext == ciphertext and factor.failed_attempts == 0
        assert all(row.consumed_at is not None for row in session.scalars(select(AuthChallenge).where(AuthChallenge.user_id == case["actor"])))
        assert all(row.used_at is None for row in session.scalars(select(UserBackupCode).where(UserBackupCode.user_id == case["actor"])))
    assert len(case["mailer"].notices) == 1
    assert case["client"].post("/api/v1/auth/sign-in", headers={"Origin": ORIGIN}, json={"email": EMAIL, "password": PASSWORD}).status_code == 401
    response = case["client"].post("/api/v1/auth/sign-in", headers={"Origin": ORIGIN}, json={"email": EMAIL, "password": NEW_PASSWORD})
    assert response.status_code == 202
    assert case["client"].post("/api/v1/auth/sign-in/second-factor", headers={"Origin": ORIGIN}, json={"code": backups[0]}).status_code == 200
