"""Workspace administration with server-side role checks and serialized mutations."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.accounts.access import require_administrator
from app.accounts.email_rules import creation_email, lookup_forms
from app.accounts.recovery import RecoveryMailer
from app.accounts.security import hash_password
from app.config import Settings
from app.contracts import WorkspaceRole
from app.db.models import Membership, RecoveryToken, User, Workspace
from app.db.models import Session as StoredSession
from app.workspace.activity import record_event


class MemberNotFound(RuntimeError):
    pass


class MemberExists(RuntimeError):
    pass


class LastAdministrator(RuntimeError):
    pass


class WorkspaceVersionConflict(RuntimeError):
    def __init__(self, current: int):
        self.current = current
        super().__init__("Workspace settings changed. Reload before saving.")


@dataclass(frozen=True)
class MemberRecord:
    user_id: UUID
    email: str
    role: WorkspaceRole
    revoked_at: datetime | None
    disabled_at: datetime | None


@dataclass(frozen=True)
class WorkspaceRecord:
    id: UUID
    name: str
    content_retention_days: int
    activity_retention_days: int
    settings_version: int


def _workspace_record(workspace: Workspace) -> WorkspaceRecord:
    return WorkspaceRecord(
        workspace.id,
        workspace.name,
        workspace.content_retention_days,
        workspace.activity_retention_days,
        workspace.settings_version,
    )


def _member_record(membership: Membership, user: User) -> MemberRecord:
    return MemberRecord(
        user.id,
        user.email,
        WorkspaceRole(membership.role),
        membership.revoked_at,
        user.disabled_at,
    )


def _target(session: Session, workspace_id: UUID, user_id: UUID) -> tuple[Membership, User]:
    membership = session.get(Membership, (workspace_id, user_id))
    user = session.get(User, user_id)
    if membership is None or user is None:
        raise MemberNotFound("Member not found.")
    return membership, user


def _ensure_other_administrator(session: Session, workspace_id: UUID, user_id: UUID) -> None:
    others = session.scalar(
        select(func.count())
        .select_from(Membership)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.workspace_id == workspace_id,
            Membership.user_id != user_id,
            Membership.role == WorkspaceRole.ADMINISTRATOR,
            Membership.revoked_at.is_(None),
            User.disabled_at.is_(None),
        )
    )
    if not others:
        raise LastAdministrator("Assign another administrator before changing this account.")


def list_members(session: Session, *, workspace_id: UUID, actor_id: UUID) -> list[MemberRecord]:
    require_administrator(session, workspace_id=workspace_id, actor_id=actor_id)
    rows = session.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.workspace_id == workspace_id)
        .order_by(User.email)
    ).all()
    return [_member_record(membership, user) for membership, user in rows]


def get_workspace_settings(
    session: Session, *, workspace_id: UUID, actor_id: UUID
) -> WorkspaceRecord:
    return _workspace_record(
        require_administrator(session, workspace_id=workspace_id, actor_id=actor_id)
    )


def update_workspace_settings(
    session: Session,
    *,
    workspace_id: UUID,
    actor_id: UUID,
    expected_version: int,
    content_retention_days: int,
    activity_retention_days: int,
) -> WorkspaceRecord:
    if not 1 <= content_retention_days <= 30 or not 1 <= activity_retention_days <= 365:
        raise ValueError("Choose valid retention periods.")
    with session.begin():
        workspace = require_administrator(
            session, workspace_id=workspace_id, actor_id=actor_id, lock=True
        )
        if workspace.settings_version != expected_version:
            raise WorkspaceVersionConflict(workspace.settings_version)
        workspace.content_retention_days = content_retention_days
        workspace.activity_retention_days = activity_retention_days
        workspace.settings_version += 1
        record_event(
            session,
            workspace_id=workspace_id,
            actor_id=actor_id,
            document_id=None,
            event_code="workspace_settings_changed",
            now=datetime.now(UTC),
        )
        session.flush()
        result = _workspace_record(workspace)
    return result


def change_member_role(
    session: Session,
    *,
    workspace_id: UUID,
    actor_id: UUID,
    user_id: UUID,
    role: WorkspaceRole,
) -> MemberRecord:
    with session.begin():
        require_administrator(session, workspace_id=workspace_id, actor_id=actor_id, lock=True)
        membership, user = _target(session, workspace_id, user_id)
        if membership.revoked_at is not None:
            raise MemberNotFound("Member not found.")
        if membership.role == WorkspaceRole.ADMINISTRATOR and role != WorkspaceRole.ADMINISTRATOR:
            _ensure_other_administrator(session, workspace_id, user_id)
        if membership.role != role.value:
            membership.role = role.value
            record_event(
                session,
                workspace_id=workspace_id,
                actor_id=actor_id,
                document_id=None,
                event_code="member_role_changed",
                now=datetime.now(UTC),
            )
        session.flush()
        result = _member_record(membership, user)
    return result


def revoke_member(
    session: Session, *, workspace_id: UUID, actor_id: UUID, user_id: UUID, now: datetime
) -> MemberRecord:
    with session.begin():
        require_administrator(session, workspace_id=workspace_id, actor_id=actor_id, lock=True)
        membership, user = _target(session, workspace_id, user_id)
        if membership.revoked_at is None:
            if membership.role == WorkspaceRole.ADMINISTRATOR:
                _ensure_other_administrator(session, workspace_id, user_id)
            membership.revoked_at = now
            from app.team_review.comments import revoke_member_handoffs

            revoke_member_handoffs(session, workspace_id, user_id, now)
            session.execute(
                update(StoredSession)
                .where(StoredSession.user_id == user_id, StoredSession.revoked_at.is_(None))
                .values(revoked_at=now)
            )
            record_event(
                session,
                workspace_id=workspace_id,
                actor_id=actor_id,
                document_id=None,
                event_code="member_revoked",
                now=now,
            )
        session.flush()
        result = _member_record(membership, user)
    return result


def restore_member(
    session: Session, *, workspace_id: UUID, actor_id: UUID, user_id: UUID
) -> MemberRecord:
    with session.begin():
        require_administrator(session, workspace_id=workspace_id, actor_id=actor_id, lock=True)
        membership, user = _target(session, workspace_id, user_id)
        if user.disabled_at is not None:
            raise MemberNotFound("Member not found.")
        if membership.revoked_at is not None:
            membership.revoked_at = None
            record_event(
                session,
                workspace_id=workspace_id,
                actor_id=actor_id,
                document_id=None,
                event_code="member_restored",
                now=datetime.now(UTC),
            )
        session.flush()
        result = _member_record(membership, user)
    return result


def invite_member(
    session: Session,
    *,
    workspace_id: UUID,
    actor_id: UUID,
    email: str,
    role: WorkspaceRole,
    mailer: RecoveryMailer,
    settings: Settings,
    now: datetime,
) -> MemberRecord:
    normalized = creation_email(email, settings)
    unknown_password_hash = hash_password(secrets.token_urlsafe(32))
    code = secrets.token_urlsafe(24)
    with session.begin():
        require_administrator(session, workspace_id=workspace_id, actor_id=actor_id, lock=True)
        if session.scalar(select(User).where(User.email.in_(lookup_forms(email)))) is not None:
            raise MemberExists("This account already exists. Manage its membership separately.")
        user = User(
            id=uuid4(),
            email=normalized,
            password_hash=unknown_password_hash,
            created_at=now,
        )
        membership = Membership(
            workspace_id=workspace_id,
            user_id=user.id,
            role=role.value,
            created_at=now,
        )
        token = RecoveryToken(
            id=uuid4(),
            user_id=user.id,
            token_hash=hashlib.sha256(code.encode("ascii")).digest(),
            created_at=now,
            expires_at=now + timedelta(hours=24),
        )
        session.add(user)
        session.flush()
        session.add_all([membership, token])
        session.flush()
        mailer.send_invitation_code(user.email, code)
        record_event(
            session,
            workspace_id=workspace_id,
            actor_id=actor_id,
            document_id=None,
            event_code="member_invited",
            now=now,
        )
        result = _member_record(membership, user)
    return result
