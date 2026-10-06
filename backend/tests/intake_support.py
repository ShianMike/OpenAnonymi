"""Paste, file, and revision workflow on an explicit local PostgreSQL database."""

import os
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.accounts.security import hash_password
from app.config import Settings
from app.db.batches import Batch
from app.db.models import (
    Document,
    Membership,
    User,
    Workspace,
)
from app.factory import create_app

ORIGIN = "http://localhost:5173"
PASSWORD = "synthetic-intake-password"


@pytest.fixture
def intake_site():
    raw_url = os.getenv("PRIVACY_REVIEW_TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("set PRIVACY_REVIEW_TEST_DATABASE_URL for the local database gate")
    url = make_url(raw_url)
    if url.host not in ("127.0.0.1", "localhost") or url.port not in (5433, 5434):
        pytest.fail("intake test requires a local database on port 5433 or 5434")
    engine = create_engine(raw_url, pool_pre_ping=True, hide_parameters=True)
    workspace_id, owner_id, other_id = uuid4(), uuid4(), uuid4()
    with Session(engine) as session, session.begin():
        session.add(
            Workspace(id=workspace_id, name="Intake test workspace", content_retention_days=7)
        )
        session.add_all(
            [
                User(
                    id=owner_id,
                    email="intake-owner@example.invalid",
                    password_hash=hash_password(PASSWORD),
                ),
                User(
                    id=other_id,
                    email="intake-other@example.invalid",
                    password_hash=hash_password(PASSWORD),
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                Membership(workspace_id=workspace_id, user_id=owner_id, role="member"),
                Membership(workspace_id=workspace_id, user_id=other_id, role="member"),
            ]
        )
    settings = Settings(
        database_url=raw_url,
        allowed_origins=[ORIGIN],
        environment="test",
        active_key_id="test",
        content_keys={"test": Fernet.generate_key().decode()},
        _env_file=None,
    )
    try:
        app = create_app(settings, engine=engine)
        with (
            TestClient(app) as owner,
            TestClient(app) as other,
        ):
            yield owner, other, engine, workspace_id, owner_id
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(Document).where(Document.workspace_id == workspace_id))
            session.execute(delete(Batch).where(Batch.workspace_id == workspace_id))
            session.execute(delete(Membership).where(Membership.workspace_id == workspace_id))
            session.execute(delete(Workspace).where(Workspace.id == workspace_id))
            session.execute(delete(User).where(User.id.in_([owner_id, other_id])))
        engine.dispose()


def _login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/sign-in",
        json={"email": email, "password": PASSWORD},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 200
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def _draft_body(workspace_id, **overrides):
    return {
        "workspace_id": str(workspace_id),
        "source": "Synthetic owner 😀\r\nsecond line",
        "title": "Synthetic optional title",
        "categories": ["email", "phone"],
        "phone_region": "PH",
        "retention_days": 3,
        **overrides,
    }
