import pytest
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
