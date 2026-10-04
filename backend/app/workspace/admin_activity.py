"""Administrator event metadata and fixed decision diffs without implicit content access."""

import csv
import io
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import Text, and_, cast, func, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import WorkspaceAccessDenied, require_administrator
from app.accounts.api import mutation_identity
from app.accounts.limits import AttemptLimiter
from app.accounts.security import SessionIdentity
from app.config import Settings
from app.contracts import ErrorResponse
from app.db.models import AuditEvent
from app.errors import ApiError
from app.workspace.activity import EVENT_CODES
from app.workspace.decision_audit import DecisionChange

MAX_CSV_BYTES = 8 * 1024 * 1024


def export_limit() -> ApiError:
    return ApiError(
        413,
        "activity_export_limit",
        "Choose a shorter period or event type for an export within 1,000 events and 8 MiB.",
    )


class ActivityCursor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    occurred_at: AwareDatetime
    id: UUID


class AdminActivityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    days: int = Field(default=30, ge=1, le=90, strict=True)
    event_code: str | None = None
    cursor: ActivityCursor | None = None
    limit: int = Field(default=50, ge=1, le=50, strict=True)

    @field_validator("event_code")
    @classmethod
    def known_code(cls, value):
        if value is not None and value not in EVENT_CODES:
            raise ValueError("Choose a supported event code.")
        return value


class AdminActivityEntry(BaseModel):
    id: UUID
    actor_id: UUID | None
    document_id: UUID | None
    occurred_at: datetime
    event_code: str
    outcome: Literal["completed", "failed"]
    decision_version: int | None = Field(ge=0)
    decision_change_count: int = Field(ge=0)
    decision_changes: list[DecisionChange]


class AdminActivityView(BaseModel):
    as_of: datetime
    since: datetime
    events: list[AdminActivityEntry]
    next_cursor: ActivityCursor | None


def read_admin_activity(
    engine: Engine,
    *,
    workspace_id: UUID,
    actor_id: UUID,
    body: AdminActivityRequest,
    maximum: int | None = None,
) -> AdminActivityView:
    now = datetime.now(UTC)
    with Session(engine) as session:
        workspace = require_administrator(session, workspace_id=workspace_id, actor_id=actor_id)
        since = now - timedelta(days=min(body.days, workspace.activity_retention_days))
        query = select(AuditEvent).where(
            AuditEvent.workspace_id == workspace_id,
            AuditEvent.occurred_at >= since,
            AuditEvent.occurred_at <= now,
        )
        if body.event_code:
            query = query.where(AuditEvent.event_code == body.event_code)
        if body.cursor is not None and maximum is None:
            query = query.where(
                or_(
                    AuditEvent.occurred_at < body.cursor.occurred_at,
                    and_(
                        AuditEvent.occurred_at == body.cursor.occurred_at,
                        AuditEvent.id < body.cursor.id,
                    ),
                )
            )
        limit = maximum if maximum is not None else body.limit
        if maximum is not None:
            # Refuse large JSON before loading it into Python. The fixed per-row
            # allowance also bounds the remaining IDs, codes and CSV quoting.
            selected = (
                query.with_only_columns(
                    AuditEvent.id,
                    func.octet_length(cast(AuditEvent.decision_changes, Text)).label("diff_bytes"),
                )
                .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
                .limit(maximum + 1)
                .subquery()
            )
            count, diff_bytes = session.execute(
                select(func.count(), func.coalesce(func.sum(selected.c.diff_bytes), 0)).select_from(
                    selected
                )
            ).one()
            require_administrator(session, workspace_id=workspace_id, actor_id=actor_id)
            if count > maximum or diff_bytes + count * 512 > MAX_CSV_BYTES:
                raise export_limit()
        rows = session.scalars(
            query.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc()).limit(limit + 1)
        ).all()
        events = []
        for row in rows[:limit]:
            try:
                if (
                    row.event_code not in EVENT_CODES
                    or row.decision_change_count < len(row.decision_changes)
                    or len(row.decision_changes) > 256
                ):
                    raise ValueError
                events.append(AdminActivityEntry.model_validate(row, from_attributes=True))
            except (ValueError, ValidationError):
                raise ApiError(
                    503, "activity_unavailable", "Activity metadata is unavailable."
                ) from None
        require_administrator(session, workspace_id=workspace_id, actor_id=actor_id)
        if maximum is not None and len(rows) > maximum:
            raise export_limit()
        cursor = (
            ActivityCursor(occurred_at=events[-1].occurred_at, id=events[-1].id)
            if len(rows) > limit
            else None
        )
        return AdminActivityView(as_of=now, since=since, events=events, next_cursor=cursor)


