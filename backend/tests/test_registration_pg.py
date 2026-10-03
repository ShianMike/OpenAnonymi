"""Actual API code proof, expiry, password binding and concurrency on PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.accounts.limits import AttemptLimiter
from app.accounts.signup import (
    AccountUnavailable,
    digest,
    request_registration,
    verify_registration,
)
from app.cleanup.service import purge_unavailable_content
from app.db.crypto import KeyRing, ProtectedValue
from app.db.durable import AttemptEvent
from app.db.email_verification import PendingRegistration
from app.db.models import Membership, User, Workspace
from app.db.rotate_keys import rotate_pending_registrations
from tests.intake_support import ORIGIN, PASSWORD
from tests.mail_support import Mailbox


@pytest.fixture
def registration_site(intake_site):
    client, _, engine, _, _ = intake_site
    settings = client.app.state.settings
    settings.email_allow_test_domains = True
    mailer = Mailbox()
    client.app.state.recovery_mailer = mailer
    email = f"new-{uuid4().hex}@openanonymi.test"
    try:
        yield client, engine, settings, mailer, email
    finally:
        with Session(engine) as session, session.begin():
            user = session.scalar(select(User).where(User.email == email))
            if user:
                workspace_ids = session.scalars(
                    select(Membership.workspace_id).where(Membership.user_id == user.id)
                ).all()
                session.execute(delete(Membership).where(Membership.user_id == user.id))
                session.execute(delete(Workspace).where(Workspace.id.in_(workspace_ids)))
                session.delete(user)
            session.execute(
                delete(PendingRegistration).where(PendingRegistration.canonical_email == email)
            )


def request(client, email, *, password=PASSWORD):
    return client.post(
        "/api/v1/auth/sign-up",
        headers={"Origin": ORIGIN},
        json={"email": email, "password": password, "workspace_name": "Protected pending name"},
    )


def verify(client, email, code, *, password=PASSWORD):
    return client.post(
        "/api/v1/auth/sign-up/verify",
        headers={"Origin": ORIGIN},
        json={"email": email, "code": code, "password": password},
    )


def test_no_user_until_proof_wrong_expired_replay_and_protected_storage(registration_site):
    client, engine, settings, mailer, email = registration_site
    response = request(client, email)
    assert response.status_code == 202 and "set-cookie" not in response.headers
    code = mailer.latest(email)
    assert code not in response.text
    malformed = verify(client, email, "private-code-canary-☃")
    assert malformed.status_code == 422 and "private-code-canary" not in malformed.text
    with Session(engine) as session:
        assert session.scalar(select(User).where(User.email == email)) is None
        row = session.scalar(
            select(PendingRegistration).where(PendingRegistration.canonical_email == email)
        )
        assert row.code_digest != code.encode() and len(row.code_digest) == 32
        assert row.password_hash.startswith("$argon2") and PASSWORD not in row.password_hash
        assert b"Protected pending name" not in row.workspace_name_ciphertext
        assert (
            KeyRing.from_settings(settings).decrypt_text(
                ProtectedValue(row.workspace_name_ciphertext, row.key_id)
            )
            == "Protected pending name"
        )
        id_ = row.id
    wrong = verify(client, email, "x" * 32)
    mismatch = verify(client, email, code, password="different-owner-password")
    assert wrong.status_code == mismatch.status_code == 400 and wrong.json() == mismatch.json()
    with Session(engine) as session, session.begin():
        row = session.get(PendingRegistration, id_)
        row.created_at = datetime.now(UTC) - timedelta(minutes=20)
        row.expires_at = datetime.now(UTC) - timedelta(minutes=5)
    assert verify(client, email, code).json() == wrong.json()
    with Session(engine) as session, session.begin():
        row = session.get(PendingRegistration, id_)
        row.expires_at = datetime.now(UTC) + timedelta(minutes=15)
    created = verify(client, email, f" {code} ")
    assert created.status_code == 201 and created.json()["email_verified"]
    assert "httponly" in created.headers["set-cookie"].lower()
    assert client.get("/api/v1/auth/session").json()["email_verified"]
    assert verify(client, email, code).status_code == 400
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(PendingRegistration)
                .where(PendingRegistration.canonical_email == email)
            )
            == 0
        )
        assert (
            session.scalar(select(func.count()).select_from(User).where(User.email == email)) == 1
        )


def test_later_request_never_replaces_an_owners_password_or_code(registration_site):
    client, engine, _, mailer, email = registration_site
    assert request(client, email).status_code == 202
    first = mailer.latest(email)
    assert request(client, email, password="third-party-password").status_code == 202
    second = mailer.latest(email)
    assert first != second
    assert verify(client, email, first, password="third-party-password").status_code == 400
    assert verify(client, email, second).status_code == 400
    for _ in range(3):
        assert verify(client, email, "x" * 32).status_code == 400
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(PendingRegistration)
                .where(PendingRegistration.canonical_email == email)
            )
            == 2
        )
    assert verify(client, email, first).status_code == 201


def test_existing_and_exhausted_addresses_get_identical_receipts_and_no_extra_mail(
    registration_site,
):
    client, engine, settings, mailer, email = registration_site
    for _ in range(3):
        delivery = request_registration(
            engine,
            settings=settings,
            email=email,
            password=PASSWORD,
            workspace_name="First",
            now=datetime.now(UTC),
        )
        assert delivery is not None
    assert (
        request_registration(
            engine,
            settings=settings,
            email=email,
            password=PASSWORD,
            workspace_name="Fourth",
            now=datetime.now(UTC),
        )
        is None
    )
    exhausted = request(client, email)
    assert exhausted.status_code == 202 and mailer.messages == []
    # The fixture's existing legacy address remains accepted for sign-in and is not created again.
    settings.email_allow_test_domains = False
    settings.email_check_deliverability = False
    with Session(engine) as session, session.begin():
        user = session.scalar(select(User).where(User.email == "intake-owner@example.invalid"))
        original_email = user.email
        user.email = "owner@openanonymi.vercel.app"
    try:
        existing = request(client, "owner@openanonymi.vercel.app")
        assert existing.status_code == 202 and existing.json() == exhausted.json()
        assert mailer.messages == []
    finally:
        with Session(engine) as session, session.begin():
            session.scalar(
                select(User).where(User.email == "owner@openanonymi.vercel.app")
            ).email = original_email


def test_concurrent_valid_codes_create_exactly_one_workspace_without_deadlock(registration_site):
    _, engine, settings, _, email = registration_site
    now = datetime.now(UTC)
    deliveries = [
        request_registration(
            engine,
            settings=settings,
            email=email,
            password=PASSWORD,
            workspace_name="Concurrent",
            now=now,
        )
        for _ in range(2)
    ]

    def finish(delivery):
        try:
            return verify_registration(
                engine,
                settings=settings,
                email=email,
                code=delivery.code,
                password=PASSWORD,
                now=now,
            ).identity.user_id
        except (AccountUnavailable, ValueError):
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(finish, deliveries))
    assert sum(result is not None for result in results) == 1
    with Session(engine) as session:
        user = session.scalar(select(User).where(User.email == email))
        assert (
            session.scalar(
                select(func.count()).select_from(Membership).where(Membership.user_id == user.id)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(PendingRegistration)
                .where(PendingRegistration.canonical_email == email)
            )
            == 0
        )


def test_unconfigured_registration_is_unavailable_without_creating_rows(registration_site):
    client, engine, _, _, email = registration_site
    client.app.state.recovery_mailer = None
    response = request(client, email)
    assert response.status_code == 503 and response.json()["code"] == "registration_unavailable"
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(PendingRegistration)
                .where(PendingRegistration.canonical_email == email)
            )
            == 0
        )


def test_pending_name_survives_key_rotation_and_expired_rows_are_purged(registration_site):
    client, engine, settings, mailer, email = registration_site
    assert request(client, email).status_code == 202
    first_code = mailer.latest(email)
    assert request(client, email).status_code == 202
    fresh_code = mailer.latest(email)
    now = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        rows = session.scalars(
            select(PendingRegistration).where(PendingRegistration.canonical_email == email)
        ).all()
        for row in rows:
            if row.code_digest == digest(first_code):
                row.created_at = now - timedelta(minutes=20)
                row.expires_at = now - timedelta(minutes=5)
    old_key = settings.content_keys[settings.active_key_id].get_secret_value().encode()
    next_key = Fernet.generate_key()
    rotating = KeyRing("rotated", {settings.active_key_id: old_key, "rotated": next_key})
    with Session(engine) as session, session.begin():
        assert rotate_pending_registrations(session, rotating) == 2
        assert rotate_pending_registrations(session, rotating) == 0
    settings.active_key_id, settings.content_keys = (
        "rotated",
        {"rotated": SecretStr(next_key.decode())},
    )
    assert purge_unavailable_content(engine, now=now).documents_purged == 0
    with Session(engine) as session:
        row = session.scalar(
            select(PendingRegistration).where(PendingRegistration.canonical_email == email)
        )
        assert row.key_id == "rotated"
        assert (
            KeyRing.from_settings(settings).decrypt_text(
                ProtectedValue(row.workspace_name_ciphertext, row.key_id)
            )
            == "Protected pending name"
        )
    assert verify(client, email, first_code).status_code == 400
    assert verify(client, email, fresh_code).status_code == 201


def test_signup_address_budget_admits_new_owner_after_10001_other_addresses(registration_site):
    client, engine, settings, mailer, email = registration_site
    limiter = AttemptLimiter(
        engine,
        settings,
        scope="registration_address",
        maximum=3,
        window_seconds=3600,
        network_scope=False,
    )
    now, prefix = datetime.now(UTC), uuid4().hex
    owned_ids = [uuid4() for _ in range(10001)]
    try:
        with Session(engine) as session, session.begin():
            session.execute(
                insert(AttemptEvent),
                [
                    {
                        "id": row_id,
                        "scope": limiter.scope,
                        "subject_hmac": limiter._digest(f"flood-{prefix}-{i}@openanonymi.test"),
                        "attempted_at": now,
                    }
                    for i, row_id in enumerate(owned_ids)
                ],
            )
        assert request(client, email).status_code == 202
        assert mailer.latest(email)
        with Session(engine) as session:
            assert (
                session.scalar(
                    select(PendingRegistration.id).where(
                        PendingRegistration.canonical_email == email
                    )
                )
                is not None
            )
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(AttemptEvent).where(AttemptEvent.id.in_(owned_ids)))
