"""No session before factor proof; replay, challenges, budgets and recovery stay durable."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.accounts.challenges import (
    finish_forced_enrollment,
    finish_password_step,
    start_forced_enrollment,
)
from app.accounts.recovery import complete_recovery, request_recovery
from app.accounts.reset_second_factor import reset_factor
from app.accounts.second_factor import FactorError
from app.accounts.security import sign_in
from app.config import Settings
from app.db.models import Session as StoredSession
from app.db.second_factor import AuthChallenge, UserSecondFactor
from app.factory import create_app
from tests.intake_support import ORIGIN, PASSWORD
from tests.mail_support import Mailbox
from tests.second_factor_support import enroll, invalid_code, password_step, totp


def test_password_alone_never_issues_session_backup_is_single_use_and_cookie_clears(intake_site):
    owner, other, engine, _, user_id = intake_site
    _, key, backups = enroll(owner)
    with Session(engine) as session:
        used_step = session.get(UserSecondFactor, user_id).last_used_step
    assert used_step is not None
    consumed_code = totp(key, datetime.fromtimestamp(used_step * 30, UTC))
    response = password_step(other)
    cookie = next(
        value
        for value in response.headers.get_list("set-cookie")
        if value.startswith("openanonymi_challenge=")
    )
    assert "HttpOnly" in cookie and "Path=/api/v1/auth" in cookie and "Max-Age=300" in cookie
    assert "openanonymi_challenge" not in response.text
    assert other.get("/api/v1/auth/session").status_code == 401
    denied = other.post(
        "/api/v1/auth/sign-in/second-factor", headers={"Origin": ORIGIN}, json={"code": consumed_code}
    )
    assert denied.status_code == 400  # enrollment already consumed this step
    finished = other.post(
        "/api/v1/auth/sign-in/second-factor",
        headers={"Origin": ORIGIN},
        json={"code": backups[0].lower().replace("-", " ")},
    )
    assert finished.status_code == 200 and finished.json()["second_factor_enabled"]
    assert (
        "openanonymi_challenge=" in finished.headers["set-cookie"]
        and "Max-Age=0" in finished.headers["set-cookie"]
    )
    assert other.get("/api/v1/auth/session").status_code == 200
    password_step(other)
    replay = other.post(
        "/api/v1/auth/sign-in/second-factor", headers={"Origin": ORIGIN}, json={"code": backups[0]}
    )
    assert replay.status_code == 400 and "csrf_token" not in replay.json()
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(StoredSession)
                .where(StoredSession.user_id == user_id, StoredSession.revoked_at.is_(None))
            )
            == 2
        )


def test_five_bad_codes_consume_challenge_and_expiry_origin_are_enforced(intake_site):
    owner, other, engine, _, _ = intake_site
    _, key, backups = enroll(owner)
    password_step(other)
    assert (
        other.post(
            "/api/v1/auth/sign-in/second-factor",
            headers={"Origin": "https://foreign.invalid"},
            json={"code": backups[0]},
        ).status_code
        == 403
    )
    for _ in range(5):
        failed = other.post(
            "/api/v1/auth/sign-in/second-factor",
            headers={"Origin": ORIGIN},
            json={"code": invalid_code(key)},
        )
        assert failed.status_code == 400
    assert "Max-Age=0" in failed.headers["set-cookie"]
    assert (
        other.post(
            "/api/v1/auth/sign-in/second-factor",
            headers={"Origin": ORIGIN},
            json={"code": backups[0]},
        ).status_code
        == 401
    )
    password_step(other)
    with Session(engine) as session, session.begin():
        challenge = session.scalar(
            select(AuthChallenge)
            .where(AuthChallenge.consumed_at.is_(None))
            .order_by(AuthChallenge.created_at.desc())
        )
        challenge.created_at, challenge.expires_at = (
            datetime.now(UTC) - timedelta(minutes=6),
            datetime.now(UTC) - timedelta(seconds=1),
        )
    expired = other.post(
        "/api/v1/auth/sign-in/second-factor", headers={"Origin": ORIGIN}, json={"code": backups[0]}
    )
    assert expired.status_code == 401 and "Max-Age=0" in expired.headers["set-cookie"]


def test_concurrent_independent_instances_accept_one_totp_step(intake_site):
    owner, _, engine, _, _ = intake_site
    _, key, _ = enroll(owner)
    settings = owner.app.state.settings
    second = create_engine(settings.database_url, hide_parameters=True)
    now = datetime.now(UTC) + timedelta(seconds=60)
    challenges = []
    for database in (engine, second):
        with Session(database) as session:
            challenges.append(
                sign_in(session, email="intake-owner@example.invalid", password=PASSWORD, now=now)
            )

    def finish(index):
        try:
            result, _ = finish_password_step(
                (engine, second)[index],
                settings,
                challenges[index].token,
                totp(key, now),
                now,
                "Chrome/100 Windows",
            )
            return result.identity.session_id
        except FactorError:
            return None

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(finish, range(2)))
        assert sum(value is not None for value in results) == 1
    finally:
        second.dispose()


def test_short_budget_notice_once_per_day_daily_budget_and_hundred_failure_lock(intake_site):
    owner, _, engine, _, user_id = intake_site
    _, key, backups = enroll(owner)
    settings, base = owner.app.state.settings, datetime.now(UTC) + timedelta(days=1)
    # Actual failures across fresh challenges and sliding windows, without clearing
    # persistent events or bypassing either budget to reach the 100-failure lock.
    for index in range(100):
        now = base + timedelta(days=index // 30, seconds=((index % 30) // 5) * 901)
        if index % 5 == 0:
            with Session(engine) as session:
                challenge = sign_in(
                    session, email="intake-owner@example.invalid", password=PASSWORD, now=now
                )
        with pytest.raises(FactorError) as failure:
            finish_password_step(engine, settings, challenge.token, invalid_code(key, now), now, "")
        assert failure.value.code in ("invalid_second_factor_code", "second_factor_locked")
    with Session(engine) as session:
        assert session.get(UserSecondFactor, user_id).failed_attempts == 100
    with Session(engine) as session:
        challenge = sign_in(
            session, email="intake-owner@example.invalid", password=PASSWORD, now=now
        )
    with pytest.raises(FactorError) as locked:
        finish_password_step(engine, settings, challenge.token, backups[0], now, "")
    assert locked.value.code == "second_factor_locked"
    mailer = Mailbox()
    with Session(engine) as session:
        request_recovery(session, email="intake-owner@example.invalid", now=now, mailer=mailer)
    with Session(engine) as session:
        complete_recovery(
            session,
            email="intake-owner@example.invalid",
            code=mailer.latest("intake-owner@example.invalid"),
            new_password="recovered-long-password",
            now=now,
        )
    with Session(engine) as session:
        factor = session.get(UserSecondFactor, user_id)
        assert factor.status == "active" and factor.failed_attempts == 0
        assert (
            session.scalar(
                select(func.count())
                .select_from(StoredSession)
                .where(StoredSession.user_id == user_id, StoredSession.revoked_at.is_(None))
            )
            == 0
        )


def test_limiter_denials_survive_restart_and_notice_is_once_in_utc_day(intake_site):
    owner, _, engine, _, user_id = intake_site
    _, key, backups = enroll(owner)
    settings, now = owner.app.state.settings, datetime.now(UTC)
    # Enrollment used one of ten attempts in this window.
    notices = []
    for _ in range(2):
        with Session(engine) as session:
            challenge = sign_in(
                session, email="intake-owner@example.invalid", password=PASSWORD, now=now
            )
        for _ in range(5):
            with pytest.raises(FactorError) as failure:
                finish_password_step(
                    engine, settings, challenge.token, invalid_code(key, now), now, ""
                )
            if failure.value.notice:
                notices.append(failure.value.notice)
    assert len(notices) == 1 and notices[0].event == "second_factor_attempts_exceeded"
    second = create_engine(settings.database_url, hide_parameters=True)
    try:
        with Session(second) as session:
            challenge = sign_in(
                session, email="intake-owner@example.invalid", password=PASSWORD, now=now
            )
        with pytest.raises(FactorError) as limited:
            finish_password_step(second, settings, challenge.token, backups[0], now, "")
        assert limited.value.code == "second_factor_limited"
        # The first denial above already persisted its notice timestamp.
        assert limited.value.notice is None
        with Session(second) as session:
            assert session.get(UserSecondFactor, user_id).last_limit_notice_at is not None
        reset_factor(second, user_id, now)
        with Session(second) as session:
            forced = sign_in(
                session, email="intake-owner@example.invalid", password=PASSWORD, now=now
            )
        restarted = start_forced_enrollment(second, settings, forced.token, now)
        with pytest.raises(FactorError) as limited_after_reset:
            finish_forced_enrollment(
                second, settings, forced.token, invalid_code(restarted.manual_key, now), now, ""
            )
        assert (
            limited_after_reset.value.code == "second_factor_limited"
            and limited_after_reset.value.notice is None
        )
    finally:
        second.dispose()


def test_daily_budget_survives_a_new_engine_after_short_window_expires(intake_site):
    owner, _, engine, _, user_id = intake_site
    _, key, backups = enroll(owner)
    settings, base = owner.app.state.settings, datetime.now(UTC) + timedelta(days=1)
    for index in range(30):
        now = base + timedelta(seconds=(index // 5) * 901)
        if index % 5 == 0:
            with Session(engine) as session:
                challenge = sign_in(
                    session, email="intake-owner@example.invalid", password=PASSWORD, now=now
                )
        with pytest.raises(FactorError) as failure:
            finish_password_step(engine, settings, challenge.token, invalid_code(key, now), now, "")
        assert failure.value.code == "invalid_second_factor_code"
    second = create_engine(settings.database_url, hide_parameters=True)
    try:
        now += timedelta(seconds=901)
        with Session(second) as session:
            challenge = sign_in(
                session, email="intake-owner@example.invalid", password=PASSWORD, now=now
            )
        with pytest.raises(FactorError) as denied:
            finish_password_step(second, settings, challenge.token, backups[0], now, "")
        assert denied.value.code == "second_factor_limited" and denied.value.notice is None
        with Session(second) as session:
            assert session.get(UserSecondFactor, user_id).failed_attempts == 30
    finally:
        second.dispose()


def test_real_production_challenge_and_session_cookie_attributes_match(intake_site):
    owner, _, engine, _, _ = intake_site
    _, _, backups = enroll(owner)
    origin = "https://frontend.example.invalid"
    current = owner.app.state.settings
    settings = Settings(
        database_url=current.database_url,
        allowed_origins=[origin],
        environment="production",
        attempt_subject_key=current.content_keys[current.active_key_id],
        active_key_id=current.active_key_id,
        content_keys=current.content_keys,
        _env_file=None,
    )
    with TestClient(
        create_app(settings, engine=engine), base_url="https://backend.example.invalid"
    ) as client:
        password = client.post(
            "/api/v1/auth/sign-in",
            headers={"Origin": origin},
            json={"email": "intake-owner@example.invalid", "password": PASSWORD},
        )
        assert password.status_code == 202 and client.get("/api/v1/auth/session").status_code == 401
        challenge = next(
            value
            for value in password.headers.get_list("set-cookie")
            if value.startswith("openanonymi_challenge=")
        )
        assert all(
            value in challenge
            for value in (
                "HttpOnly",
                "Secure",
                "SameSite=None",
                "Partitioned",
                "Path=/api/v1/auth",
                "Max-Age=300",
            )
        )
        finished = client.post(
            "/api/v1/auth/sign-in/second-factor",
            headers={"Origin": origin},
            json={"code": backups[0]},
        )
        assert finished.status_code == 200
        cookies = finished.headers.get_list("set-cookie")
        issued = next(value for value in cookies if value.startswith("openanonymi_session="))
        cleared = next(value for value in cookies if value.startswith("openanonymi_challenge="))
        assert all(
            value in issued
            for value in (
                "HttpOnly",
                "Secure",
                "SameSite=None",
                "Partitioned",
                "Path=/api/v1;",
                "Max-Age=43200",
            )
        )
        assert all(
            value in cleared
            for value in (
                "Max-Age=0",
                "Path=/api/v1/auth",
                "Secure",
                "SameSite=None",
                "Partitioned",
            )
        )
