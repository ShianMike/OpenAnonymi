"""Configured recovery delivery uses a validated TLS connection."""

import ssl

import pytest
from pydantic import ValidationError

from app.accounts.recovery import SmtpRecoveryMailer
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


def test_configured_smtp_sends_one_time_code_with_certificate_validation(monkeypatch):
    observed = {}

    class FakeSmtp:
        def __init__(self, host, port, *, timeout, context):
            observed.update(host=host, port=port, timeout=timeout, context=context)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def login(self, username, password):
            observed["login"] = (username, password)

        def send_message(self, message):
            observed["message"] = message

    monkeypatch.setattr("app.accounts.recovery.smtplib.SMTP_SSL", FakeSmtp)
    settings = _settings(
        smtp_host="smtp.example.invalid",
        smtp_port=465,
        smtp_username="test-account",
        smtp_password="synthetic-mail-secret",
        smtp_from="review@example.invalid",
    )
    SmtpRecoveryMailer(settings).send_recovery_code(
        "member@example.invalid", "synthetic-recovery-code"
    )
    assert observed["host"] == "smtp.example.invalid"
    assert observed["port"] == 465
    assert observed["timeout"] == 10
    assert isinstance(observed["context"], ssl.SSLContext)
    assert observed["context"].verify_mode == ssl.CERT_REQUIRED
    assert observed["message"]["To"] == "member@example.invalid"
    assert "synthetic-recovery-code" in observed["message"].get_content()
