"""Real email-proof writes and queued delivery recheck current authorization."""
from datetime import UTC, datetime, timedelta
from time import sleep

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.accounts import api, signup
from app.accounts.recovery import RecoveryDeliveryError
from app.accounts.security import _digest
from app.db.email_verification import EmailVerification
from app.db.models import Membership, User
from app.db.models import Session as StoredSession
from tests.intake_support import _login
from tests.mail_support import Mailbox


def email_case(site, operation="request"):
    client, _, engine, workspace, actor = site
    client.app.state.recovery_mailer = mailer = Mailbox()
    headers = _login(client, "intake-owner@example.invalid")
    with Session(engine) as session:
        session_id = session.scalar(select(StoredSession.id).where(
            StoredSession.token_hash == _digest(client.cookies.get("openanonymi_session"))))
    body = None
    if operation in ("confirm", "wrong", "replace"):
        assert client.post("/api/v1/auth/email-verification", headers=headers).status_code == 202
        code = mailer.latest("intake-owner@example.invalid")
        if operation != "replace":
            body = {"code": code if operation == "confirm" else "x" * 32}
        mailer.messages.clear()
    if operation == "verified":
        with Session(engine) as session, session.begin():
            session.get(User, actor).email_verified_at = datetime.now(UTC)
    return {"client":client, "engine":engine, "workspace":workspace, "actor":actor,
        "session_id":session_id, "headers":headers, "body":body, "mailer":mailer,
        "path":"/api/v1/auth/email-verification" + ("/confirm" if body else "")}


def perform(case):
    return case["client"].post(case["path"], headers=case["headers"], json=case["body"])


def proof_state(case):
    with Session(case["engine"]) as session:
        row = session.get(EmailVerification, case["actor"])
        return (session.get(User, case["actor"]).email_verified_at,
            None if row is None else tuple(getattr(row, col.name) for col in row.__table__.columns))


def lose_access(case, change="revoked"):
    now = datetime.now(UTC)
    with Session(case["engine"]) as session, session.begin():
        if change == "membership":
            session.get(Membership, (case["workspace"], case["actor"])).revoked_at = now
        elif change == "disabled":
            session.get(User, case["actor"]).disabled_at = now
        else:
            row = session.get(StoredSession, case["session_id"])
            if change == "revoked":
                row.revoked_at = now
            else:
                row.created_at, row.expires_at = now - timedelta(days=1), now - timedelta(seconds=1)


def denied(response):
    assert response.status_code == 401 and response.headers["cache-control"] == "no-store"
    assert response.json()["code"] == "sign_in_required" and not response.json().get("details")
    assert "intake-owner@example.invalid" not in response.text and "set-cookie" not in response.headers


@pytest.mark.parametrize("operation", ("request", "replace", "confirm", "wrong"))
@pytest.mark.parametrize("change", ("revoked", "expired", "membership"))
def test_prepared_email_proof_changes_roll_back_when_access_ends(intake_site, operation, change):
    case = email_case(intake_site, operation)
    before, fired = proof_state(case), []
    def after(connection, cursor, statement, parameters, context, executemany):
        clause = getattr(getattr(context, "compiled", None), "statement", None)
        if not fired and getattr(getattr(clause, "table", None), "name", None) == "email_verifications" and (
            getattr(clause, "is_insert", False) or getattr(clause, "is_update", False) or getattr(clause, "is_delete", False)
        ):
            fired.append(True)
            lose_access(case, change)
    event.listen(case["engine"], "after_cursor_execute", after)
    try:
        denied(perform(case))
    finally:
        event.remove(case["engine"], "after_cursor_execute", after)
    assert fired and proof_state(case) == before and not case["mailer"].messages


@pytest.mark.parametrize("operation", ("request", "confirm", "wrong"))
def test_account_disabled_after_dependency_cannot_change_email_proof(intake_site, operation):
    case = email_case(intake_site, operation)
    before, fired = proof_state(case), []
    def before_lock(connection, cursor, statement, parameters, context, executemany):
        if not fired and "users" in statement and "FOR UPDATE" in statement:
            fired.append(True)
            lose_access(case, "disabled")
    event.listen(case["engine"], "before_cursor_execute", before_lock)
    try:
        denied(perform(case))
    finally:
        event.remove(case["engine"], "before_cursor_execute", before_lock)
    assert fired and proof_state(case) == before and not case["mailer"].messages


def test_already_verified_no_op_checks_session_after_actual_user_lock(intake_site):
    case = email_case(intake_site, "verified")
    before, fired = proof_state(case), []
    def after_lock(connection, cursor, statement, parameters, context, executemany):
        if not fired and "users" in statement and "FOR UPDATE" in statement:
            fired.append(True)
            lose_access(case)
    event.listen(case["engine"], "after_cursor_execute", after_lock)
    try:
        denied(perform(case))
    finally:
        event.remove(case["engine"], "after_cursor_execute", after_lock)
    assert fired and proof_state(case) == before and not case["mailer"].messages


