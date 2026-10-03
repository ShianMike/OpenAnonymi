"""Proxy-facing behavior that needs no database: client address, cookies, headers, limits."""

import logging

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.accounts import api as accounts_api
from app.accounts.api import _session_cookie
from app.accounts.security import InvalidCredentials
from app.config import Settings
from app.edge import MAX_REQUEST_BYTES, attempt_key, client_address
from app.factory import create_app

ORIGIN = "https://review.example.invalid"
DOCUMENT_ID = "0b6f2c4e-6c1d-4a59-9d61-3f0c5c1f2a77"


def _settings(**overrides) -> Settings:
    values = {
        "database_url": "postgresql+psycopg://test:test@localhost/review",
        "allowed_origins": [ORIGIN],
        "environment": "test",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


def _production(**overrides) -> Settings:
    return _settings(
        environment="production",
        active_key_id="synthetic",
        content_keys={"synthetic": Fernet.generate_key().decode()},
        **overrides,
    )


def _app(settings: Settings):
    return create_app(settings, engine=create_engine("sqlite://"))


def test_client_address_trusts_only_configured_proxy_hops():
    peer = "10.0.0.5"
    assert client_address([], peer, 0) == peer
    assert client_address(["203.0.113.9"], peer, 0) == peer
    assert client_address(["198.51.100.7"], peer, 1) == "198.51.100.7"
    assert client_address(["203.0.113.9, 198.51.100.7"], peer, 1) == "198.51.100.7"
    assert client_address(["203.0.113.9", "198.51.100.7, 10.1.2.3"], peer, 2) == "198.51.100.7"
    assert client_address(["198.51.100.7"], peer, 2) == peer
    assert client_address(["not-an-address"], peer, 1) == peer
    assert client_address(["198.51.100.7:4711"], peer, 1) == "198.51.100.7"
    assert client_address(['"[2001:db8::1]:443"'], peer, 1) == "2001:db8::1"
    assert client_address(["::ffff:198.51.100.7"], peer, 1) == "198.51.100.7"
    assert client_address([], None, 1) == "unknown"


def test_attempt_key_groups_ipv6_subscriber_prefixes():
    assert attempt_key("2001:db8:1:2:aaaa::1") == "2001:db8:1:2::/64"
    assert attempt_key("2001:db8:1:2:bbbb::2") == "2001:db8:1:2::/64"
    assert attempt_key("198.51.100.7") == "198.51.100.7"
    assert attempt_key("testclient") == "testclient"


def test_production_session_cookie_is_cross_site_and_cleared_with_the_same_attributes():
    settings = _production()
    issued = _session_cookie("synthetic-token", max_age=43200, settings=settings)
    cleared = _session_cookie("", max_age=0, settings=settings)
    assert issued == (
        "openanonymi_session=synthetic-token; Max-Age=43200; Path=/api/v1; "
        "HttpOnly; Secure; SameSite=None; Partitioned"
    )
    assert cleared.startswith("openanonymi_session=; Max-Age=0; Path=/api/v1; Expires=")
    for attribute in ("HttpOnly", "Secure", "SameSite=None", "Partitioned"):
        assert attribute in cleared


def test_development_session_cookie_stays_lax_for_plain_http():
    issued = _session_cookie("synthetic-token", max_age=43200, settings=_settings())
    assert issued.endswith("HttpOnly; SameSite=Lax")
    assert "Secure" not in issued and "Partitioned" not in issued


def test_attempt_limits_use_the_trusted_forwarded_address(monkeypatch):
    def reject(*_args, **_kwargs):
        raise InvalidCredentials("Email or password was not accepted.")

    monkeypatch.setattr(accounts_api, "sign_in", reject)
    body = {"email": "member@example.invalid", "password": "synthetic-password"}

    def attempt(client: TestClient, forwarded: str) -> int:
        headers = {"Origin": ORIGIN, "X-Forwarded-For": forwarded}
        return client.post("/api/v1/auth/sign-in", json=body, headers=headers).status_code

    trusted = TestClient(_app(_settings(trusted_proxy_hops=1)))
    assert [attempt(trusted, "203.0.113.1, 198.51.100.7") for _ in range(8)] == [401] * 8
    # A rotated client-supplied entry does not buy new attempts for the same client.
    assert attempt(trusted, "203.0.113.2, 198.51.100.7") == 429
    # A different client behind the same proxy keeps its own budget.
    assert attempt(trusted, "198.51.100.8") == 401

    untrusted = TestClient(_app(_settings()))
    assert [attempt(untrusted, f"198.51.100.{n}") for n in range(8)] == [401] * 8
    # Without trusted hops a forged header is ignored entirely.
    assert attempt(untrusted, "198.51.100.99") == 429


def test_security_headers_cors_and_cache_policy():
    client = TestClient(_app(_settings()))
    meta = client.get("/api/v1/meta", headers={"Origin": ORIGIN})
    preflight = client.options(
        "/api/v1/auth/sign-in",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-csrf-token",
        },
    )
    foreign = client.options(
        "/api/v1/auth/sign-in",
        headers={"Origin": "https://other.example.invalid", "Access-Control-Request-Method": "POST"},
    )
    assert meta.status_code == 200
    assert meta.headers["access-control-allow-origin"] == ORIGIN
    assert meta.headers["access-control-allow-credentials"] == "true"
    expected = {
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "no-referrer",
        "cross-origin-resource-policy": "same-origin",
        "cache-control": "no-store",
    }
    assert {name: meta.headers.get(name) for name in expected} == expected
    assert "default-src 'none'" in meta.headers["content-security-policy"]
    assert "strict-transport-security" not in meta.headers
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == ORIGIN
    assert preflight.headers["access-control-allow-credentials"] == "true"
    assert "x-csrf-token" in preflight.headers["access-control-allow-headers"].lower()
    assert preflight.headers["cache-control"] == "no-store"
    assert foreign.status_code == 400
    assert "access-control-allow-origin" not in foreign.headers


