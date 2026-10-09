"""Actual website/API routing and privacy headers in the combined ASGI server."""

from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.edge import SecurityHeadersMiddleware
from app.site import FrontendFiles, FrontendMount


@pytest.fixture
def site(tmp_path):
    index = '<html><div id="root">Synthetic website</div></html>'
    (tmp_path / "index.html").write_text(index, encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/app-hash.js").write_text("window.synthetic = true", encoding="utf-8")
    (tmp_path / ".env").write_text("synthetic-private-setting", encoding="utf-8")
    (tmp_path / "api").mkdir()
    (tmp_path / "api/hidden.js").write_text("synthetic-private-file", encoding="utf-8")
    events = []

    @asynccontextmanager
    async def lifespan(_app):
        events.append("started")
        yield
        events.append("stopped")

    app = FastAPI(
        docs_url=None, redoc_url=None, openapi_url=None,
        redirect_slashes=False, lifespan=lifespan,
    )
    app.add_middleware(SecurityHeadersMiddleware, strict_transport=True)

    @app.get("/api/v1/health/ready")
    def ready():
        return {"ok": True}

    app.router.routes.append(FrontendMount("/", app=FrontendFiles(directory=tmp_path, html=True)))
    with TestClient(app) as client:
        assert events == ["started"]
        yield client, index
    assert events == ["started", "stopped"]


@pytest.mark.parametrize("path", ["/", "/documents", "/review/synthetic-id", "/preferences", "/terms", "/privacy"])
def test_website_and_deep_links_serve_the_compiled_index(site, path):
    client, index = site
    response = client.get(path)
    assert response.status_code == 200 and response.text == index
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-security-policy"] == "frame-ancestors 'none'"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["strict-transport-security"].startswith("max-age=63072000")
    assert client.head(path).status_code == 200
    assert client.head(path).content == b""
    conditional = client.get(path, headers={"If-None-Match": response.headers["etag"]})
    assert conditional.status_code == 304
    assert conditional.headers["cache-control"] == "no-store"


def test_existing_api_prefix_and_policy_survive_the_frontend_mount(site):
    client, _ = site
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200 and response.json() == {"ok": True}
    assert response.headers["content-security-policy"].startswith("default-src 'none'")
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("method", ["POST", "SYNTHETIC_PRIVATE_METHOD"])
def test_existing_api_preserves_method_denial_and_unknown_api_preserves_404(site, method):
    client, index = site
    response = client.request(method, "/api/v1/health/ready")
    assert response.status_code == 405 and index not in response.text
    assert "GET" in response.headers["allow"]
    for path in ["/api/v1/unknown", "/api/hidden.js", "/api/v1/health/ready/", "/docs"]:
        response = client.request(method, path)
        assert response.status_code == 404 and index not in response.text


@pytest.mark.parametrize("path", [
    "/api", "/api/v1/unknown", "/api/hidden.js", "/docs", "/redoc", "/openapi.json",
    "/assets/missing.js", "/assets/missing", "/.env", "/.git/config", "/app/config.py",
])
def test_unknown_api_assets_and_private_paths_never_receive_the_spa(site, path):
    client, index = site
    response = client.get(path)
    assert response.status_code == 404
    assert index not in response.text
    assert "synthetic-private" not in response.text


def test_assets_have_correct_types_and_non_get_routes_do_not_fall_back(site):
    client, index = site
    response = client.get("/assets/app-hash.js")
    assert response.status_code == 200 and "javascript" in response.headers["content-type"]
    assert response.text == "window.synthetic = true"
    assert response.headers["cache-control"] == "no-cache"
    response = client.post("/documents")
    assert response.status_code == 405 and index not in response.text
