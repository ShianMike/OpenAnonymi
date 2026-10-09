"""Password proof yields a bounded HttpOnly challenge before any full session."""

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.second_factor import (
    ENROLLMENT_TTL,
    FactorError,
    activate_locked,
    consume_code,
    locked_user,
    requires_factor,
    start_locked_enrollment,
    take_code_budget,
)
from app.accounts.security import IssuedSession, _digest, issue_session
from app.accounts.security_notices import SecurityNotice
from app.config import Settings
from app.db.crypto import KeyRing
from app.db.models import Membership, User
from app.db.second_factor import AuthChallenge, UserSecondFactor

CHALLENGE_NAME = "openanonymi_challenge"
CHALLENGE_PATH = "/api/v1/auth"
CHALLENGE_TTL = timedelta(minutes=5)


@dataclass(frozen=True)
class IssuedChallenge:
    token: str
    status: str
    expires_at: datetime


def password_step(
    session: Session, user: User, now: datetime, user_agent: str
) -> IssuedSession | IssuedChallenge:
    factor = session.get(UserSecondFactor, user.id)
    if factor is not None and factor.status == "active":
        kind, status = "second_factor", "second_factor_required"
    elif user.second_factor_reenroll_required or requires_factor(session, user.id):
        kind, status = "enrollment", "enrollment_required"
    else:
        return issue_session(session, user=user, now=now, user_agent=user_agent)
    token, expires = secrets.token_urlsafe(32), now + CHALLENGE_TTL
    session.add(
        AuthChallenge(
            id=uuid4(),
            user_id=user.id,
            token_digest=_digest(token),
            kind=kind,
            failed_attempts=0,
            created_at=now,
            expires_at=expires,
        )
    )
    return IssuedChallenge(token, status, expires)


def _challenge_statement(token: str | None, kind: str, now: datetime):
    if token is None or len(token) != 43 or not token.isascii():
        raise FactorError(
            401,
            "challenge_expired",
            "Sign in again; the verification step expired.",
            clear_challenge=True,
        )
    return select(AuthChallenge).join(User, User.id == AuthChallenge.user_id).where(
        AuthChallenge.token_digest == _digest(token), AuthChallenge.kind == kind,
        AuthChallenge.consumed_at.is_(None), AuthChallenge.expires_at > now,
        AuthChallenge.failed_attempts < 5, User.disabled_at.is_(None),
        select(Membership.user_id).where(
            Membership.user_id == AuthChallenge.user_id, Membership.revoked_at.is_(None),
        ).exists(),
    )


def _current_challenge(session, token, kind, now, *, lock=False):
    statement = _challenge_statement(token, kind, now)
    if lock:
        statement = statement.with_for_update(of=AuthChallenge)
    row = session.scalar(statement.execution_options(populate_existing=True))
    if row is None:
        raise FactorError(
            401,
            "challenge_expired",
            "Sign in again; the verification step expired.",
            clear_challenge=True,
        )
    return row


def locked_challenge(
    session: Session, token: str | None, kind: str, now: datetime
) -> tuple[User, AuthChallenge]:
    row = _current_challenge(session, token, kind, now)
    user = locked_user(session, row.user_id, now)
    return user, _current_challenge(session, token, kind, now, lock=True)


def validate_challenge(engine, token, kind, *, expires_at=None):
    """Fresh read of the actual pre-session capability; never lock a caller's rows."""
    with Session(engine) as session:
        row = _current_challenge(session, token, kind, datetime.now(UTC))
        if expires_at is not None and row.expires_at != expires_at:
            raise FactorError(401, "challenge_expired", "Sign in again; account access changed.", clear_challenge=True)
        return row.user_id


