"""Configured recovery delivery uses a validated TLS connection."""

import smtplib
import ssl

import pytest
from pydantic import ValidationError

from app.accounts.recovery import RecoveryDeliveryError, SmtpRecoveryMailer
from app.config import Settings


def _settings(**overrides):
    return Settings(
        database_url="postgresql+psycopg://test:test@localhost/review",
        allowed_origins=["http://localhost:5173"],
        environment="test",
        _env_file=None,
        **overrides,
    )


def test_partial_recovery_configuration_is_rejected():
    with pytest.raises(ValidationError):
        _settings(smtp_host="smtp.example.invalid")


@pytest.mark.parametrize("port", [465, 587])
def test_configured_smtp_sends_one_time_code_with_certificate_validation(monkeypatch, port):
    observed = {"events": []}

    class FakeSmtp:
        def __init__(self, host, port, *, timeout, context=None):
            observed.update(host=host, port=port, timeout=timeout, context=context)
            if port == 587:
                assert context is None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def starttls(self, *, context):
            observed["context"] = context
            observed["events"].append("tls")

        def login(self, username, password):
            assert observed["context"].verify_mode == ssl.CERT_REQUIRED
            assert observed["context"].check_hostname
            observed["events"].append("login")
            observed["login"] = (username, password)

        def send_message(self, message):
            observed["events"].append("send")
            observed["message"] = message

    monkeypatch.setattr("app.accounts.recovery.smtplib.SMTP_SSL", FakeSmtp)
    monkeypatch.setattr("app.accounts.recovery.smtplib.SMTP", FakeSmtp)
    settings = _settings(
        smtp_host="smtp.example.invalid",
        smtp_port=port,
        smtp_username="test-account",
        smtp_password="synthetic-mail-secret",
        smtp_from="review@example.invalid",
    )
    SmtpRecoveryMailer(settings).send_recovery_code(
        "member@example.invalid", "synthetic-recovery-code"
    )
    assert observed["host"] == "smtp.example.invalid"
    assert observed["port"] == port
    assert observed["timeout"] == 10
    assert isinstance(observed["context"], ssl.SSLContext)
    assert observed["context"].verify_mode == ssl.CERT_REQUIRED
    assert observed["message"]["To"] == "member@example.invalid"
    assert observed["message"]["Date"].datetime.utcoffset().total_seconds() == 0
    assert observed["message"]["Message-ID"].endswith("@example.invalid>")
    assert not observed["message"]["Message-ID"].defects
    assert "synthetic-recovery-code" in observed["message"].get_content()
    assert observed["events"] == (["tls"] if port == 587 else []) + ["login", "send"]


@pytest.mark.parametrize("error", [ssl.SSLCertVerificationError, smtplib.SMTPNotSupportedError])
def test_starttls_failure_never_sends_credentials_or_code(monkeypatch, error):
    class RefusedTls:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def starttls(self, *, context):
            assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
            raise error("synthetic TLS refusal")

        def login(self, *_args):
            pytest.fail("Credentials must not be sent before validated TLS")

        def send_message(self, *_args):
            pytest.fail("Codes must not be sent before validated TLS")

    monkeypatch.setattr("app.accounts.recovery.smtplib.SMTP", RefusedTls)
    mailer = SmtpRecoveryMailer(_settings(
        smtp_host="smtp.example.invalid", smtp_port=587, smtp_username="test-account",
        smtp_password="synthetic-mail-secret", smtp_from="review@example.invalid",
    ))
    with pytest.raises(RecoveryDeliveryError, match="Account recovery delivery failed"):
        mailer.send_recovery_code("member@example.invalid", "synthetic-recovery-code")