def activity_csv(view: AdminActivityView) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\r\n")
    writer.writerow(
        (
            "occurred_at",
            "event_code",
            "outcome",
            "document_id",
            "actor_id",
            "decision_version",
            "decision_change_count",
            "recorded_changes",
            "decision_changes",
        )
    )
    for row in view.events:
        values = [
            row.occurred_at.isoformat(),
            row.event_code,
            row.outcome,
            str(row.document_id) if row.document_id else "",
            str(row.actor_id) if row.actor_id else "",
            row.decision_version if row.decision_version is not None else "",
            row.decision_change_count,
            len(row.decision_changes),
            json.dumps(
                [change.model_dump(mode="json") for change in row.decision_changes],
                separators=(",", ":"),
            ),
        ]
        # All strings above are fixed codes, typed IDs/times or allowlisted JSON.
        # Keep spreadsheet safety even if a future column adds free-form values.
        writer.writerow(
            [
                "'" + value
                if isinstance(value, str)
                and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n"))
                else value
                for value in values
            ]
        )
        # Every exported string is ASCII (fixed enums, UUIDs, ISO times and
        # ensure_ascii JSON). Check each row before the buffer can grow further.
        if stream.tell() + 3 > MAX_CSV_BYTES:
            raise export_limit()
    payload = stream.getvalue().encode("utf-8-sig")
    if len(payload) > MAX_CSV_BYTES:
        raise export_limit()
    return payload


def create_admin_activity_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1/workspaces", tags=["administrator activity"])
    limiter = AttemptLimiter(
        engine,
        settings,
        scope="admin_activity_export",
        maximum=10,
        window_seconds=60,
        network_scope=False,
    )
    errors = {code: {"model": ErrorResponse} for code in (401, 403, 404, 413, 422, 429, 503)}

    def guarded(operation: Callable):
        try:
            return operation()
        except WorkspaceAccessDenied:
            raise ApiError(404, "workspace_not_found", "Workspace not found.") from None

    def recheck(request, workspace_id, actor_id):
        mutation_identity(request)
        with Session(engine) as session:
            guarded(
                lambda: require_administrator(session, workspace_id=workspace_id, actor_id=actor_id)
            )

    @router.post(
        "/{workspace_id}/activity/admin", response_model=AdminActivityView, responses=errors
    )
    def read(
        workspace_id: UUID,
        body: AdminActivityRequest,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        view = guarded(
            lambda: read_admin_activity(
                engine, workspace_id=workspace_id, actor_id=identity.user_id, body=body
            )
        )
        recheck(request, workspace_id, identity.user_id)
        return view

    @router.post("/{workspace_id}/activity/admin/csv", response_class=Response, responses=errors)
    def export(
        workspace_id: UUID,
        body: AdminActivityRequest,
        request: Request,
        identity: Annotated[SessionIdentity, Depends(mutation_identity)],
    ):
        with Session(engine) as session:
            guarded(
                lambda: require_administrator(
                    session, workspace_id=workspace_id, actor_id=identity.user_id
                )
            )
        if not limiter.take(str(identity.user_id)):
            raise ApiError(429, "action_limited", "Please wait a minute and try again.")
        view = guarded(
            lambda: read_admin_activity(
                engine,
                workspace_id=workspace_id,
                actor_id=identity.user_id,
                body=body,
                maximum=1000,
            )
        )
        payload = activity_csv(view)
        recheck(request, workspace_id, identity.user_id)
        return Response(
            payload,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="workspace-activity.csv"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    return router
