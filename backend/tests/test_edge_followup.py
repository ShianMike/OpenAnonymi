"""Production proxy redirects and attacker-controlled HTTP metadata regressions."""

import logging

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.config import Settings
from app.factory import create_app

ORIGIN = "https://app.example.invalid"


def client(environment="production"):
    settings = Settings(
        database_url="postgresql+psycopg://synthetic:synthetic@localhost/review",
        allowed_origins=[ORIGIN],
        environment=environment,
        attempt_subject_key=Fernet.generate_key().decode(),
        active_key_id="synthetic",
        content_keys={"synthetic": Fernet.generate_key().decode()},
        _env_file=None,
    )
    # A proxy terminates TLS; the ASGI request itself still has an HTTP scheme.
    return TestClient(
        create_app(settings, engine=create_engine("sqlite://")),
        base_url="http://internal-api",
        follow_redirects=False,
    )


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/meta/"),
        ("GET", "/api/v1/health/live/"),
        ("POST", "/api/v1/auth/sign-in/"),
    ],
)
def test_production_never_redirects_noncanonical_api_paths_to_plain_http(method, path):
    response = client().request(method, path, headers={"Origin": ORIGIN})
    assert response.status_code == 404
    assert "location" not in response.headers
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["strict-transport-security"].startswith("max-age=")


@pytest.mark.parametrize("path", ["/api/v1/meta", "/api/v1/health/live"])
def test_canonical_production_paths_still_work_without_redirects(path):
    response = client().get(path)
    assert response.status_code == 200
    assert "location" not in response.headers


@pytest.mark.parametrize("path", ["/docs", "/docs/oauth2-redirect", "/redoc", "/docs-private"])
def test_disabled_production_docs_and_lookalikes_keep_csp(path):
    response = client().get(path)
    assert response.status_code == 404
    assert response.headers["content-security-policy"].startswith("default-src 'none'")
    assert response.headers["x-content-type-options"] == "nosniff"


def test_development_docs_still_load_and_lookalikes_are_protected():
    development = client("test")
    docs = development.get("/docs")
    assert docs.status_code == 200
    assert "content-security-policy" not in docs.headers
    missing = development.get("/docs-private")
    assert missing.status_code == 404
    assert missing.headers["content-security-policy"].startswith("default-src 'none'")


def test_unsupported_http_method_never_echoes_private_text_into_access_log(caplog):
    with caplog.at_level(logging.INFO, logger="app.access"):
        response = client().request("SYNTHETIC_PRIVATE_METHOD", "/api/v1/meta")
    assert response.status_code == 405
    messages = [record.getMessage() for record in caplog.records if record.name == "app.access"]
    assert len(messages) == 1
    assert "SYNTHETIC_PRIVATE_METHOD" not in messages[0]
    assert "/api/v1/meta" in messages[0]
