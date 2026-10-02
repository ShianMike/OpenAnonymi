"""Auth behavior against an explicitly chosen local PostgreSQL test server."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.accounts.recovery import RecoveryDeliveryError
from app.accounts.security import COOKIE_NAME, hash_password
from app.config import Settings
from app.db.models import Membership, RecoveryToken, User, Workspace
from app.db.models import Session as StoredSession
from app.factory import create_app

ORIGIN = "http://localhost:5173"
PASSWORD = "synthetic-password-123"


@pytest.fixture
def auth_site():
    raw_url = os.getenv("PRIVACY_REVIEW_TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("set PRIVACY_REVIEW_TEST_DATABASE_URL for the local database gate")
    url = make_url(raw_url)
    if url.host not in ("127.0.0.1", "localhost") or url.port not in (5433, 5434):
        pytest.fail("authentication test requires a local database on port 5433 or 5434")
    engine = create_engine(raw_url, pool_pre_ping=True, hide_parameters=True)
    workspace_id, member_id, other_id, admin_id = (uuid4() for _ in range(4))
    identities = (
        (member_id, "member-a@example.invalid", "member"),
        (other_id, "member-b@example.invalid", "member"),
        (admin_id, "admin@example.invalid", "administrator"),
    )
    with Session(engine) as session, session.begin():
        session.add(Workspace(id=workspace_id, name="Auth test workspace"))
        session.add_all(
            User(id=user_id, email=email, password_hash=hash_password(PASSWORD))
            for user_id, email, _role in identities
        )
        session.flush()
        session.add_all(
            Membership(workspace_id=workspace_id, user_id=user_id, role=role)
            for user_id, _email, role in identities
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
        with TestClient(create_app(settings, engine=engine)) as client:
            yield client, engine, workspace_id, member_id, other_id, admin_id
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(Membership).where(Membership.workspace_id == workspace_id))
            session.execute(delete(Workspace).where(Workspace.id == workspace_id))
            session.execute(delete(User).where(User.id.in_([member_id, other_id, admin_id])))
        engine.dispose()


def _sign_in(client: TestClient, email: str = "member-a@example.invalid"):
    return client.post(
        "/api/v1/auth/sign-in",
        json={"email": email, "password": PASSWORD},
        headers={"Origin": ORIGIN},
    )


def test_sign_in_session_recovery_and_protected_sign_out(auth_site):
    client, engine, workspace_id, member_id, _other_id, _admin_id = auth_site
    denied = client.post(
        "/api/v1/auth/sign-in",
        json={"email": "member-a@example.invalid", "password": "wrong-password"},
        headers={"Origin": ORIGIN},
    )
    assert denied.status_code == 401
    assert COOKIE_NAME not in denied.headers.get("set-cookie", "")

    signed_in = _sign_in(client)
    assert signed_in.status_code == 200
    token = client.cookies.get(COOKIE_NAME)
    assert token
    assert signed_in.json()["user_id"] == str(member_id)
    assert signed_in.json()["memberships"] == [
        {
            "workspace_id": str(workspace_id),
            "role": "member",
            "workspace_name": "Auth test workspace",
        }
    ]
    assert "httponly" in signed_in.headers["set-cookie"].lower()
    assert "samesite=lax" in signed_in.headers["set-cookie"].lower()
    assert "path=/api/v1" in signed_in.headers["set-cookie"].lower()
    with Session(engine) as session:
        stored = session.scalar(select(StoredSession).where(StoredSession.user_id == member_id))
        assert stored is not None
        assert token.encode() != stored.token_hash
        assert len(stored.csrf_hash) == 32

    reloaded = client.get("/api/v1/auth/session")
    assert reloaded.json()["memberships"][0]["workspace_name"] == "Auth test workspace"
    assert reloaded.status_code == 200
    csrf = signed_in.json()["csrf_token"]
    assert reloaded.json()["csrf_token"] == csrf

    assert client.post("/api/v1/auth/sign-out", headers={"Origin": ORIGIN}).status_code == 403
    assert (
        client.post(
            "/api/v1/auth/sign-out",
            headers={"Origin": "http://example.invalid", "X-CSRF-Token": csrf},
        ).status_code
        == 403
    )
    assert client.get("/api/v1/auth/session").status_code == 200

    signed_out = client.post(
        "/api/v1/auth/sign-out", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf}
    )
    assert signed_out.status_code == 204
    assert client.get("/api/v1/auth/session").status_code == 401


def test_expired_and_revoked_membership_sessions_are_denied(auth_site):
    client, engine, workspace_id, member_id, _other_id, admin_id = auth_site
    assert _sign_in(client).status_code == 200
    with Session(engine) as session, session.begin():
        stored = session.scalar(select(StoredSession).where(StoredSession.user_id == member_id))
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert client.get("/api/v1/auth/session").status_code == 401

    assert _sign_in(client).status_code == 200
    with Session(engine) as session, session.begin():
        membership = session.get(Membership, (workspace_id, member_id))
        membership.revoked_at = datetime.now(UTC)
    assert client.get("/api/v1/auth/session").status_code == 401

    admin_sign_in = _sign_in(client, "admin@example.invalid")
    assert admin_sign_in.status_code == 200
    assert admin_sign_in.json()["user_id"] == str(admin_id)
    assert admin_sign_in.json()["memberships"][0]["role"] == "administrator"


def test_sign_in_attempts_are_bounded(auth_site):
    client, _engine, _workspace_id, _member_id, _other_id, _admin_id = auth_site
    for _ in range(8):
        response = client.post(
            "/api/v1/auth/sign-in",
            json={"email": "member-a@example.invalid", "password": "wrong-password"},
            headers={"Origin": ORIGIN},
        )
        assert response.status_code == 401
    limited = _sign_in(client)
    assert limited.status_code == 429


def test_production_cookie_is_secure_and_foreign_origin_cannot_sign_in(auth_site):
    _client, engine, _workspace_id, _member_id, _other_id, _admin_id = auth_site
    origin = "https://review.example.invalid"
    settings = Settings(
        database_url=os.environ["PRIVACY_REVIEW_TEST_DATABASE_URL"],
        allowed_origins=[origin],
        environment="production",
        active_key_id="synthetic",
        content_keys={"synthetic": Fernet.generate_key().decode()},
        _env_file=None,
    )
    with TestClient(create_app(settings, engine=engine)) as production_client:
        denied = production_client.post(
            "/api/v1/auth/sign-in",
            json={"email": "member-a@example.invalid", "password": PASSWORD},
            headers={"Origin": "https://other.example.invalid"},
        )
        assert denied.status_code == 403
        signed_in = production_client.post(
            "/api/v1/auth/sign-in",
            json={"email": "member-a@example.invalid", "password": PASSWORD},
            headers={"Origin": origin},
        )
        assert signed_in.status_code == 200
        assert "secure" in signed_in.headers["set-cookie"].lower()


class CapturingMailer:
    def __init__(self, *, fail: bool = False) -> None:
        self.sent: list[tuple[str, str]] = []
        self.fail = fail

    def send_recovery_code(self, recipient: str, code: str) -> None:
        if self.fail:
            raise RecoveryDeliveryError("Synthetic delivery failure")
        self.sent.append((recipient, code))


def _request_recovery(client: TestClient, email: str):
    return client.post(
        "/api/v1/auth/recovery/request",
        json={"email": email},
        headers={"Origin": ORIGIN},
    )


def test_recovery_requires_delivery_and_revokes_existing_sessions(auth_site):
    client, engine, _workspace_id, member_id, _other_id, _admin_id = auth_site
    assert _request_recovery(client, "member-a@example.invalid").status_code == 503
    mailer = CapturingMailer()
    client.app.state.recovery_mailer = mailer
    assert _request_recovery(client, "unknown@example.invalid").status_code == 202
    assert not mailer.sent
    assert _sign_in(client).status_code == 200
    assert _request_recovery(client, "member-a@example.invalid").status_code == 202
    assert len(mailer.sent) == 1
    recipient, code = mailer.sent[0]
    assert recipient == "member-a@example.invalid"
    with Session(engine) as session:
        token = session.scalar(select(RecoveryToken).where(RecoveryToken.user_id == member_id))
        assert token is not None
        assert code.encode() != token.token_hash

    new_password = "new-synthetic-password-456"
    invalid = client.post(
        "/api/v1/auth/recovery/complete",
        json={"email": recipient, "code": "invalid-code", "new_password": new_password},
        headers={"Origin": ORIGIN},
    )
    assert invalid.status_code == 400
    completed = client.post(
        "/api/v1/auth/recovery/complete",
        json={"email": recipient, "code": code, "new_password": new_password},
        headers={"Origin": ORIGIN},
    )
    assert completed.status_code == 204
    assert client.get("/api/v1/auth/session").status_code == 401
    assert _sign_in(client).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/sign-in",
            json={"email": recipient, "password": new_password},
            headers={"Origin": ORIGIN},
        ).status_code
        == 200
    )
    replay = client.post(
        "/api/v1/auth/recovery/complete",
        json={"email": recipient, "code": code, "new_password": new_password},
        headers={"Origin": ORIGIN},
    )
    assert replay.status_code == 400


def test_failed_recovery_delivery_does_not_leave_usable_code(auth_site):
    client, engine, _workspace_id, member_id, _other_id, _admin_id = auth_site
    client.app.state.recovery_mailer = CapturingMailer(fail=True)
    failed = _request_recovery(client, "member-a@example.invalid")
    assert failed.status_code == 503
    with Session(engine) as session:
        assert (
            session.scalars(select(RecoveryToken).where(RecoveryToken.user_id == member_id)).all()
            == []
        )


def test_expired_recovery_code_is_denied(auth_site):
    client, engine, _workspace_id, member_id, _other_id, _admin_id = auth_site
    mailer = CapturingMailer()
    client.app.state.recovery_mailer = mailer
    assert _request_recovery(client, "member-a@example.invalid").status_code == 202
    with Session(engine) as session, session.begin():
        token = session.scalar(select(RecoveryToken).where(RecoveryToken.user_id == member_id))
        token.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    denied = client.post(
        "/api/v1/auth/recovery/complete",
        json={
            "email": "member-a@example.invalid",
            "code": mailer.sent[0][1],
            "new_password": "new-synthetic-password-456",
        },
        headers={"Origin": ORIGIN},
    )
    assert denied.status_code == 400


@pytest.fixture
def registered_account(auth_site):
    client, engine, *_ = auth_site
    email = f"new-{uuid4().hex}@example.invalid"
    response = client.post(
        "/api/v1/auth/sign-up",
        json={"email": email, "password": PASSWORD, "workspace_name": "My new workspace"},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 201
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=lax" in response.headers["set-cookie"].lower()
    assert "path=/api/v1" in response.headers["set-cookie"].lower()
    identity = response.json()
    try:
        yield client, engine, email, identity
    finally:
        with Session(engine) as session, session.begin():
            user = session.scalar(select(User).where(User.email == email))
            if user:
                memberships = session.scalars(
                    select(Membership).where(Membership.user_id == user.id)
                ).all()
                workspace_ids = [item.workspace_id for item in memberships]
                session.execute(delete(Membership).where(Membership.user_id == user.id))
                session.execute(delete(Workspace).where(Workspace.id.in_(workspace_ids)))
                session.execute(delete(User).where(User.id == user.id))


def test_registration_creates_separate_workspace_and_revocable_session(
    registered_account, auth_site
):
    client, engine, email, identity = registered_account
    original_workspace = auth_site[2]
    assert identity["email"] == email
    assert len(identity["memberships"]) == 1
    membership = identity["memberships"][0]
    assert membership["workspace_id"] != str(original_workspace)
    assert membership["role"] == "administrator"
    assert membership["workspace_name"] == "My new workspace"
    reloaded = client.get("/api/v1/auth/session").json()
    assert datetime.fromisoformat(reloaded.pop("expires_at")) == datetime.fromisoformat(
        identity["expires_at"]
    )
    assert reloaded == {key: value for key, value in identity.items() if key != "expires_at"}
    assert client.get(f"/api/v1/workspaces/{original_workspace}/documents").status_code == 404
    with Session(engine) as session:
        user = session.scalar(select(User).where(User.email == email))
        assert user.password_hash.startswith("$argon2")
        assert user.password_hash != PASSWORD
        records = session.scalars(
            select(StoredSession).where(StoredSession.user_id == user.id)
        ).all()
        assert len(records) == 1
        assert records[0].token_hash != client.cookies[COOKIE_NAME].encode()
    headers = {"Origin": ORIGIN, "X-CSRF-Token": identity["csrf_token"]}
    assert client.post("/api/v1/auth/sign-out", headers=headers).status_code == 204
    assert client.get("/api/v1/auth/session").status_code == 401
    assert _sign_in(client, email).status_code == 200


def test_registration_duplicate_is_atomic_and_never_takes_over_account(registered_account):
    client, engine, email, identity = registered_account
    with Session(engine) as session:
        before = set(session.scalars(select(Workspace.id)).all())
    response = client.post(
        "/api/v1/auth/sign-up",
        json={
            "email": f"  {email.upper()}  ",
            "password": "a-different-password",
            "workspace_name": "Unwanted",
        },
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 409
    assert "set-cookie" not in response.headers
    assert client.get("/api/v1/auth/session").json()["user_id"] == identity["user_id"]
    with Session(engine) as session:
        assert set(session.scalars(select(Workspace.id)).all()) == before
    assert _sign_in(client, email).status_code == 200


def test_registration_origin_validation_access_fields_and_throttling(auth_site):
    client, engine, workspace_id, *_ = auth_site
    body = {"email": "not-an-email", "password": PASSWORD, "workspace_name": "Workspace"}
    assert client.post("/api/v1/auth/sign-up", json=body).status_code == 403
    assert (
        client.post(
            "/api/v1/auth/sign-up",
            json={**body, "workspace_id": str(workspace_id)},
            headers={"Origin": ORIGIN},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/auth/sign-up",
            json={**body, "role": "administrator"},
            headers={"Origin": ORIGIN},
        ).status_code
        == 422
    )
    for _ in range(3):
        assert (
            client.post("/api/v1/auth/sign-up", json=body, headers={"Origin": ORIGIN}).status_code
            == 422
        )
    assert (
        client.post("/api/v1/auth/sign-up", json=body, headers={"Origin": ORIGIN}).status_code
        == 429
    )
    with Session(engine) as session:
        assert session.scalar(select(User).where(User.email == body["email"])) is None


def test_registration_can_be_closed_by_operator(auth_site):
    client, *_ = auth_site
    client.app.state.settings.registration_enabled = False
    response = client.post(
        "/api/v1/auth/sign-up",
        json={
            "email": "closed@example.invalid",
            "password": PASSWORD,
            "workspace_name": "Closed",
        },
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "registration_closed"
