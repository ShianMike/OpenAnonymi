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
@pytest.mark.parametrize("sender", ["review@example.invalid", "Tenant Team <review@example.invalid>"])
def test_configured_smtp_sends_one_time_code_with_certificate_validation(monkeypatch, port, sender):
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
        smtp_from=sender,
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
    assert "synthetic-recovery-code" in observed["message"].get_body(preferencelist=("plain",)).get_content()
    assert "synthetic-recovery-code" in observed["message"].get_body(preferencelist=("html",)).get_content()
    assert observed["message"]["From"].addresses[0].display_name == (
        "Tenant Team" if sender.startswith("Tenant Team") else "OpenAnonymi"
    )
    assert observed["message"]["Reply-To"] is None
    html = observed["message"].get_body(preferencelist=("html",)).get_content()
    assert 'href="mailto:review@example.invalid"' in html
    assert "support@openanonymi.com" not in html and "https://openanonymi.com" not in html
    assert observed["events"] == (["tls"] if port == 587 else []) + ["login", "send"]


@pytest.mark.parametrize("method,expiry", [
    ("send_registration_code", "15 minutes"),
    ("send_email_verification_code", "15 minutes"),
    ("send_recovery_code", "30 minutes"),
    ("send_invitation_code", "24 hours"),
])
def test_every_code_email_has_same_copyable_code_and_expiry_in_both_formats(monkeypatch, method, expiry):
    from app.accounts.email_template import email_html

    observed = {}
    mailer = SmtpRecoveryMailer(_settings(
        smtp_host="smtp.example.invalid", smtp_port=587, smtp_username="test-account",
        smtp_password="synthetic-mail-secret", smtp_from="review@example.invalid",
    ))
    def capture(recipient, subject, body, *, code):
        observed.update(body=body, html=email_html(subject, body, sender="review@example.invalid", code=code))
    monkeypatch.setattr(mailer, "_send_message", capture)
    code = "synthetic-<code>&\"'"
    getattr(mailer, method)("member@example.invalid", code)
    assert code in observed["body"] and expiry in observed["body"]
    assert "synthetic-&lt;code&gt;&amp;&quot;&#x27;" in observed["html"]
    assert code not in observed["html"] and expiry in observed["html"]
    assert "YOUR ONE-TIME CODE" in observed["html"]
    assert "<img" not in observed["html"] and "<script" not in observed["html"]
    assert code not in observed["html"].split("</div>", 1)[0]


def test_other_email_content_is_escaped_without_a_code_panel():
    from app.accounts.email_template import email_html

    html = email_html("<Private subject>", "A notification.\n\n<script>bad()</script>", sender="review@example.invalid")
    assert "&lt;Private subject&gt;" in html and "&lt;script&gt;bad()&lt;/script&gt;" in html
    assert "YOUR ONE-TIME CODE" not in html and "<script>" not in html


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