def test_production_hides_interactive_docs_and_sends_hsts():
    client = TestClient(_app(_production()))
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    meta = client.get("/api/v1/meta")
    assert meta.status_code == 200
    assert meta.headers["strict-transport-security"].startswith("max-age=63072000")


def test_oversized_bodies_are_refused_with_the_error_contract():
    client = TestClient(_app(_settings()))
    headers = {"Origin": ORIGIN, "Content-Type": "application/json"}
    declared = client.post(
        "/api/v1/auth/sign-in", content=b"x" * (MAX_REQUEST_BYTES + 1), headers=headers
    )
    assert declared.status_code == 413
    assert declared.json()["code"] == "request_too_large"
    assert declared.headers["access-control-allow-origin"] == ORIGIN

    def chunks():
        for _ in range(10):
            yield b"x" * (1024 * 1024)

    streamed = client.post("/api/v1/auth/sign-in", content=chunks(), headers=headers)
    assert streamed.status_code == 413
    assert streamed.json() == {
        "code": "request_too_large",
        "message": "The request exceeds the 9 MiB upload limit.",
        "details": [],
    }
    assert streamed.headers["access-control-allow-origin"] == ORIGIN


def test_access_log_records_route_templates_without_identifiers_or_queries(caplog):
    client = TestClient(_app(_settings(trusted_proxy_hops=1)))
    with caplog.at_level(logging.INFO, logger="app.access"):
        client.get(
            f"/api/v1/documents/{DOCUMENT_ID}/source?finding=synthetic-secret",
            headers={"X-Forwarded-For": "203.0.113.5, 198.51.100.7"},
        )
        client.get("/api/v1/health/live")
        client.get(f"/api/v1/unknown/{DOCUMENT_ID}?q=synthetic-secret")
    lines = [record.getMessage() for record in caplog.records if record.name == "app.access"]
    assert any(
        line.startswith("198.51.100.7 ")
        and '"GET /api/v1/documents/{document_id}/source" 401' in line
        for line in lines
    )
    assert any('"GET [unmatched]" 404' in line for line in lines)
    assert not any("/health/live" in line for line in lines)
    joined = "\n".join(lines)
    assert DOCUMENT_ID not in joined
    assert "synthetic-secret" not in joined
    assert "203.0.113.5" not in joined
