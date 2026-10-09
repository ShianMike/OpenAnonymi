import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.config import ConfigurationError, Settings, load_settings


def test_configuration_is_required_and_errors_do_not_reveal_values(monkeypatch):
    monkeypatch.setenv("PRIVACY_REVIEW_DATABASE_URL", "not-a-url-with-secret-123")
    monkeypatch.setenv("PRIVACY_REVIEW_ALLOWED_ORIGINS", '["http://localhost:5173"]')
    with pytest.raises(ConfigurationError) as error:
        load_settings()
    assert "database_url" in str(error.value)
    assert "secret-123" not in str(error.value)


def test_production_rejects_insecure_origin():
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql+psycopg://user:pass@localhost/review",
            allowed_origins=["http://localhost:5173"],
            environment="production",
            _env_file=None,
        )


def test_production_requires_a_stable_attempt_subject_key():
    with pytest.raises(ValidationError, match="stable attempt subject key"):
        Settings(
            database_url="postgresql+psycopg://user:secure@localhost/review",
            allowed_origins=["https://example.test"],
            environment="production",
            active_key_id="synthetic",
            content_keys={"synthetic": Fernet.generate_key().decode()},
            _env_file=None,
        )


def test_invalid_attempt_key_is_sanitized(monkeypatch):
    secret = "invalid-private-subject-key"
    monkeypatch.setenv("PRIVACY_REVIEW_DATABASE_URL", "postgresql+psycopg://user:secure@localhost/review")
    monkeypatch.setenv("PRIVACY_REVIEW_ALLOWED_ORIGINS", '["http://localhost:5173"]')
    monkeypatch.setenv("PRIVACY_REVIEW_ATTEMPT_SUBJECT_KEY", secret)
    with pytest.raises(ConfigurationError) as error:
        load_settings()
    assert "attempt_subject_key" in str(error.value) and secret not in str(error.value)