def finish_password_step(
    engine: Engine, settings: Settings, token: str | None, code: str, now: datetime, user_agent: str,
    *, reauthorize: Callable[[], object] | None = None,
) -> tuple[IssuedSession, list[SecurityNotice]]:
    keys = KeyRing.from_settings(settings)
    error, issued, notices = None, None, []
    with Session(engine) as session, session.begin():
        user, challenge = locked_challenge(session, token, "second_factor", now)
        if reauthorize is not None:
            reauthorize()
        factor = session.get(UserSecondFactor, user.id)
        if factor is None or factor.status != "active":
            error = FactorError(
                401,
                "challenge_expired",
                "Sign in again; account security changed.",
                clear_challenge=True,
            )
        else:
            error = take_code_budget(session, engine, settings, factor, user, now)
            if error is None:
                method = consume_code(session, factor, code, keys, now, allow_backup=True)
                if method is None:
                    challenge.failed_attempts += 1
                    locked = factor.failed_attempts >= 100
                    clear = locked or challenge.failed_attempts >= 5
                    if clear:
                        challenge.consumed_at = now
                    error = FactorError(
                        429 if locked else 400,
                        "second_factor_locked" if locked else "invalid_second_factor_code",
                        "Authenticator attempts are locked. Recover your password or request a reset."
                        if locked
                        else "That code is invalid or already used.",
                        clear_challenge=clear,
                    )
                else:
                    challenge.consumed_at = now
                    issued = issue_session(
                        session, user=user, now=now, user_agent=user_agent, auth_method=method
                    )
                    if method == "password_backup_code":
                        notices.append(SecurityNotice(user.email, "backup_code_used", now))
        session.flush()
        if reauthorize is not None:
            reauthorize()
    if error:
        raise error
    return issued, notices


def start_forced_enrollment(
    engine: Engine, settings: Settings, token: str | None, now: datetime,
    *, reauthorize: Callable[[], object] | None = None,
):
    keys = KeyRing.from_settings(settings)
    with Session(engine) as session, session.begin():
        user, _ = locked_challenge(session, token, "enrollment", now)
        if reauthorize is not None:
            reauthorize()
        result = start_locked_enrollment(session, user, keys, now)
        session.flush()
        if reauthorize is not None:
            reauthorize()
        return result


def finish_forced_enrollment(
    engine: Engine, settings: Settings, token: str | None, code: str, now: datetime, user_agent: str,
    *, reauthorize: Callable[[], object] | None = None,
) -> tuple[IssuedSession, list[str], list[SecurityNotice]]:
    keys = KeyRing.from_settings(settings)
    error, issued, codes, notices = None, None, [], []
    with Session(engine) as session, session.begin():
        user, challenge = locked_challenge(session, token, "enrollment", now)
        if reauthorize is not None:
            reauthorize()
        factor = session.get(UserSecondFactor, user.id)
        if (
            factor is None
            or factor.status != "pending"
            or factor.created_at + ENROLLMENT_TTL <= now
        ):
            error = FactorError(
                400,
                "enrollment_expired",
                "Start authenticator setup again; the enrollment expired.",
            )
        else:
            error = take_code_budget(session, engine, settings, factor, user, now)
            if error is None:
                if consume_code(session, factor, code, keys, now, allow_backup=False) is None:
                    challenge.failed_attempts += 1
                    locked = factor.failed_attempts >= 100
                    clear = challenge.failed_attempts >= 5 or locked
                    if clear:
                        challenge.consumed_at = now
                    error = FactorError(
                        429 if locked else 400,
                        "second_factor_locked" if locked else "invalid_second_factor_code",
                        "Authenticator attempts are locked. Recover your password or request a reset."
                        if locked
                        else "That authenticator code is invalid or already used.",
                        clear_challenge=clear,
                    )
                else:
                    codes = activate_locked(session, user, factor, now, None)
                    challenge.consumed_at = now
                    issued = issue_session(
                        session, user=user, now=now, user_agent=user_agent, auth_method="enrollment"
                    )
                    notices.append(SecurityNotice(user.email, "second_factor_enabled", now))
        session.flush()
        if reauthorize is not None:
            reauthorize()
    if error:
        raise error
    return issued, codes, notices
