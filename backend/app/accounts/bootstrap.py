"""Interactive, one-time setup of the first workspace administrator.

Run after migrations. Passwords are read from the terminal, never command arguments.
"""

import getpass
import hmac
import sys
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.accounts.email_rules import creation_email
from app.accounts.security import hash_password
from app.config import ConfigurationError, Settings, load_settings
from app.db.models import Membership, User, Workspace

_BOOTSTRAP_LOCK = 612_004_871


class BootstrapUnavailable(RuntimeError):
    pass


def bootstrap_admin(
    session: Session,
    *,
    email: str,
    password: str,
    workspace_name: str,
    now: datetime,
    settings: Settings,
) -> tuple[UUID, UUID]:
    normalized = creation_email(email, settings)
    name = workspace_name.strip()
    if not 1 <= len(name) <= 120:
        raise ValueError("Workspace name must contain 1 to 120 characters.")
    password_hash = hash_password(password)
    user_id, workspace_id = uuid4(), uuid4()
    with session.begin():
        session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": _BOOTSTRAP_LOCK}
        )
        if session.scalar(select(func.count()).select_from(User)) or session.scalar(
            select(func.count()).select_from(Workspace)
        ):
            raise BootstrapUnavailable("Initial setup is already complete.")
        session.add_all(
            [
                User(
                    id=user_id,
                    email=normalized,
                    password_hash=password_hash,
                    created_at=now,
                ),
                Workspace(id=workspace_id, name=name, created_at=now),
            ]
        )
        session.flush()
        session.add(
            Membership(
                workspace_id=workspace_id,
                user_id=user_id,
                role="administrator",
                created_at=now,
            )
        )
    return user_id, workspace_id


def _read_password(prompt: str) -> str:
    if sys.stdin.isatty():
        return getpass.getpass(prompt)
    line = sys.stdin.readline()
    if not line:
        raise ValueError("Password input ended before setup completed.")
    return line.removesuffix("\n").removesuffix("\r")


def main() -> None:
    try:
        settings = load_settings()
        email = input("Administrator email: ")
        workspace_name = input("Workspace name: ")
        password = _read_password("Password (at least 12 characters): ")
        confirmation = _read_password("Confirm password: ")
        if not hmac.compare_digest(password, confirmation):
            raise ValueError("Passwords do not match.")
        engine = create_engine(settings.database_url, pool_pre_ping=True, hide_parameters=True)
        try:
            with Session(engine) as session:
                bootstrap_admin(
                    session,
                    settings=settings,
                    email=email,
                    password=password,
                    workspace_name=workspace_name,
                    now=datetime.now(UTC),
                )
        finally:
            engine.dispose()
    except (BootstrapUnavailable, ConfigurationError, ValueError, SQLAlchemyError) as exc:
        if isinstance(exc, (BootstrapUnavailable, ValueError)):
            raise SystemExit(str(exc)) from None
        raise SystemExit("Initial setup failed. Check configuration and database access.") from None
    print("Initial administrator created. Sign in through the website.")


if __name__ == "__main__":
    main()
