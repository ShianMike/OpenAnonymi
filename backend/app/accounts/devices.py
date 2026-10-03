"""List and revoke only the signed-in user's own active server-side sessions."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.second_factor import FactorError, locked_user, security_activity
from app.accounts.security_notices import SecurityNotice
from app.db.models import Session as StoredSession


def list_devices(engine: Engine, user_id: UUID, current_id: UUID, now: datetime) -> list[dict]:
    with Session(engine) as session:
        rows = session.scalars(
            select(StoredSession)
            .where(
                StoredSession.user_id == user_id,
                StoredSession.revoked_at.is_(None),
                StoredSession.expires_at > now,
            )
            .order_by(
                (StoredSession.id == current_id).desc(),
                StoredSession.created_at.desc(),
                StoredSession.id,
            )
            .limit(100)
        ).all()
        return [
            {
                "id": row.id,
                "current": row.id == current_id,
                "created_at": row.created_at,
                "last_seen_at": row.last_seen_at,
                "expires_at": row.expires_at,
                "device_label": row.device_label,
                "auth_method": row.auth_method,
            }
            for row in rows
        ]


def revoke_device(
    engine: Engine, user_id: UUID, current_id: UUID, target_id: UUID, now: datetime
) -> bool:
    with Session(engine) as session, session.begin():
        locked_user(session, user_id, now, current_id)
        row = session.scalar(
            select(StoredSession)
            .where(
                StoredSession.id == target_id,
                StoredSession.user_id == user_id,
                StoredSession.revoked_at.is_(None),
                StoredSession.expires_at > now,
            )
            .with_for_update()
        )
        if row is None:
            raise FactorError(404, "session_not_found", "Session not found.")
        row.revoked_at = now
        if row.id != current_id:
            security_activity(session, user_id, "device_signed_out", now)
        return row.id == current_id


def revoke_others(
    engine: Engine, user_id: UUID, current_id: UUID, now: datetime
) -> list[SecurityNotice]:
    with Session(engine) as session, session.begin():
        user = locked_user(session, user_id, now, current_id)
        changed = session.execute(
            update(StoredSession)
            .where(
                StoredSession.user_id == user_id,
                StoredSession.id != current_id,
                StoredSession.revoked_at.is_(None),
                StoredSession.expires_at > now,
            )
            .values(revoked_at=now)
        ).rowcount
        if changed:
            security_activity(session, user_id, "other_devices_signed_out", now)
            return [SecurityNotice(user.email, "other_sessions_signed_out", now)]
        return []
