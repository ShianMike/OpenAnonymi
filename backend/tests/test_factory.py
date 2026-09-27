from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.config import Settings
from app.contracts import SourceSpan
from app.factory import create_app


def test_liveness_readiness_and_metadata_contract():
    settings = Settings(
        database_url="postgresql+psycopg://test:test@localhost/review",
        allowed_origins=["http://localhost:5173"],
        environment="test",
        _env_file=None,
    )
    engine = create_engine("sqlite://")
    app = create_app(settings, engine=engine)
    with TestClient(app) as client:
        live = client.get("/api/v1/health/live")
        ready = client.get("/api/v1/health/ready")
        metadata = client.get("/api/v1/meta")
    engine.dispose()
    assert live.status_code == 200 and live.json() == {"status": "ok"}
    assert ready.status_code == 200 and ready.json() == {"status": "ok"}
    assert metadata.status_code == 200
    assert metadata.headers["Cache-Control"] == "no-store"
    assert metadata.json()["source_max_code_points"] == 100_000
    assert "/api/v1/meta" in app.openapi()["paths"]


def test_validation_errors_do_not_echo_submitted_text():
    settings = Settings(
        database_url="postgresql+psycopg://test:test@localhost/review",
        allowed_origins=["http://localhost:5173"],
        environment="test",
        _env_file=None,
    )
    app = create_app(settings, engine=create_engine("sqlite://"))

    @app.post("/api/v1/test-span")
    def receive_span(span: SourceSpan):
        return span

    with TestClient(app) as client:
        response = client.post("/api/v1/test-span", json={"start": "synthetic-secret", "end": 3})
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert "synthetic-secret" not in response.text
