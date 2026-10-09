"""Password verification and revocable, opaque server-side sessions."""

import hashlib
import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from sqlalchemy import exists, select, update
from sqlalchemy.orm import Session

from app.accounts.email_rules import lookup_forms
from app.contracts import WorkspaceRole
from app.db.models import Membership, User, Workspace
from app.db.models import Session as StoredSession
from app.db.second_factor import AuthChallenge, UserSecondFactor

if TYPE_CHECKING:
    from app.accounts.challenges import IssuedChallenge

SESSION_TTL = timedelta(hours=12)
COOKIE_NAME = "openanonymi_session"
COOKIE_PATH = "/api/v1"
_password_hash = PasswordHash.recommended()
_dummy_hash = _password_hash.hash(secrets.token_urlsafe(32))


class InvalidCredentials(RuntimeError):
    pass


class InvalidSession(RuntimeError):
    pass


@dataclass(frozen=True)
class ActiveMembership:
    workspace_id: UUID
    role: WorkspaceRole
    workspace_name: str
    require_second_factor: bool = False
    factor_active: bool = False


@dataclass(frozen=True)
class SessionIdentity:
    session_id: UUID
    user_id: UUID
    email: str
    expires_at: datetime
    memberships: tuple[ActiveMembership, ...]
    csrf_token: str
    email_verified: bool = False
    second_factor_enabled: bool = False
    second_factor_setup_required: bool = False


@dataclass(frozen=True)
class IssuedSession:
    token: str
    identity: SessionIdentity


def hash_password(password: str) -> str:
    if not 12 <= len(password) <= 1024:
        raise ValueError("Password must contain 12 to 1024 characters.")
    return _password_hash.hash(password)


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        return _password_hash.verify(password, stored_hash)
    except (UnknownHashError, ValueError):
        return False


def _digest(token: str) -> bytes:
    return hashlib.sha256(token.encode("ascii")).digest()


def _csrf_token(token: str) -> str:
    return hmac.new(
        token.encode("ascii"), b"openanonymi-session-csrf-v1", hashlib.sha256
    ).hexdigest()


def _memberships(session: Session, user_id: UUID) -> tuple[ActiveMembership, ...]:
    active_factor = exists(
        select(UserSecondFactor.user_id).where(
            UserSecondFactor.user_id == user_id, UserSecondFactor.status == "active"
        )
    )
    rows = session.execute(
        select(Membership, Workspace.name, Workspace.require_second_factor, active_factor)
        .join(Workspace, Workspace.id == Membership.workspace_id)
        .where(Membership.user_id == user_id, Membership.revoked_at.is_(None))
        .order_by(Membership.workspace_id)
    ).all()
    return tuple(
        ActiveMembership(
            membership.workspace_id, WorkspaceRole(membership.role), name, required, enabled
        )
        for membership, name, required, enabled in rows
    )


def sign_in(
    session: Session, *, email: str, password: str, now: datetime, user_agent: str = "",
    reauthorize: "Callable[[Session, IssuedSession | IssuedChallenge], object] | None" = None,
) -> "IssuedSession | IssuedChallenge":
    from app.accounts.challenges import password_step

    try:
        forms = lookup_forms(email)
    except ValueError:
        forms = ()
    with session.begin():
        user = (
            session.scalar(select(User).where(User.email.in_(forms)).with_for_update())
            if forms
            else None
        )
        valid_password = _verify_password(password, user.password_hash if user else _dummy_hash)
        if user is None or user.disabled_at is not None or not valid_password:
            raise InvalidCredentials("Email or password was not accepted.")
        memberships = _memberships(session, user.id)
        if not memberships:
            raise InvalidCredentials("Email or password was not accepted.")
        issued = password_step(session, user, now, user_agent)
        session.flush()
        if reauthorize is not None:
            reauthorize(session, issued)
    return issued


