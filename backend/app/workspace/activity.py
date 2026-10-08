"""Allowlisted, content-free activity and member-safe reporting."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import active_workspace
from app.contracts import WorkspaceRole
from app.db.models import AuditEvent, Document, Membership
from app.workspace.decision_audit import decision_diff

EVENT_CODES = frozenset(
    {
        "document_created",
        "source_revised",
        "review_completed",
        "output_copied",
        "output_generated",
        "document_deleted",
        "document_expired",
        "document_retention_renewed",
        "preset_created",
        "preset_updated",
        "preset_defaults_applied",
        "workspace_rule_saved",
        "review_handoff_changed",
        "review_second_approved",
        "finding_comment_added",
        "scan_settings_changed",
        "scan_completed",
        "scan_failed",
        "review_decision_saved",
        "finding_added",
        "finding_corrected",
        "finding_removed",
        "group_split",
        "group_merged",
        "review_edit_undone",
        "workspace_settings_changed",
        "member_invited",
        "member_role_changed",
        "member_revoked",
        "member_restored",
        "second_factor_enabled",
        "second_factor_disabled",
        "backup_codes_regenerated",
        "device_signed_out",
        "other_devices_signed_out",
        "second_factor_reset",
    }
)


@dataclass(frozen=True)
class ActivityEntry:
    event_code: str
    outcome: str
    document_id: UUID | None
    occurred_at: datetime


@dataclass(frozen=True)
class ActivityViewData:
    as_of: datetime
    since: datetime
    own_events: list[ActivityEntry]
    own_total: int
    workspace_counts: dict[str, int] | None


def record_event(
    session: Session,
    *,
    workspace_id: UUID,
    actor_id: UUID | None,
    document_id: UUID | None,
    event_code: str,
    now: datetime,
    outcome: str = "completed",
    decision_before: dict | None = None,
    decision_version: int | None = None,
) -> None:
    if event_code not in EVENT_CODES:
        raise ValueError("Unsupported activity code.")
    if outcome not in ("completed", "failed"):
        raise ValueError("Unsupported activity outcome.")
    changes, count = (
        decision_diff(session, decision_before) if decision_before is not None else ([], 0)
    )
    session.add(
        AuditEvent(
            id=uuid4(),
            workspace_id=workspace_id,
            actor_id=actor_id,
            document_id=document_id,
            event_code=event_code,
            outcome=outcome,
            occurred_at=now,
            decision_changes=changes,
            decision_change_count=count,
            decision_version=decision_version,
        )
    )


def load_activity(
    engine: Engine, *, workspace_id: UUID, actor_id: UUID, now: datetime
) -> ActivityViewData:
    since = now - timedelta(days=30)
    with Session(engine) as session:
        active_workspace(session, workspace_id, actor_id)
        own_filter = or_(AuditEvent.actor_id == actor_id, Document.owner_id == actor_id)
        own_total = (
            session.scalar(
                select(func.count(AuditEvent.id))
                .outerjoin(Document, Document.id == AuditEvent.document_id)
                .where(
                    AuditEvent.workspace_id == workspace_id,
                    AuditEvent.occurred_at >= since,
                    own_filter,
                )
            )
            or 0
        )
        own = session.execute(
            select(
                AuditEvent.event_code,
                AuditEvent.outcome,
                AuditEvent.document_id,
                AuditEvent.occurred_at,
            )
            .outerjoin(Document, Document.id == AuditEvent.document_id)
            .where(
                AuditEvent.workspace_id == workspace_id,
                AuditEvent.occurred_at >= since,
                own_filter,
            )
            .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
            .limit(100)
        ).all()
        active_workspace(session, workspace_id, actor_id)
        role = session.scalar(
            select(Membership.role).where(
                Membership.workspace_id == workspace_id, Membership.user_id == actor_id
            )
        )
        workspace_counts = None
        if role == WorkspaceRole.ADMINISTRATOR:
            workspace_counts = dict(
                session.execute(
                    select(AuditEvent.event_code, func.count(AuditEvent.id))
                    .where(
                        AuditEvent.workspace_id == workspace_id,
                        AuditEvent.occurred_at >= since,
                    )
                    .group_by(AuditEvent.event_code)
                ).all()
            )
        active_workspace(session, workspace_id, actor_id)
        if (
            session.scalar(
                select(Membership.role).where(
                    Membership.workspace_id == workspace_id, Membership.user_id == actor_id
                )
            )
            != WorkspaceRole.ADMINISTRATOR
        ):
            workspace_counts = None
        return ActivityViewData(
            as_of=now,
            since=since,
            own_events=[
                ActivityEntry(
                    event_code=event.event_code,
                    outcome=event.outcome,
                    document_id=event.document_id,
                    occurred_at=event.occurred_at,
                )
                for event in own
            ],
            own_total=own_total,
            workspace_counts=workspace_counts,
        )
