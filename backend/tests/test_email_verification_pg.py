"""Signed-in code verification, attempt persistence, outbox bytes and cleanup."""

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.accounts.outbox import OutboxMailer
from app.cleanup.service import purge_unavailable_content
from app.db.email_verification import EmailVerification
from app.db.models import User
from tests.intake_support import _login
from tests.mail_support import Mailbox


def test_settings_email_proof_single_use_and_persisted_failure_limit(intake_site):
    owner, _, engine, _, actor = intake_site
    mailer = Mailbox()
    owner.app.state.recovery_mailer = mailer
    headers = _login(owner, "intake-owner@example.invalid")
    initial = owner.get("/api/v1/auth/session").json()
    assert not initial["email_verified"] and initial["email_verification_available"]
    assert (
        owner.post(
            "/api/v1/auth/email-verification", headers={"Origin": headers["Origin"]}
        ).status_code
        == 403
    )
    response = owner.post("/api/v1/auth/email-verification", headers=headers)
    assert response.status_code == 202
    code = mailer.latest("intake-owner@example.invalid")
    assert code not in response.text
    for _ in range(5):
        assert (
            owner.post(
                "/api/v1/auth/email-verification/confirm", headers=headers, json={"code": "x" * 32}
            ).status_code
            == 400
        )
    assert (
        owner.post(
            "/api/v1/auth/email-verification/confirm", headers=headers, json={"code": code}
        ).status_code
        == 400
    )
    with Session(engine) as session:
        row = session.get(EmailVerification, actor)
        assert row.failed_attempts == 5 and row.code_digest != code.encode()
    assert owner.post("/api/v1/auth/email-verification", headers=headers).status_code == 202
    replacement = mailer.latest("intake-owner@example.invalid")
    assert replacement != code
    assert (
        owner.post(
            "/api/v1/auth/email-verification/confirm", headers=headers, json={"code": replacement}
        ).status_code
        == 204
    )
    assert owner.get("/api/v1/auth/session").json()["email_verified"]
    assert (
        owner.post(
            "/api/v1/auth/email-verification/confirm", headers=headers, json={"code": replacement}
        ).status_code
        == 400
    )
    with Session(engine) as session:
        assert session.get(EmailVerification, actor) is None
        assert session.get(User, actor).email_verified_at is not None


def test_email_proof_expiry_and_cleanup(intake_site):
    owner, _, engine, _, actor = intake_site
    mailer = Mailbox()
    owner.app.state.recovery_mailer = mailer
    headers = _login(owner, "intake-owner@example.invalid")
    owner.post("/api/v1/auth/email-verification", headers=headers)
    code = mailer.latest("intake-owner@example.invalid")
    now = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        row = session.get(EmailVerification, actor)
        row.created_at, row.expires_at = now - timedelta(minutes=20), now - timedelta(minutes=5)
    assert (
        owner.post(
            "/api/v1/auth/email-verification/confirm", headers=headers, json={"code": code}
        ).status_code
        == 400
    )
    purge_unavailable_content(engine, now=now)
    with Session(engine) as session:
        assert session.get(EmailVerification, actor) is None
    owner.app.state.recovery_mailer = None
    assert not owner.get("/api/v1/auth/session").json()["email_verification_available"]
    assert owner.post("/api/v1/auth/email-verification", headers=headers).status_code == 503


def test_development_outbox_writes_real_messages_with_no_api_code_response(intake_site, tmp_path):
    owner, _, _, _, _ = intake_site
    directory = tmp_path / ".local-dev/outbox"
    owner.app.state.recovery_mailer = OutboxMailer(directory)
    headers = _login(owner, "intake-owner@example.invalid")
    response = owner.post("/api/v1/auth/email-verification", headers=headers)
    assert response.status_code == 202
    files = list(directory.glob("*.json"))
    assert len(files) == 1
    message = json.loads(files[0].read_text())
    assert message["to"] == "intake-owner@example.invalid" and "15 minutes" in message["body"]
    code = message["body"].splitlines()[0]
    assert code not in response.text
    assert (
        owner.post(
            "/api/v1/auth/email-verification/confirm", headers=headers, json={"code": code}
        ).status_code
        == 204
    )
