"""Synthetic regression checks for privacy at the production HTTP/config boundary."""

import logging
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine

from app.config import Settings
from app.factory import create_app

ORIGIN = "https://app.example.invalid"


def settings(**overrides):
    values = {
        "database_url": "postgresql+psycopg://synthetic:synthetic@localhost/review",
        "allowed_origins": [ORIGIN],
        "environment": "test",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize(
    "query",
    [
        "",
        "?sslmode=disable",
        "?sslmode=prefer",
        "?sslmode=require",
        "?sslmode=verify-ca",
        "?sslmode=verify-full",
    ],
)
def test_production_remote_database_requires_verified_tls(query):
    with pytest.raises(ValidationError):
        settings(
            database_url="postgresql+psycopg://synthetic:synthetic@db.example.invalid/review"
            + query,
            environment="production",
            active_key_id="synthetic",
            content_keys={"synthetic": Fernet.generate_key().decode()},
        )


def test_production_accepts_verified_remote_database():
    configured = settings(
        database_url="postgresql+psycopg://synthetic:synthetic@db.example.invalid/review?sslmode=verify-full&sslrootcert=system",
        environment="production",
        active_key_id="synthetic",
        content_keys={"synthetic": Fernet.generate_key().decode()},
    )
    assert configured.environment == "production"


def test_unknown_path_text_and_control_characters_never_reach_access_logs(caplog):
    app = create_app(settings(), engine=create_engine("sqlite://"))
    with caplog.at_level(logging.INFO, logger="app.access"):
        response = TestClient(app).get(
            "/api/v1/missing/synthetic-secret%40example.invalid%0Aforged-line"
        )
    assert response.status_code == 404
    messages = [record.getMessage() for record in caplog.records if record.name == "app.access"]
    assert len(messages) == 1
    assert "synthetic-secret" not in messages[0]
    assert "forged-line" not in messages[0]
    assert "\n" not in messages[0]


def test_non_ascii_csrf_header_is_rejected_without_a_server_error(monkeypatch):
    app = create_app(settings(), engine=create_engine("sqlite://"))
    monkeypatch.setattr(
        "app.accounts.api.current_identity", lambda _request: SimpleNamespace(csrf_token="a" * 64)
    )
    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/auth/sign-out",
        headers=[(b"origin", ORIGIN.encode()), (b"x-csrf-token", b"\xff")],
    )
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_denied"


def test_unexpected_errors_have_safe_json_headers_and_logs(caplog):
    app = create_app(settings(), engine=create_engine("sqlite://"))

    @app.get("/api/v1/synthetic-error")
    def fail():
        raise RuntimeError("synthetic-private-source-and-secret")

    with caplog.at_level(logging.INFO):
        response = TestClient(app).get("/api/v1/synthetic-error")
    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"].startswith("default-src 'none'")
    assert "synthetic-private-source" not in response.text
    assert "synthetic-private-source" not in caplog.text
    assert not any(record.exc_info for record in caplog.records)
