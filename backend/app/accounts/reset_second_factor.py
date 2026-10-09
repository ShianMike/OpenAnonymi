"""Authorized cross-workspace resets force enrollment and revoke prior challenges."""

import argparse
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import create_engine, delete, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import require_administrator
from app.accounts.second_factor import FactorError, locked_user
from app.accounts.security_notices import SecurityNotice, deliver_notice
from app.config import load_settings
from app.db.models import Membership, User, Workspace
from app.db.models import Session as StoredSession
from app.db.second_factor import AuthChallenge, UserBackupCode, UserSecondFactor
from app.workspace.activity import record_event


def _require_reset_scope(session, user_id, actor_id, workspace_id):
    active = set(session.scalars(select(Membership.workspace_id).where(
        Membership.user_id == user_id, Membership.revoked_at.is_(None),
    )))
    administered = set(session.scalars(
        select(Membership.workspace_id).join(User, User.id == Membership.user_id).where(
            Membership.user_id == actor_id, Membership.role == "administrator",
            Membership.revoked_at.is_(None), User.disabled_at.is_(None),
        )
    ))
    if actor_id == user_id or workspace_id not in active or not active.issubset(administered):
        raise FactorError(403, "reset_requires_operator", "This reset requires the system operator.")


def reset_factor(
    engine: Engine,
    user_id: UUID,
    now: datetime,
    *,
    actor_id: UUID | None = None,
    workspace_id: UUID | None = None,
    actor_session_id: UUID | None = None,
    reauthorize: Callable[[], object] | None = None,
) -> list[SecurityNotice]:
    with Session(engine) as session, session.begin():
        if actor_id is not None:
            # Authorize the requested workspace before inspecting the target.
            require_administrator(session, workspace_id=workspace_id, actor_id=actor_id)
        workspace_ids = set(
            session.scalars(select(Membership.workspace_id).where(Membership.user_id == user_id))
        )
        if workspace_id is not None:
            workspace_ids.add(workspace_id)
        # Include revoked memberships so restoration cannot race the scope check.
        session.scalars(
            select(Workspace)
            .where(Workspace.id.in_(workspace_ids))
            .order_by(Workspace.id)
            .with_for_update(key_share=True)
        ).all()
        if actor_id is not None:
            require_administrator(session, workspace_id=workspace_id, actor_id=actor_id, lock=True)
            locked_user(session, actor_id, now, actor_session_id)
            if reauthorize is not None:
                reauthorize()
            _require_reset_scope(session, user_id, actor_id, workspace_id)
            event_workspaces = [workspace_id]
        else:
            event_workspaces = list(
                session.scalars(
                    select(Membership.workspace_id).where(
                        Membership.user_id == user_id, Membership.revoked_at.is_(None)
                    )
                )
            )
        user = session.scalar(
            select(User).where(User.id == user_id).with_for_update(key_share=True)
        )
        if user is None or user.disabled_at is not None:
            raise FactorError(
                403, "reset_requires_operator", "This reset requires the system operator."
            )
        session.execute(delete(UserBackupCode).where(UserBackupCode.user_id == user_id))
        session.execute(delete(UserSecondFactor).where(UserSecondFactor.user_id == user_id))
        user.second_factor_reenroll_required = True
        session.execute(
            update(StoredSession)
            .where(StoredSession.user_id == user_id, StoredSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        session.execute(
            update(AuthChallenge)
            .where(AuthChallenge.user_id == user_id, AuthChallenge.consumed_at.is_(None))
            .values(consumed_at=now)
        )
        for ws in event_workspaces:
            record_event(
                session,
                workspace_id=ws,
                actor_id=actor_id,
                document_id=None,
                event_code="second_factor_reset",
                now=now,
            )
        session.flush()
        if reauthorize is not None:
            reauthorize()
            _require_reset_scope(session, user_id, actor_id, workspace_id)
        return [SecurityNotice(user.email, "second_factor_reset", now)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", type=UUID, required=True)
    args = parser.parse_args()
    confirmation = input(
        "This revokes sessions and forces authenticator enrollment. Type the user UUID: "
    )
    if confirmation.strip() != str(args.user_id):
        raise SystemExit("Reset canceled.")
    settings = load_settings()
    engine = create_engine(settings.database_url, hide_parameters=True)
    try:
        notices = reset_factor(engine, args.user_id, datetime.now(UTC))
        from app.accounts.recovery import SmtpRecoveryMailer

        mailer = SmtpRecoveryMailer(settings) if settings.smtp_host else None
        for notice in notices:
            deliver_notice(mailer, notice)
        print("Authenticator reset recorded. New enrollment is required at sign-in.")
    except FactorError:
        raise SystemExit("The account could not be reset.") from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
