"""Paste, file, and revision workflow on an explicit local PostgreSQL database."""

import os
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.accounts.security import hash_password
from app.config import Settings
from app.db.models import Document, Membership, SourceRevision, User, Workspace
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
        with (
            TestClient(create_app(settings, engine=engine)) as owner,
            TestClient(create_app(settings, engine=engine)) as other,
        ):
            yield owner, other, engine, workspace_id, owner_id
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(Document).where(Document.workspace_id == workspace_id))
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


def test_paste_save_reopen_revision_and_stale_conflict(intake_site):
    owner, other, engine, workspace_id, _owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    _login(other, "intake-other@example.invalid")
    defaults = owner.get(f"/api/v1/documents/intake-defaults/{workspace_id}")
    assert defaults.status_code == 200
    assert defaults.json()["content_retention_days"] == 7

    created = owner.post("/api/v1/documents", json=_draft_body(workspace_id), headers=headers)
    assert created.status_code == 201, created.text
    version = created.json()["version"]
    assert created.json()["status"] == "draft"
    assert "Synthetic owner" not in created.text
    document_id = version["document_id"]
    path = f"/api/v1/documents/{document_id}/source"
    reopened = owner.get(path)
    assert reopened.status_code == 200
    assert reopened.json()["text"] == "Synthetic owner 😀\r\nsecond line"
    assert reopened.json()["title"] == "Synthetic optional title"
    assert reopened.json()["categories"] == ["email", "phone"]
    assert reopened.json()["phone_region"] == "PH"
    assert reopened.headers["Cache-Control"] == "no-store"
    assert other.get(path).status_code == 404
    with Session(engine) as session:
        revision = session.get(SourceRevision, version["source_revision_id"])
        assert revision is not None
        assert b"Synthetic owner" not in revision.source_ciphertext
        assert (
            session.get(Document, version["document_id"]).title_ciphertext
            != b"Synthetic optional title"
        )

    changed_text = "Synthetic owner 😀\r\nchanged line"
    edited = owner.put(
        path,
        json={"expected": version, "source": changed_text},
        headers=headers,
    )
    assert edited.status_code == 200
    next_version = edited.json()["version"]
    assert next_version["source_revision_id"] != version["source_revision_id"]
    assert next_version["decision_version"] == version["decision_version"] + 1
    assert owner.get(path).json()["text"] == changed_text
    with Session(engine) as session:
        revisions = session.scalars(
            select(SourceRevision).where(SourceRevision.document_id == document_id)
        ).all()
        assert {row.revision_number for row in revisions} == {1, 2}
    stale = owner.put(
        path,
        json={"expected": version, "source": "Stale data"},
        headers=headers,
    )
    assert stale.status_code == 409
    assert stale.json()["current_version"] == next_version
    assert owner.get(path).json()["text"] == changed_text
    assert (
        other.put(
            path,
            json={"expected": next_version, "source": "Intrusion"},
            headers={
                "Origin": ORIGIN,
                "X-CSRF-Token": other.get("/api/v1/auth/session").json()["csrf_token"],
            },
        ).status_code
        == 404
    )


def test_file_intake_and_rejections(intake_site):
    owner, other, engine, workspace_id, _owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    _login(other, "intake-other@example.invalid")
    path = "/api/v1/documents/from-file"
    data = {
        "workspace_id": str(workspace_id),
        "title": "",
        "categories": "email,phone",
        "phone_region": "PH",
        "retention_days": "2",
    }
    valid = owner.post(
        path,
        data=data,
        files={"file": ("synthetic.txt", b"\xef\xbb\xbfHello\r\nworld", "text/plain")},
        headers=headers,
    )
    assert valid.status_code == 201, valid.text
    source = owner.get(f"/api/v1/documents/{valid.json()['version']['document_id']}/source")
    assert source.json()["text"] == "Hello\r\nworld"
    assert source.json()["title"] is None
    for filename, content in (
        ("synthetic.pdf", b"Hello"),
        ("synthetic.txt", b"\xff"),
        ("synthetic.txt", b" \r\n"),
        ("synthetic.txt", b"Hello\x00world"),
        ("synthetic.txt", b"x" * 1_048_577),
    ):
        rejected = owner.post(
            path,
            data=data,
            files={"file": (filename, content, "application/octet-stream")},
            headers=headers,
        )
        assert rejected.status_code == 422, rejected.text
        assert filename not in rejected.text
    multiple = owner.post(
        path,
        data=data,
        files=[
            ("file", ("one.txt", b"One", "text/plain")),
            ("file", ("two.txt", b"Two", "text/plain")),
        ],
        headers=headers,
    )
    assert multiple.status_code == 422
    assert other.get(f"/api/v1/documents/intake-defaults/{uuid4()}").status_code == 404
    with Session(engine) as session:
        assert (
            len(
                session.scalars(select(Document).where(Document.workspace_id == workspace_id)).all()
            )
            == 1
        )


def test_paste_validation_and_expiry_limit(intake_site):
    owner, _other, engine, workspace_id, _owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    for source in ("", " \r\n", "x" * 100_001, "Hello\x1bworld"):
        response = owner.post(
            "/api/v1/documents",
            json=_draft_body(workspace_id, source=source),
            headers=headers,
        )
        assert response.status_code in (422, 400)
        assert "Synthetic optional title" not in response.text
    too_long = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, retention_days=8),
        headers=headers,
    )
    assert too_long.status_code == 422
    with Session(engine) as session:
        assert (
            session.scalars(select(Document).where(Document.workspace_id == workspace_id)).all()
            == []
        )


def test_content_intake_refuses_to_save_without_encryption_key(intake_site):
    _owner, _other, engine, workspace_id, _owner_id = intake_site
    settings = Settings(
        database_url=os.environ["PRIVACY_REVIEW_TEST_DATABASE_URL"],
        allowed_origins=[ORIGIN],
        environment="test",
        _env_file=None,
    )
    with TestClient(create_app(settings, engine=engine)) as client:
        headers = _login(client, "intake-owner@example.invalid")
        response = client.post(
            "/api/v1/documents",
            json=_draft_body(workspace_id),
            headers=headers,
        )
        assert response.status_code == 503
        assert "Synthetic owner" not in response.text
    with Session(engine) as session:
        assert (
            session.scalars(select(Document).where(Document.workspace_id == workspace_id)).all()
            == []
        )
