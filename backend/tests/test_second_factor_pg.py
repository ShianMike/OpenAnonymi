"""Enrollment, code primitives, key rotation, changes and small-pool transactions."""

import base64
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.accounts.second_factor import (
    FactorError,
    change_factor,
    confirm_enrollment,
    start_enrollment,
)
from app.accounts.second_factor_codes import matching_step, normalize_code
from app.accounts.security import sign_in
from app.db.crypto import KeyRing, ProtectedValue
from app.db.models import Session as StoredSession
from app.db.rotate_keys import rotate_second_factors
from app.db.second_factor import UserBackupCode, UserSecondFactor
from tests.intake_support import ORIGIN, PASSWORD, _login
from tests.mail_support import Mailbox
from tests.second_factor_support import enroll, invalid_code, totp


@pytest.mark.parametrize(
    "timestamp,expected",
    [
        (59, "94287082"),
        (1111111109, "07081804"),
        (1111111111, "14050471"),
        (1234567890, "89005924"),
        (2000000000, "69279037"),
        (20000000000, "65353130"),
    ],
)
def test_rfc6238_sha1_vectors_in_the_real_six_digit_verifier(timestamp, expected):
    key = base64.b32encode(b"12345678901234567890").decode()
    now = datetime.fromtimestamp(timestamp, UTC)
    assert matching_step(key, expected[-6:], now, None) == timestamp // 30
    assert matching_step(key, expected[-6:], now, timestamp // 30) is None


def test_enrollment_secret_digest_storage_replay_and_current_session_survives(intake_site):
    owner, other, engine, _, user_id = intake_site
    _login(other, "intake-owner@example.invalid")
    owner.app.state.recovery_mailer = mailer = Mailbox()
    headers, key, backups = enroll(owner)
    assert len(backups) == len(set(backups)) == 10
    assert all(len(normalize_code(code)) == 16 for code in backups)
    assert other.get("/api/v1/auth/session").status_code == 401
    assert owner.get("/api/v1/auth/session").json()["second_factor_enabled"]
    assert owner.get("/api/v1/auth/second-factor").json()["backup_codes_remaining"] == 10
    assert (
        owner.post("/api/v1/auth/second-factor/enrollment/start", headers=headers).status_code
        == 422
    )
    with Session(engine) as session:
        factor = session.get(UserSecondFactor, user_id)
        assert key.encode() not in factor.secret_ciphertext
        assert (
            KeyRing.from_settings(owner.app.state.settings).decrypt_text(
                ProtectedValue(factor.secret_ciphertext, factor.key_id)
            )
            == key
        )
        rows = session.scalars(
            select(UserBackupCode).where(UserBackupCode.user_id == user_id)
        ).all()
        assert all(len(row.code_digest) == 32 and row.used_at is None for row in rows)
        assert all(row.code_digest not in [code.encode() for code in backups] for row in rows)
        assert (
            session.scalar(
                select(func.count())
                .select_from(StoredSession)
                .where(StoredSession.user_id == user_id, StoredSession.revoked_at.is_(None))
            )
            == 1
        )
    assert mailer.notices[0][1] == "second_factor_enabled"
    assert key not in mailer.notices[0][2] and backups[0] not in mailer.notices[0][2]


def test_pending_expiry_wrong_attempts_and_production_key_absence(intake_site):
    owner, _, engine, _, user_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    initial = owner.post("/api/v1/auth/second-factor/enrollment/start", headers=headers).json()
    assert "qr_svg_path" in initial and initial["qr_size"] > 20
    wrong = invalid_code(initial["manual_key"])
    assert (
        owner.post(
            "/api/v1/auth/second-factor/enrollment/confirm", headers=headers, json={"code": wrong}
        ).status_code
        == 400
    )
    with Session(engine) as session, session.begin():
        factor = session.get(UserSecondFactor, user_id)
        assert factor.failed_attempts == 1 and factor.status == "pending"
        factor.created_at = datetime.now(UTC) - timedelta(minutes=11)
    assert (
        owner.post(
            "/api/v1/auth/second-factor/enrollment/confirm",
            headers=headers,
            json={"code": totp(initial["manual_key"])},
        ).json()["code"]
        == "enrollment_expired"
    )
    owner.app.state.settings.active_key_id = None
    assert (
        owner.post("/api/v1/auth/second-factor/enrollment/start", headers=headers).status_code
        == 503
    )
    assert (
        owner.post(
            "/api/v1/auth/second-factor/enrollment/start", headers={"Origin": ORIGIN}
        ).status_code
        == 403
    )


def test_regeneration_requires_password_and_unused_totp_then_disable_accepts_backup(intake_site):
    owner, _, engine, _, user_id = intake_site
    _, key, old = enroll(owner)
    settings = owner.app.state.settings
    with Session(engine) as session:
        current = session.scalar(
            select(StoredSession).where(
                StoredSession.user_id == user_id, StoredSession.revoked_at.is_(None)
            )
        )
        session_id = current.id
    now = datetime.now(UTC) + timedelta(seconds=60)
    with pytest.raises(FactorError) as error:
        change_factor(engine, settings, user_id, session_id, PASSWORD, old[0], now, disable=False)
    assert error.value.code == "invalid_second_factor_code"
    with pytest.raises(FactorError) as error:
        change_factor(
            engine,
            settings,
            user_id,
            session_id,
            "wrong-password",
            totp(key, now),
            now,
            disable=False,
        )
    assert error.value.code == "incorrect_password"
    new, _ = change_factor(
        engine, settings, user_id, session_id, PASSWORD, totp(key, now), now, disable=False
    )
    assert len(new) == 10 and not set(new) & set(old)
    with pytest.raises(FactorError):
        change_factor(engine, settings, user_id, session_id, PASSWORD, old[0], now, disable=True)
    assert (
        change_factor(
            engine,
            settings,
            user_id,
            session_id,
            PASSWORD,
            new[0].lower().replace("-", " "),
            now,
            disable=True,
        )[0]
        == []
    )
    with Session(engine) as session:
        assert session.get(UserSecondFactor, user_id) is None
        assert (
            session.scalar(
                select(func.count())
                .select_from(UserBackupCode)
                .where(UserBackupCode.user_id == user_id)
            )
            == 0
        )


def test_factor_rotation_and_single_connection_pool_are_operational(intake_site):
    owner, _, _, _, user_id = intake_site
    settings = owner.app.state.settings
    limited = create_engine(
        settings.database_url, pool_size=1, max_overflow=0, pool_timeout=2, hide_parameters=True
    )
    try:
        now = datetime.now(UTC)
        with Session(limited) as session:
            issued = sign_in(
                session, email="intake-owner@example.invalid", password=PASSWORD, now=now
            )
        started = start_enrollment(limited, settings, user_id, issued.identity.session_id, now)
        codes, _ = confirm_enrollment(
            limited,
            settings,
            user_id,
            issued.identity.session_id,
            totp(started.manual_key, now),
            now,
        )
        assert len(codes) == 10
        old_key = settings.content_keys[settings.active_key_id].get_secret_value().encode()
        next_key = Fernet.generate_key()
        rotating = KeyRing("next", {settings.active_key_id: old_key, "next": next_key})
        with Session(limited) as session, session.begin():
            session.get(UserSecondFactor, user_id).failed_attempts = 100
            assert rotate_second_factors(session, rotating) == 1
            row = session.get(UserSecondFactor, user_id)
            assert row.failed_attempts == 100
            assert (
                KeyRing("next", {"next": next_key}).decrypt_text(
                    ProtectedValue(row.secret_ciphertext, row.key_id)
                )
                == started.manual_key
            )
    finally:
        limited.dispose()