@pytest.mark.parametrize("change", ("revoked", "expired", "membership", "disabled"))
def test_serialized_email_request_denies_reply_and_does_not_send(intake_site, monkeypatch, change):
    case = email_case(intake_site)
    original, fired = api.RegistrationMessage.model_dump_json, []
    def serialized(*args, **kwargs):
        payload = original(*args, **kwargs)
        if not fired:
            fired.append(True)
            lose_access(case, change)
        return payload
    monkeypatch.setattr(api.RegistrationMessage, "model_dump_json", serialized)
    denied(perform(case))
    assert fired and proof_state(case)[1] is not None and not case["mailer"].messages


def before_delivery(monkeypatch, change):
    original, fired = BackgroundTask.__call__, []
    async def queued(self):
        if not fired and self.func.__name__ == "dispatch" and self.args[2] == "send_email_verification_code":
            fired.append(True)
            change()
        return await original(self)
    monkeypatch.setattr(BackgroundTask, "__call__", queued)
    return fired


@pytest.mark.parametrize("change", ("revoked", "expired", "membership", "disabled"))
def test_session_ending_before_actual_delivery_skips_queued_code(intake_site, monkeypatch, change):
    case = email_case(intake_site)
    fired = before_delivery(monkeypatch, lambda: lose_access(case, change))
    assert perform(case).status_code == 202
    assert fired and proof_state(case)[1] is not None and not case["mailer"].messages


@pytest.mark.parametrize("change", ("expired", "exhausted", "superseded", "deleted", "verified", "recipient"))
def test_delivery_requires_exact_current_unverified_mailbox_proof(intake_site, monkeypatch, change):
    case = email_case(intake_site)
    def change_proof():
        with Session(case["engine"]) as session, session.begin():
            row = session.get(EmailVerification, case["actor"])
            user = session.get(User, case["actor"])
            if change == "expired":
                now = datetime.now(UTC)
                row.created_at, row.expires_at = now - timedelta(minutes=20), now - timedelta(minutes=5)
            elif change == "exhausted":
                row.failed_attempts = 5
            elif change == "superseded":
                row.code_digest = signup.digest("different-current-proof")
            elif change == "deleted":
                session.delete(row)
            elif change == "verified":
                user.email_verified_at = datetime.now(UTC)
            else:
                user.email = "changed@example.invalid"
    fired = before_delivery(monkeypatch, change_proof)
    assert perform(case).status_code == 202
    assert fired and not case["mailer"].messages


def test_session_ending_during_mailbox_proof_query_is_checked_again(intake_site, monkeypatch):
    case = email_case(intake_site)
    original, fired = api.validate_email_delivery, []
    def validate(*args, **kwargs):
        result = original(*args, **kwargs)
        fired.append(True)
        lose_access(case)
        return result
    monkeypatch.setattr(api, "validate_email_delivery", validate)
    assert perform(case).status_code == 202
    assert fired and not case["mailer"].messages


@pytest.mark.parametrize("phase", ("locked", "compared"))
def test_real_proof_expiry_during_work_rolls_back_verification(intake_site, monkeypatch, phase):
    case = email_case(intake_site, "confirm")
    with Session(case["engine"]) as session, session.begin():
        row = session.get(EmailVerification, case["actor"])
        now = datetime.now(UTC)
        row.created_at, row.expires_at = now - timedelta(seconds=1), now + timedelta(seconds=1)
    before, fired = proof_state(case), []
    original = signup.hmac.compare_digest
    def compared(*args, **kwargs):
        result = original(*args, **kwargs)
        if not fired and isinstance(args[0], bytes):
            fired.append(True)
            sleep(2)
        return result
    def after_lock(connection, cursor, statement, parameters, context, executemany):
        if not fired and "users" in statement and "FOR UPDATE" in statement:
            fired.append(True)
            sleep(2)
    if phase == "compared":
        monkeypatch.setattr(signup.hmac, "compare_digest", compared)
    else:
        event.listen(case["engine"], "after_cursor_execute", after_lock)
    try:
        response = perform(case)
    finally:
        if phase == "locked":
            event.remove(case["engine"], "after_cursor_execute", after_lock)
    assert response.status_code == 400 and response.json()["code"] == "invalid_verification_code"
    assert fired and proof_state(case) == before and not case["mailer"].messages


def test_delivery_failure_keeps_neutral_reply_and_genuine_retryable_proof(intake_site):
    case = email_case(intake_site)
    class FailedMailer(Mailbox):
        def send_email_verification_code(self, recipient, code):
            raise RecoveryDeliveryError("Synthetic transport failure")
    case["client"].app.state.recovery_mailer = FailedMailer()
    assert perform(case).status_code == 202
    assert proof_state(case)[1] is not None
    case["client"].app.state.recovery_mailer = case["mailer"]
    assert perform(case).status_code == 202
    assert len(case["mailer"].messages) == 1
    code = case["mailer"].latest("intake-owner@example.invalid")
    assert case["client"].post("/api/v1/auth/email-verification/confirm", headers=case["headers"], json={"code":code}).status_code == 204
