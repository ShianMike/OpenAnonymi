"""Workspace administration and owner isolation on local PostgreSQL."""

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.accounts.recovery import RecoveryDeliveryError
from app.accounts.security import hash_password
from app.config import Settings
from app.contracts import FindingCategory, SourceSpan
from app.db.crypto import KeyRing
from app.db.models import Document, Membership, User, Workspace
from app.db.repository import (
    DocumentNotFound,
    add_manual_finding,
    create_document,
    load_current_source,
)
from app.factory import create_app

ORIGIN = "http://localhost:5173"
PASSWORD = "synthetic-admin-test-password"


@pytest.fixture
def admin_site():
    raw_url = os.getenv("PRIVACY_REVIEW_TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("set PRIVACY_REVIEW_TEST_DATABASE_URL for the local database gate")
    url = make_url(raw_url)
    if url.host not in ("127.0.0.1", "localhost") or url.port not in (5433, 5434):
        pytest.fail("administration test requires a local database on port 5433 or 5434")
    engine = create_engine(raw_url, pool_pre_ping=True, hide_parameters=True)
    workspace_id, admin_id, first_id, second_id = (uuid4() for _ in range(4))
    identities = (
        (admin_id, "admin-access@example.invalid", "administrator"),
        (first_id, "member-first@example.invalid", "member"),
        (second_id, "member-second@example.invalid", "member"),
    )
    with Session(engine) as session, session.begin():
        session.add(Workspace(id=workspace_id, name="Access test workspace"))
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
    app = create_app(settings, engine=engine)
    try:
        yield app, engine, workspace_id, admin_id, first_id, second_id
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(Document).where(Document.workspace_id == workspace_id))
            session.execute(delete(Membership).where(Membership.workspace_id == workspace_id))
            session.execute(delete(Workspace).where(Workspace.id == workspace_id))
            session.execute(delete(User).where(User.id.in_([admin_id, first_id, second_id])))
            invited = session.scalar(select(User).where(User.email == "invited@example.invalid"))
            if invited is not None:
                session.delete(invited)
        engine.dispose()


