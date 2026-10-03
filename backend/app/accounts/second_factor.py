"""Account-locked authenticator changes, shared budgets and durable replay guards."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.limits import AttemptLimiter
from app.accounts.second_factor_codes import (
    backup_digest,
    matching_step,
    new_backup_codes,
    new_manual_key,
    normalize_code,
    qr_path,
)
from app.accounts.security import _verify_password
from app.accounts.security_notices import SecurityNotice
from app.config import Settings
from app.db.crypto import KeyRing, ProtectedValue
from app.db.models import Membership, User, Workspace
from app.db.models import Session as StoredSession
from app.db.second_factor import AuthChallenge, UserBackupCode, UserSecondFactor
from app.workspace.activity import record_event

ENROLLMENT_TTL = timedelta(minutes=10)


class FactorError(RuntimeError):
    def __init__(self, status: int, code: str, message: str, *, clear_challenge=False, notice=None):
        self.status, self.code, self.message = status, code, message
        self.clear_challenge, self.notice = clear_challenge, notice
        super().__init__(message)


@dataclass(frozen=True)
class Enrollment:
    qr_svg_path: str
    qr_size: int
    manual_key: str
    expires_at: datetime


def locked_user(
    session: Session, user_id: UUID, now: datetime, session_id: UUID | None = None
) -> User:
    user = session.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if user is None or user.disabled_at is not None:
        raise FactorError(401, "sign_in_required", "Sign in to continue.", clear_challenge=True)
    if session_id is not None:
        record = session.get(StoredSession, session_id, populate_existing=True)
        if (
            record is None
            or record.user_id != user.id
            or record.revoked_at is not None
            or record.expires_at <= now
        ):
            raise FactorError(401, "sign_in_required", "Sign in to continue.")
    return user


def security_activity(
    session: Session, user_id: UUID, event: str, now: datetime, *, actor_id: UUID | None = None
):
    workspaces = session.scalars(
        select(Membership.workspace_id).where(
            Membership.user_id == user_id, Membership.revoked_at.is_(None)
        )
    ).all()
    for workspace_id in workspaces:
        record_event(
            session,
            workspace_id=workspace_id,
            actor_id=actor_id or user_id,
            document_id=None,
            event_code=event,
            now=now,
        )


def requires_factor(session: Session, user_id: UUID) -> bool:
    return bool(
        session.scalar(
            select(Workspace.id)
            .join(Membership, Membership.workspace_id == Workspace.id)
            .where(
                Membership.user_id == user_id,
                Membership.revoked_at.is_(None),
                Workspace.require_second_factor.is_(True),
            )
            .limit(1)
        )
    )


def take_code_budget(
    session: Session,
    engine: Engine,
    settings: Settings,
    factor: UserSecondFactor,
    user: User,
    now: datetime,
) -> FactorError | None:
    if factor.failed_attempts >= 100:
        return FactorError(
            429,
            "second_factor_locked",
            "Authenticator attempts are locked. Recover your password or contact an administrator for a reset.",
            clear_challenge=True,
        )
    short = AttemptLimiter(
        engine, settings, scope="second_factor", maximum=10, window_seconds=900, network_scope=False
    )
    daily = AttemptLimiter(
        engine,
        settings,
        scope="second_factor_daily",
        maximum=30,
        window_seconds=86400,
        network_scope=False,
    )
    if not short.take(str(user.id), now=now, session=session):
        notice = None
        notice_budget = AttemptLimiter(
            engine,
            settings,
            scope="second_factor_notice",
            maximum=1,
            window_seconds=86400,
            network_scope=False,
        )
        # A UTC-day subject keeps the notice bound across factor disable/reset
        # and pending enrollment cleanup, which can delete the factor row.
        if notice_budget.take(
            f"{user.id}:{now.astimezone(UTC).date().isoformat()}", now=now, session=session
        ):
            factor.last_limit_notice_at = now
            notice = SecurityNotice(user.email, "second_factor_attempts_exceeded", now)
        return FactorError(
            429,
            "second_factor_limited",
            "Too many authenticator attempts. Try again later.",
            notice=notice,
        )
    if not daily.take(str(user.id), now=now, session=session):
        return FactorError(
            429, "second_factor_limited", "Too many authenticator attempts. Try again later."
        )
    return None


def consume_code(
    session: Session,
    factor: UserSecondFactor,
    code: str,
    keys: KeyRing,
    now: datetime,
    *,
    allow_backup: bool,
) -> str | None:
    code = normalize_code(code)
    manual = keys.decrypt_text(ProtectedValue(factor.secret_ciphertext, factor.key_id))
    step = matching_step(manual, code, now, factor.last_used_step)
    if step is not None:
        factor.last_used_step, factor.failed_attempts = step, 0
        return "password_totp"
    if allow_backup and len(code) == 16:
        backup = session.scalar(
            select(UserBackupCode)
            .where(
                UserBackupCode.user_id == factor.user_id,
                UserBackupCode.code_digest == backup_digest(code),
                UserBackupCode.used_at.is_(None),
            )
            .with_for_update()
        )
        if backup is not None:
            backup.used_at, factor.failed_attempts = now, 0
            return "password_backup_code"
    factor.failed_attempts = min(100, factor.failed_attempts + 1)
    return None


def replace_backup_codes(session: Session, user_id: UUID, now: datetime) -> list[str]:
    session.execute(delete(UserBackupCode).where(UserBackupCode.user_id == user_id))
    codes = new_backup_codes()
    for code in codes:
        session.add(
            UserBackupCode(
                id=uuid4(),
                user_id=user_id,
                code_digest=backup_digest(normalize_code(code)),
                created_at=now,
            )
        )
    return codes


def revoke_other_sessions(session: Session, user_id: UUID, current_id: UUID | None, now: datetime):
    conditions = [StoredSession.user_id == user_id, StoredSession.revoked_at.is_(None)]
    if current_id is not None:
        conditions.append(StoredSession.id != current_id)
    session.execute(update(StoredSession).where(*conditions).values(revoked_at=now))


def start_locked_enrollment(
    session: Session, user: User, keys: KeyRing, now: datetime
) -> Enrollment:
    factor = session.get(UserSecondFactor, user.id)
    if factor is not None and factor.status == "active":
        raise FactorError(
            422, "second_factor_already_enabled", "Two-step verification is already enabled."
        )
    manual = new_manual_key()
    protected = keys.encrypt_text(manual)
    if factor is None:
        factor = UserSecondFactor(user_id=user.id, failed_attempts=0)
        session.add(factor)
    factor.status, factor.secret_ciphertext, factor.key_id = (
        "pending",
        protected.ciphertext,
        protected.key_id,
    )
    factor.created_at, factor.last_used_step, factor.enabled_at = now, None, None
    path, size = qr_path(manual, user.email)
    return Enrollment(path, size, manual, now + ENROLLMENT_TTL)


def activate_locked(
    session: Session,
    user: User,
    factor: UserSecondFactor,
    now: datetime,
    current_session_id: UUID | None,
) -> list[str]:
    factor.status, factor.enabled_at = "active", now
    user.second_factor_reenroll_required = False
    revoke_other_sessions(session, user.id, current_session_id, now)
    session.execute(
        update(AuthChallenge)
        .where(AuthChallenge.user_id == user.id, AuthChallenge.consumed_at.is_(None))
        .values(consumed_at=now)
    )
    security_activity(session, user.id, "second_factor_enabled", now)
    return replace_backup_codes(session, user.id, now)


def start_enrollment(
    engine: Engine, settings: Settings, user_id: UUID, session_id: UUID, now: datetime
) -> Enrollment:
    keys = KeyRing.from_settings(settings)
    with Session(engine) as session, session.begin():
        user = locked_user(session, user_id, now, session_id)
        return start_locked_enrollment(session, user, keys, now)


def confirm_enrollment(
    engine: Engine, settings: Settings, user_id: UUID, session_id: UUID, code: str, now: datetime
) -> tuple[list[str], list[SecurityNotice]]:
    keys = KeyRing.from_settings(settings)
    error, codes, notices = None, [], []
    with Session(engine) as session, session.begin():
        user = locked_user(session, user_id, now, session_id)
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
                    error = FactorError(
                        400,
                        "invalid_second_factor_code",
                        "That authenticator code is invalid or already used.",
                    )
                else:
                    codes = activate_locked(session, user, factor, now, session_id)
                    notices.append(SecurityNotice(user.email, "second_factor_enabled", now))
    if error:
        raise error
    return codes, notices


def change_factor(
    engine: Engine,
    settings: Settings,
    user_id: UUID,
    session_id: UUID,
    password: str,
    code: str,
    now: datetime,
    *,
    disable: bool,
) -> tuple[list[str], list[SecurityNotice]]:
    keys = KeyRing.from_settings(settings)
    error, codes, notices = None, [], []
    with Session(engine) as session, session.begin():
        user = locked_user(session, user_id, now, session_id)
        factor = session.get(UserSecondFactor, user.id)
        if factor is None or factor.status != "active":
            error = FactorError(
                422, "second_factor_not_enabled", "Two-step verification is not enabled."
            )
        elif disable and requires_factor(session, user.id):
            error = FactorError(
                422,
                "second_factor_required_by_workspace",
                "A workspace requires two-step verification. It cannot be disabled.",
            )
        else:
            error = take_code_budget(session, engine, settings, factor, user, now)
            if error is None and not _verify_password(password, user.password_hash):
                error = FactorError(400, "incorrect_password", "Current password was not accepted.")
            if error is None:
                method = consume_code(session, factor, code, keys, now, allow_backup=disable)
                if method is None:
                    error = FactorError(
                        400,
                        "invalid_second_factor_code",
                        "That authenticator code is invalid or already used.",
                    )
                else:
                    if method == "password_backup_code":
                        notices.append(SecurityNotice(user.email, "backup_code_used", now))
                    if disable:
                        session.delete(factor)
                        session.execute(
                            delete(UserBackupCode).where(UserBackupCode.user_id == user.id)
                        )
                        revoke_other_sessions(session, user.id, session_id, now)
                        session.execute(
                            update(AuthChallenge)
                            .where(AuthChallenge.user_id == user.id)
                            .values(consumed_at=now)
                        )
                        event = "second_factor_disabled"
                    else:
                        codes = replace_backup_codes(session, user.id, now)
                        event = "backup_codes_regenerated"
                    security_activity(session, user.id, event, now)
                    notices.append(SecurityNotice(user.email, event, now))
    if error:
        raise error
    return codes, notices


def security_status(engine: Engine, user_id: UUID, now: datetime) -> dict:
    with Session(engine) as session:
        factor = session.get(UserSecondFactor, user_id)
        return {
            "enabled": factor is not None and factor.status == "active",
            "pending_expires_at": factor.created_at + ENROLLMENT_TTL
            if factor is not None
            and factor.status == "pending"
            and factor.created_at + ENROLLMENT_TTL > now
            else None,
            "backup_codes_remaining": session.scalar(
                select(func.count())
                .select_from(UserBackupCode)
                .where(UserBackupCode.user_id == user_id, UserBackupCode.used_at.is_(None))
            )
            or 0,
            "locked": factor is not None and factor.failed_attempts >= 100,
        }