def issue_session(
    session: Session,
    *,
    user: User,
    now: datetime,
    user_agent: str = "",
    auth_method: str = "password",
) -> IssuedSession:
    """Issue inside the caller's transaction, including account registration."""
    memberships = _memberships(session, user.id)
    from app.accounts.device_labels import device_label

    token = secrets.token_urlsafe(32)
    csrf_token = _csrf_token(token)
    expires_at = now + SESSION_TTL
    record = StoredSession(
        id=uuid4(),
        user_id=user.id,
        token_hash=_digest(token),
        csrf_hash=_digest(csrf_token),
        created_at=now,
        expires_at=expires_at,
        last_seen_at=now,
        device_label=device_label(user_agent),
        auth_method=auth_method,
    )
    session.add(record)
    identity = SessionIdentity(
        record.id,
        user.id,
        user.email,
        expires_at,
        memberships,
        csrf_token,
        user.email_verified_at is not None,
        any(item.factor_active for item in memberships),
        bool(user.second_factor_reenroll_required)
        or any(item.require_second_factor and not item.factor_active for item in memberships),
    )
    return IssuedSession(token, identity)


def read_session(
    session: Session, *, token: str | None, now: datetime, touch: bool = True
) -> SessionIdentity:
    if token is None or len(token) > 100 or not token.isascii():
        raise InvalidSession("Sign in to continue.")
    record = session.scalar(select(StoredSession).where(StoredSession.token_hash == _digest(token)))
    if record is None or record.revoked_at is not None or record.expires_at <= now:
        raise InvalidSession("Sign in to continue.")
    user = session.get(User, record.user_id)
    if user is None or user.disabled_at is not None:
        raise InvalidSession("Sign in to continue.")
    memberships = _memberships(session, user.id)
    if not memberships:
        raise InvalidSession("Sign in to continue.")
    csrf_token = _csrf_token(token)
    if not hmac.compare_digest(record.csrf_hash, _digest(csrf_token)):
        raise InvalidSession("Sign in to continue.")
    if touch and record.last_seen_at <= now - timedelta(minutes=5):
        session.execute(
            update(StoredSession)
            .where(
                StoredSession.id == record.id,
                StoredSession.last_seen_at <= now - timedelta(minutes=5),
            )
            .values(last_seen_at=now)
        )
    return SessionIdentity(
        record.id,
        user.id,
        user.email,
        record.expires_at,
        memberships,
        csrf_token,
        user.email_verified_at is not None,
        any(item.factor_active for item in memberships),
        bool(user.second_factor_reenroll_required)
        or any(item.require_second_factor and not item.factor_active for item in memberships),
    )


def revoke_session(session: Session, *, identity: SessionIdentity, now: datetime) -> None:
    with session.begin():
        record = session.get(StoredSession, identity.session_id)
        if record is None or record.revoked_at is not None:
            raise InvalidSession("Sign in to continue.")
        record.revoked_at = now


def change_password(
    session: Session,
    *,
    identity: SessionIdentity,
    current_password: str,
    new_password: str,
    now: datetime,
    reauthorize: Callable[[], object] | None = None,
) -> None:
    """Change only the signed-in account and end all of its sessions."""
    with session.begin():
        user = session.scalar(select(User).where(User.id == identity.user_id).with_for_update())
        if (
            user is None
            or user.disabled_at is not None
            or not _verify_password(current_password, user.password_hash)
        ):
            raise InvalidCredentials("Current password was not accepted.")
        if _verify_password(new_password, user.password_hash):
            raise ValueError("Choose a different new password.")
        if reauthorize is not None:
            reauthorize()
        user.password_hash = hash_password(new_password)
        session.execute(
            update(AuthChallenge)
            .where(AuthChallenge.user_id == user.id, AuthChallenge.consumed_at.is_(None))
            .values(consumed_at=now)
        )
        session.execute(
            update(StoredSession)
            .where(StoredSession.user_id == user.id, StoredSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        session.flush()
        if reauthorize is not None:
            # A separate HTTP session read sees the committed authorization,
            # before this transaction intentionally ends the account's sessions.
            reauthorize()