def _login(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/sign-in",
        json={"email": email, "password": PASSWORD},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"]


def _headers(csrf: str) -> dict[str, str]:
    return {"Origin": ORIGIN, "X-CSRF-Token": csrf}


def test_admin_listing_roles_and_last_administrator_guard(admin_site):
    app, _engine, workspace_id, admin_id, first_id, second_id = admin_site
    with TestClient(app) as admin, TestClient(app) as member:
        admin_csrf = _login(admin, "admin-access@example.invalid")
        member_csrf = _login(member, "member-first@example.invalid")
        path = f"/api/v1/workspaces/{workspace_id}/members"
        listed = admin.get(path)
        assert listed.status_code == 200
        assert {row["user_id"] for row in listed.json()} == {
            str(admin_id),
            str(first_id),
            str(second_id),
        }
        assert member.get(path).status_code == 404
        assert (
            member.patch(
                f"{path}/{second_id}/role",
                json={"role": "administrator"},
                headers=_headers(member_csrf),
            ).status_code
            == 404
        )
        assert (
            admin.patch(
                f"{path}/{admin_id}/role",
                json={"role": "member"},
                headers=_headers(admin_csrf),
            ).status_code
            == 409
        )
        assert (
            admin.patch(
                f"{path}/{second_id}/role",
                json={"role": "administrator"},
                headers=_headers(admin_csrf),
            ).status_code
            == 200
        )
        assert (
            admin.patch(
                f"{path}/{admin_id}/role",
                json={"role": "member"},
                headers=_headers(admin_csrf),
            ).status_code
            == 200
        )
        assert admin.get(path).status_code == 404


def test_revocation_ends_session_and_restore_requires_new_sign_in(admin_site):
    app, _engine, workspace_id, admin_id, first_id, _second_id = admin_site
    with TestClient(app) as admin, TestClient(app) as member:
        admin_csrf = _login(admin, "admin-access@example.invalid")
        _login(member, "member-first@example.invalid")
        path = f"/api/v1/workspaces/{workspace_id}/members/{first_id}"
        assert admin.post(f"{path}/revoke", headers=_headers(admin_csrf)).status_code == 200
        assert member.get("/api/v1/auth/session").status_code == 401
        assert (
            admin.post(
                f"/api/v1/workspaces/{workspace_id}/members/{admin_id}/revoke",
                headers=_headers(admin_csrf),
            ).status_code
            == 409
        )
        assert admin.post(f"{path}/restore", headers=_headers(admin_csrf)).status_code == 200
        assert member.get("/api/v1/auth/session").status_code == 401
        assert _login(member, "member-first@example.invalid")
        assert member.get("/api/v1/auth/session").status_code == 200


def test_settings_versions_and_existing_expiry_are_preserved(admin_site):
    app, engine, workspace_id, admin_id, first_id, second_id = admin_site
    now = datetime.now(UTC)
    keys = KeyRing.from_settings(app.state.settings)
    with Session(engine) as session:
        existing = create_document(
            session,
            owner_id=first_id,
            workspace_id=workspace_id,
            source="Synthetic owner-only text",
            title=None,
            categories=set(),
            phone_region="PH",
            keys=keys,
            now=now,
        )
    with Session(engine) as session:
        for actor_id in (admin_id, second_id):
            with pytest.raises(DocumentNotFound):
                load_current_source(
                    session,
                    document_id=existing.version.document_id,
                    actor_id=actor_id,
                    keys=keys,
                    now=now,
                )
        assert (
            load_current_source(
                session,
                document_id=existing.version.document_id,
                actor_id=first_id,
                keys=keys,
                now=now,
            ).text
            == "Synthetic owner-only text"
        )
    with TestClient(app) as admin, TestClient(app) as member:
        csrf = _login(admin, "admin-access@example.invalid")
        _login(member, "member-first@example.invalid")
        path = f"/api/v1/workspaces/{workspace_id}/settings"
        initial = admin.get(path)
        assert initial.status_code == 200
        assert initial.json()["settings_version"] == 1
        assert member.get(path).status_code == 404
        changed = admin.put(
            path,
            json={
                "expected_version": 1,
                "content_retention_days": 3,
                "activity_retention_days": 60,
            },
            headers=_headers(csrf),
        )
        assert changed.status_code == 200
        assert changed.json()["settings_version"] == 2
        assert (
            admin.put(
                path,
                json={
                    "expected_version": 1,
                    "content_retention_days": 4,
                    "activity_retention_days": 60,
                },
                headers=_headers(csrf),
            ).status_code
            == 409
        )
    with Session(engine) as session:
        new = create_document(
            session,
            owner_id=first_id,
            workspace_id=workspace_id,
            source="Another synthetic source",
            title=None,
            categories=set(),
            phone_region="PH",
            keys=keys,
            now=now,
        )
    assert int((existing.expires_at - now).total_seconds()) == 7 * 86400
    assert int((new.expires_at - now).total_seconds()) == 3 * 86400


def test_http_source_read_rejects_cross_owner_document_and_revision_ids(admin_site):
    app, engine, workspace_id, _admin_id, first_id, second_id = admin_site
    keys = KeyRing.from_settings(app.state.settings)
    now = datetime.now(UTC)
    with Session(engine) as session:
        first = create_document(
            session,
            owner_id=first_id,
            workspace_id=workspace_id,
            source="Synthetic first owner secret",
            title=None,
            categories=set(),
            phone_region="PH",
            keys=keys,
            now=now,
        )
    with Session(engine) as session:
        second = create_document(
            session,
            owner_id=second_id,
            workspace_id=workspace_id,
            source="Synthetic second owner secret",
            title=None,
            categories=set(),
            phone_region="PH",
            keys=keys,
            now=now,
        )
    first_url = (
        f"/api/v1/documents/{first.version.document_id}/revisions/"
        f"{first.version.source_revision_id}/source"
    )
    swapped_url = (
        f"/api/v1/documents/{first.version.document_id}/revisions/"
        f"{second.version.source_revision_id}/source"
    )
    with (
        TestClient(app) as first_member,
        TestClient(app) as second_member,
        TestClient(app) as admin,
    ):
        assert first_member.get(first_url).status_code == 401
        with Session(engine) as session, pytest.raises(DocumentNotFound):
            add_manual_finding(
                session,
                document_id=first.version.document_id,
                actor_id=second_id,
                expected=first.version,
                span=SourceSpan(start=0, end=9),
                category=FindingCategory.PERSON,
                now=now,
            )
        _login(first_member, "member-first@example.invalid")
        _login(second_member, "member-second@example.invalid")
        _login(admin, "admin-access@example.invalid")
        owned = first_member.get(first_url)
        assert owned.status_code == 200
        assert owned.json()["text"] == "Synthetic first owner secret"
        assert owned.headers["Cache-Control"] == "no-store"
        assert first_member.get(swapped_url).status_code == 404
        for other in (second_member, admin):
            denied = other.get(first_url)
            assert denied.status_code == 404
            assert "Synthetic first owner secret" not in denied.text
        with Session(engine) as session, session.begin():
            membership = session.get(Membership, (workspace_id, first_id))
            membership.revoked_at = datetime.now(UTC)
        assert first_member.get(first_url).status_code == 401


def test_disabled_owner_and_direct_account_removal_cannot_expose_or_orphan_source(admin_site):
    app, engine, workspace_id, _admin_id, first_id, _second_id = admin_site
    keys = KeyRing.from_settings(app.state.settings)
    with Session(engine) as session:
        saved = create_document(
            session,
            owner_id=first_id,
            workspace_id=workspace_id,
            source="Synthetic account lifecycle source",
            title=None,
            categories=set(),
            phone_region="PH",
            keys=keys,
            now=datetime.now(UTC),
        )
    source_url = (
        f"/api/v1/documents/{saved.version.document_id}/revisions/"
        f"{saved.version.source_revision_id}/source"
    )
    with TestClient(app) as member:
        _login(member, "member-first@example.invalid")
        assert member.get(source_url).status_code == 200
        with Session(engine) as session, session.begin():
            session.get(User, first_id).disabled_at = datetime.now(UTC)
        assert member.get("/api/v1/auth/session").status_code == 401
        assert member.get(source_url).status_code == 401
    with Session(engine) as session:
        with pytest.raises(IntegrityError):
            session.execute(delete(User).where(User.id == first_id))
            session.commit()
        session.rollback()
    with Session(engine) as session:
        with pytest.raises(IntegrityError):
            session.execute(
                delete(Membership).where(
                    Membership.workspace_id == workspace_id,
                    Membership.user_id == first_id,
                )
            )
            session.commit()
        session.rollback()
    with Session(engine) as session:
        assert session.get(Document, saved.version.document_id).owner_id == first_id


class InvitationMailer:
    def __init__(self, *, fail: bool = False):
        self.sent = []
        self.fail = fail

    def send_invitation_code(self, recipient, code):
        if self.fail:
            raise RecoveryDeliveryError("Synthetic delivery failure")
        self.sent.append((recipient, code))

    def send_recovery_code(self, recipient, code):
        raise AssertionError("Invitation must use the invitation message")


def test_invitation_is_delivered_without_exposing_code_to_admin(admin_site):
    app, engine, workspace_id, _admin_id, _first_id, _second_id = admin_site
    with TestClient(app) as admin:
        csrf = _login(admin, "admin-access@example.invalid")
        path = f"/api/v1/workspaces/{workspace_id}/members/invitations"
        unavailable = admin.post(
            path,
            json={"email": "invited@example.invalid", "role": "member"},
            headers=_headers(csrf),
        )
        assert unavailable.status_code == 503
        mailer = InvitationMailer()
        app.state.recovery_mailer = mailer
        invited = admin.post(
            path,
            json={"email": "invited@example.invalid", "role": "member"},
            headers=_headers(csrf),
        )
        assert invited.status_code == 201
        assert invited.json()["role"] == "member"
        assert len(mailer.sent) == 1
        recipient, code = mailer.sent[0]
        assert recipient == "invited@example.invalid"
        assert code not in invited.text
        with Session(engine) as session:
            user = session.scalar(select(User).where(User.email == recipient))
            assert user is not None
        established = admin.post(
            "/api/v1/auth/recovery/complete",
            json={"email": recipient, "code": code, "new_password": PASSWORD},
            headers={"Origin": ORIGIN},
        )
        assert established.status_code == 204
    with TestClient(app) as invited_member:
        assert _login(invited_member, "invited@example.invalid")
        assert invited_member.get(f"/api/v1/workspaces/{workspace_id}/members").status_code == 404


def test_failed_invitation_delivery_rolls_back_new_account(admin_site):
    app, engine, workspace_id, _admin_id, _first_id, _second_id = admin_site
    app.state.recovery_mailer = InvitationMailer(fail=True)
    with TestClient(app) as admin:
        csrf = _login(admin, "admin-access@example.invalid")
        failed = admin.post(
            f"/api/v1/workspaces/{workspace_id}/members/invitations",
            json={"email": "invited@example.invalid", "role": "member"},
            headers=_headers(csrf),
        )
        assert failed.status_code == 503
    with Session(engine) as session:
        assert session.scalar(select(User).where(User.email == "invited@example.invalid")) is None
