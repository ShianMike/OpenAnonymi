"""Password verification and revocable, opaque server-side sessions."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts import WorkspaceRole
from app.db.models import Membership, User
from app.db.models import Session as StoredSession

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


@dataclass(frozen=True)
class SessionIdentity:
    session_id: UUID
    user_id: UUID
    email: str
    expires_at: datetime
    memberships: tuple[ActiveMembership, ...]
    csrf_token: str


@dataclass(frozen=True)
class IssuedSession:
    token: str
    identity: SessionIdentity


def normalize_email(email: str) -> str:
    normalized = email.strip().casefold()
    if (
        len(normalized) > 320
        or not normalized
        or "@" not in normalized
        or any(character.isspace() for character in normalized)
    ):
        raise ValueError("Enter a valid email address.")
    return normalized


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
    rows = session.scalars(
        select(Membership)
        .where(Membership.user_id == user_id, Membership.revoked_at.is_(None))
        .order_by(Membership.workspace_id)
    ).all()
    return tuple(ActiveMembership(row.workspace_id, WorkspaceRole(row.role)) for row in rows)


def sign_in(session: Session, *, email: str, password: str, now: datetime) -> IssuedSession:
    try:
        normalized = normalize_email(email)
    except ValueError:
        normalized = ""
    with session.begin():
        user = session.scalar(select(User).where(User.email == normalized)) if normalized else None
        valid_password = _verify_password(password, user.password_hash if user else _dummy_hash)
        if user is None or user.disabled_at is not None or not valid_password:
            raise InvalidCredentials("Email or password was not accepted.")
        memberships = _memberships(session, user.id)
        if not memberships:
            raise InvalidCredentials("Email or password was not accepted.")
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
        )
        session.add(record)
        identity = SessionIdentity(
            record.id, user.id, user.email, expires_at, memberships, csrf_token
        )
    return IssuedSession(token, identity)


def read_session(session: Session, *, token: str | None, now: datetime) -> SessionIdentity:
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
    return SessionIdentity(
        record.id, user.id, user.email, record.expires_at, memberships, csrf_token
    )


def revoke_session(session: Session, *, identity: SessionIdentity, now: datetime) -> None:
    with session.begin():
        record = session.get(StoredSession, identity.session_id)
        if record is None or record.revoked_at is not None:
            raise InvalidSession("Sign in to continue.")
        record.revoked_at = now
