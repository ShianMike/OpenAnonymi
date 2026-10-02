"""Registration creates an isolated workspace; it never joins an existing one."""

import re
from datetime import datetime
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.accounts.security import IssuedSession, hash_password, issue_session, normalize_email
from app.db.models import Membership, User, Workspace


class AccountUnavailable(RuntimeError):
    pass


def register_account(
    session: Session, *, email: str, password: str, workspace_name: str, now: datetime
) -> IssuedSession:
    normalized = normalize_email(email)
    if not re.fullmatch(r"[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+", normalized):
        raise ValueError("Enter a valid email address.")
    name = workspace_name.strip()
    if not 1 <= len(name) <= 120:
        raise ValueError("Workspace name must contain 1 to 120 characters.")
    password_hash = hash_password(password)
    try:
        with session.begin():
            user = User(id=uuid4(), email=normalized, password_hash=password_hash, created_at=now)
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
            session.flush()
            issued = issue_session(session, user=user, now=now)
        return issued
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise AccountUnavailable from None
        raise
