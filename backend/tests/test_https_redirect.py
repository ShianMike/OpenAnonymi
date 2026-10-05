"""Production HTTPS redirects before authentication, uploads or body parsing."""

import asyncio
import logging

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine

from app.config import Settings
from app.edge import HttpsRedirectMiddleware
from app.factory import create_app

ORIGIN = "https://review.example.invalid"


def settings(**overrides):
    values = {
        "database_url": "postgresql+psycopg://test:test@localhost/review",
        "allowed_origins": [ORIGIN], "environment": "production",
        "active_key_id": "synthetic", "content_keys": {"synthetic": Fernet.generate_key().decode()},
        "trusted_proxy_hops": 1, "https_redirect_enabled": True,
    }
    return Settings(**{**values, **overrides}, _env_file=None)


@pytest.mark.parametrize("protocol", [None, "http", "https,http", "http,https", "invalid"])
def test_plain_http_redirects_without_parsing_signin_body(protocol, caplog):
    client = TestClient(create_app(settings(), engine=create_engine("sqlite://")),
                        base_url=ORIGIN.replace("https:", "http:"))
    headers = {"X-Forwarded-Host": "foreign.example.invalid"}
    if protocol is not None:
        headers["X-Forwarded-Proto"] = protocol
    with caplog.at_level(logging.INFO, logger="app.access"):
        response = client.post("/api/v1/auth/sign-in?synthetic-private-query=secret",
                               content=b"invalid json with fictional credentials",
                               headers=headers, follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == ORIGIN + "/api/v1/auth/sign-in?synthetic-private-query=secret"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["strict-transport-security"].startswith("max-age=63072000")
    assert "set-cookie" not in response.headers
    assert "synthetic-private-query" not in caplog.text and "secret" not in caplog.text


def test_proxy_https_and_direct_tls_keep_existing_health_and_api_method_handling():
    app = create_app(settings(), engine=create_engine("sqlite://"))
    client = TestClient(app, base_url=ORIGIN.replace("https:", "http:"))
    assert client.get("/api/v1/health/live", headers={"X-Forwarded-Proto": "https"}).status_code == 200
    assert client.post("/api/v1/meta", headers={"X-Forwarded-Proto": "https"}).status_code == 405
    direct = TestClient(app, base_url=ORIGIN)
    assert direct.get("/api/v1/health/live", headers={"X-Forwarded-Proto": "http"}).status_code == 200


@pytest.mark.parametrize("host", ["foreign.example.invalid", "review.example.invalid.evil.test",
                                   "review.example.invalid:1234"])
def test_redirect_refuses_unknown_host_without_following_forwarded_host(host):
    client = TestClient(create_app(settings(), engine=create_engine("sqlite://")))
    response = client.get("/api/v1/health/live", headers={"Host": host,
        "X-Forwarded-Host": "review.example.invalid"}, follow_redirects=False)
    assert response.status_code == 400
    assert "location" not in response.headers and "set-cookie" not in response.headers


def test_http_port_eighty_maps_to_configured_https_host():
    client = TestClient(create_app(settings(), engine=create_engine("sqlite://")))
    response = client.get("/sign-in", headers={"Host": "review.example.invalid:80"},
                          follow_redirects=False)
    assert response.status_code == 307 and response.headers["location"] == ORIGIN + "/sign-in"


def test_redirect_preserves_encoded_path_and_query_without_creating_header_control_characters():
    client = TestClient(create_app(settings(), engine=create_engine("sqlite://")),
                        base_url=ORIGIN.replace("https:", "http:"))
    response = client.get("/fictional/caf%C3%A9%0D%0A?q=a%26b", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == ORIGIN + "/fictional/caf%C3%A9%0D%0A?q=a%26b"


def test_duplicate_protocol_headers_do_not_treat_an_insecure_request_as_https():
    client = TestClient(create_app(settings(), engine=create_engine("sqlite://")),
                        base_url=ORIGIN.replace("https:", "http:"))
    response = client.get("/sign-in", headers=[("X-Forwarded-Proto", "https"),
                                               ("X-Forwarded-Proto", "http")], follow_redirects=False)
    assert response.status_code == 307


@pytest.mark.parametrize("path, method, protocol, expected", [
    ("/api/v1/health/live", "GET", None, 200),
    ("/api/v1/health/live", "HEAD", None, 200),
    ("/api/v1/health/ready", "GET", None, 307),
    ("/api/v1/health/live", "POST", None, 307),
    ("/api/v1/health/live", "GET", "http", 307),
])
def test_local_docker_exception_is_only_liveness_with_no_proxy_header(path, method, protocol, expected):
    received = []

    async def app(scope, receive, send):
        received.append(scope["path"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def run():
        headers = [(b"host", b"review.example.invalid")]
        if protocol:
            headers.append((b"x-forwarded-proto", protocol.encode()))
        scope = {"type": "http", "method": method, "path": path, "query_string": b"",
                 "scheme": "http", "headers": headers, "client": ("127.0.0.1", 12345)}
        messages = []

        async def receive():
            pytest.fail("HTTP redirect must never read an uploaded body")

        async def send(message):
            messages.append(message)

        await HttpsRedirectMiddleware(app, allowed_origins=[ORIGIN])(scope, receive, send)
        return messages

    messages = asyncio.run(run())
    assert messages[0]["status"] == expected
    assert bool(received) == (expected == 200)


def test_redirect_setting_requires_explicit_proxy_trust():
    with pytest.raises(ValidationError, match="configured trusted host proxy"):
        settings(trusted_proxy_hops=0)


def test_default_preserves_development_and_existing_hosts_with_edge_https_enforcement():
    client = TestClient(create_app(settings(https_redirect_enabled=False), engine=create_engine("sqlite://")))
    assert client.get("/api/v1/health/live").status_code == 200
