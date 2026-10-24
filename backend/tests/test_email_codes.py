"""Short email proofs must not be portable across mailboxes or authentication flows."""

import hashlib

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.accounts.email_codes import code_digest, code_digests, issue_code
from app.config import Settings


@pytest.fixture
def settings():
    return Settings(
        database_url="postgresql+psycopg://synthetic:synthetic@localhost/synthetic",
        allowed_origins=["http://localhost:5173"], environment="test",
        attempt_subject_key=Fernet.generate_key().decode(), _env_file=None,
    )


def test_code_digest_is_keyed_mailbox_and_purpose_bound(settings):
    recipient, code = "synthetic@example.test", "000042"
    digest = code_digest(settings, "registration", recipient, code)
    assert code_digests(settings, "registration", recipient, code) == (digest,)
    assert digest != hashlib.sha256(code.encode()).digest()
    assert digest != code_digest(settings, "recovery", recipient, code)
    assert digest != code_digest(settings, "registration", "other@example.test", code)
    settings.attempt_subject_key = SecretStr(Fernet.generate_key().decode())
    assert digest != code_digest(settings, "registration", recipient, code)


def test_previously_sent_long_codes_keep_their_legacy_digest(settings):
    code = "previously-issued-invitation-code"
    assert hashlib.sha256(code.encode()).digest() in code_digests(settings, "recovery", "synthetic@example.test", code)
    assert len(code_digests(settings, "recovery", "synthetic@example.test", "☃")) == 1


def test_collision_exhaustion_fails_without_reissuing_a_current_code(monkeypatch, settings):
    monkeypatch.setattr("app.accounts.email_codes.secrets.randbelow", lambda _: 42)
    code, digest = issue_code(settings, "registration", "synthetic@example.test", set())
    assert code == "000042"
    with pytest.raises(RuntimeError, match="distinct email code"):
        issue_code(settings, "registration", "synthetic@example.test", {digest})
