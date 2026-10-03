"""Mailbox ownership and the chosen password are both required to create an account."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.accounts.email_rules import creation_email, lookup_forms
from app.accounts.limits import AttemptLimiter
from app.accounts.security import (
    InvalidSession,
    IssuedSession,
    _dummy_hash,
    _verify_password,
    hash_password,
    issue_session,
)
from app.config import Settings
from app.db.crypto import KeyRing, ProtectedValue
from app.db.email_verification import EmailVerification, PendingRegistration
from app.db.models import Membership, User, Workspace

TTL = timedelta(minutes=15)


class AccountUnavailable(RuntimeError):
    pass


class InvalidRegistrationCode(ValueError):
    pass


class InvalidEmailVerificationCode(ValueError):
    pass


@dataclass(frozen=True)
class CodeDelivery:
    recipient: str
    code: str


def digest(code: str) -> bytes:
    try:
        return hashlib.sha256(code.encode("ascii")).digest()
    except UnicodeEncodeError:
        return b"\0" * 32


def _lock_address(session: Session, canonical: str):
    # Every pending-row transaction for an address uses one lock, avoiding a
    # deadlock when two different valid codes try to delete each other's rows.
    key = int.from_bytes(
        hashlib.sha256(("openanonymi-signup:" + canonical).encode()).digest()[:8],
        "big",
        signed=True,
    )
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def request_registration(
    engine: Engine,
    *,
    settings: Settings,
    email: str,
    password: str,
    workspace_name: str,
    now: datetime,
) -> CodeDelivery | None:
    password_hash = hash_password(password)
    canonical = creation_email(email, settings)
    name = workspace_name.strip()
    if not name or len(name) > 120:
        raise ValueError("Workspace name must contain 1 to 120 characters.")
    keys = KeyRing.from_settings(settings)
    with Session(engine) as session, session.begin():
        _lock_address(session, canonical)
        if session.scalar(select(User.id).where(User.email.in_(lookup_forms(email)))) is not None:
            return None
        if not AttemptLimiter(
            engine,
            settings,
            scope="registration_address",
            maximum=3,
            window_seconds=3600,
            network_scope=False,
        ).take(canonical, now=now, session=session):
            return None
        code = secrets.token_urlsafe(24)
        protected = keys.encrypt_text(name)
        session.add(
            PendingRegistration(
                id=uuid4(),
                canonical_email=canonical,
                code_digest=digest(code),
                password_hash=password_hash,
                workspace_name_ciphertext=protected.ciphertext,
                key_id=protected.key_id,
                created_at=now,
                expires_at=now + TTL,
            )
        )
    return CodeDelivery(canonical, code)


def verify_registration(
    engine: Engine,
    *,
    settings: Settings,
    email: str,
    code: str,
    password: str,
    now: datetime,
    user_agent: str = "",
) -> IssuedSession:
    try:
        forms = lookup_forms(email)
    except ValueError:
        forms = ()
    unavailable = False
    try:
        with Session(engine) as session, session.begin():
            _lock_address(session, forms[0] if forms else "invalid")
            row = session.scalar(
                select(PendingRegistration)
                .where(
                    PendingRegistration.canonical_email.in_(forms),
                    PendingRegistration.code_digest == digest(code),
                    PendingRegistration.expires_at > now,
                )
                .with_for_update()
            )
            valid = _verify_password(password, row.password_hash if row else _dummy_hash)
            if row is None or not valid:
                raise InvalidRegistrationCode
            if session.scalar(select(User.id).where(User.email.in_(forms))) is not None:
                session.execute(
                    delete(PendingRegistration).where(
                        PendingRegistration.canonical_email.in_(forms)
                    )
                )
                unavailable = True
            else:
                name = KeyRing.from_settings(settings).decrypt_text(
                    ProtectedValue(row.workspace_name_ciphertext, row.key_id)
                )
                user = User(
                    id=uuid4(),
                    email=row.canonical_email,
                    password_hash=row.password_hash,
                    created_at=now,
                    email_verified_at=now,
                )
                workspace = Workspace(id=uuid4(), name=name, created_at=now)
                session.add_all([user, workspace])
                session.flush()
                session.add(
                    Membership(
                        user_id=user.id,
                        workspace_id=workspace.id,
                        role="administrator",
                        created_at=now,
                    )
                )
                session.execute(
                    delete(PendingRegistration).where(
                        PendingRegistration.canonical_email.in_(forms)
                    )
                )
                session.flush()
                issued = issue_session(session, user=user, now=now, user_agent=user_agent)
        if unavailable:
            raise AccountUnavailable
        return issued
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) != "23505":
            raise
        with Session(engine) as session, session.begin():
            session.execute(
                delete(PendingRegistration).where(PendingRegistration.canonical_email.in_(forms))
            )
        raise AccountUnavailable from None


def request_email_verification(
    engine: Engine, *, user_id: UUID, now: datetime
) -> CodeDelivery | None:
    with Session(engine) as session, session.begin():
        user = session.scalar(select(User).where(User.id == user_id).with_for_update())
        if user is None or user.disabled_at is not None:
            raise InvalidSession
        if user.email_verified_at is not None:
            return None
        row = session.get(EmailVerification, user_id)
        if row is None:
            row = EmailVerification(user_id=user_id)
            session.add(row)
        code = secrets.token_urlsafe(24)
        row.code_digest, row.created_at, row.expires_at, row.failed_attempts = (
            digest(code),
            now,
            now + TTL,
            0,
        )
        recipient = user.email
    return CodeDelivery(recipient, code)


def confirm_email_verification(engine: Engine, *, user_id: UUID, code: str, now: datetime) -> None:
    invalid = False
    with Session(engine) as session, session.begin():
        user = session.scalar(select(User).where(User.id == user_id).with_for_update())
        if user is None or user.disabled_at is not None:
            raise InvalidSession
        row = session.get(EmailVerification, user_id)
        if row is None or row.expires_at <= now or row.failed_attempts >= 5:
            invalid = True
        elif not hmac.compare_digest(row.code_digest, digest(code)):
            row.failed_attempts += 1
            invalid = True
        else:
            user.email_verified_at = now
            session.delete(row)
    if invalid:
        raise InvalidEmailVerificationCode
