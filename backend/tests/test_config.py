from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError
from sqlalchemy.engine import make_url

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
    monkeypatch.setenv(
        "PRIVACY_REVIEW_DATABASE_URL", "postgresql+psycopg://user:secure@localhost/review"
    )
    monkeypatch.setenv("PRIVACY_REVIEW_ALLOWED_ORIGINS", '["http://localhost:5173"]')
    monkeypatch.setenv("PRIVACY_REVIEW_ATTEMPT_SUBJECT_KEY", secret)
    with pytest.raises(ConfigurationError) as error:
        load_settings()
    assert "attempt_subject_key" in str(error.value) and secret not in str(error.value)


def test_platform_database_uses_verified_tls_and_current_rotated_credentials(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PRIVACY_REVIEW_DATABASE_URL", raising=False)
    monkeypatch.setenv("PRIVACY_REVIEW_ALLOWED_ORIGINS", '["http://localhost:5173"]')
    monkeypatch.setenv("PRIVACY_REVIEW_ENVIRONMENT", "test")
    for password in ("synthetic-first", "synthetic-rotated"):
        monkeypatch.setenv(
            "DATABASE_URL", f"postgres://synthetic:{password}@db.example.invalid/review"
        )
        database = make_url(load_settings().database_url)
        assert database.password == password
        assert database.drivername == "postgresql+psycopg"
        assert database.query["sslmode"] == "verify-full"
        assert Path(database.query["sslrootcert"]).is_file()


@pytest.mark.parametrize("source", ("environment", "dotenv"))
def test_explicit_database_takes_precedence_over_platform_url(monkeypatch, tmp_path, source):
    monkeypatch.chdir(tmp_path)
    explicit = "postgresql+psycopg://synthetic:synthetic@localhost/explicit"
    if source == "environment":
        monkeypatch.setenv("PRIVACY_REVIEW_DATABASE_URL", explicit)
    else:
        monkeypatch.delenv("PRIVACY_REVIEW_DATABASE_URL", raising=False)
        (tmp_path / ".env").write_text("PRIVACY_REVIEW_DATABASE_URL=" + explicit + "\n")
    monkeypatch.setenv("DATABASE_URL", "postgres://synthetic:synthetic@localhost/platform")
    monkeypatch.setenv("PRIVACY_REVIEW_ALLOWED_ORIGINS", '["http://localhost:5173"]')
    monkeypatch.setenv("PRIVACY_REVIEW_ENVIRONMENT", "test")
    assert load_settings().database_url == explicit


@pytest.mark.parametrize("url", ("not-a-url-with-private-value", "postgres://synthetic:private-value@localhost:invalid/review", "sqlite:///private-value"))
def test_invalid_platform_database_does_not_expose_credentials(monkeypatch, tmp_path, url):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PRIVACY_REVIEW_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", url)
    with pytest.raises(ConfigurationError) as error:
        load_settings()
    assert "database_url" in str(error.value)
    assert "private-value" not in str(error.value)
