"""Owner-only extension of still-available content under current workspace policy."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import owned_document, owned_document_record, refresh_document_access
from app.db.models import Workspace
from app.errors import ApiError
from app.workspace.activity import record_event


class RetentionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_expires_at: AwareDatetime
    days_from_now: int = Field(ge=1, le=30, strict=True)


class RetentionView(BaseModel):
    expires_at: datetime
    current_time: datetime
    maximum_days: int


def retention_view(engine: Engine, *, document_id: UUID, actor_id: UUID) -> RetentionView:
    with Session(engine) as session:
        now = datetime.now(UTC)
        document = owned_document(session, document_id, actor_id, now)
        maximum = session.scalar(
            select(Workspace.content_retention_days).where(Workspace.id == document.workspace_id)
        )
        session.expire(document)
        document = owned_document(session, document_id, actor_id, datetime.now(UTC))
        return RetentionView(
            expires_at=document.expires_at, current_time=now, maximum_days=min(30, maximum)
        )


def renew_retention(
    engine: Engine,
    *,
    document_id: UUID,
    actor_id: UUID,
    body: RetentionRequest,
    authorize: Callable[[], object],
) -> RetentionView:
    with Session(engine) as session, session.begin():
        now = datetime.now(UTC)
        document = owned_document(session, document_id, actor_id, now, lock=True)
        refresh_document_access(session, document_id, actor_id, authorize, owner=True)
        workspace = session.scalar(
            select(Workspace)
            .where(Workspace.id == document.workspace_id)
            .with_for_update(key_share=True)
            .execution_options(populate_existing=True)
        )
        if document.expires_at != body.expected_expires_at:
            raise ApiError(
                409, "retention_changed", "The retention date changed. Check it before renewing."
            )
        maximum = min(30, workspace.content_retention_days)
        if body.days_from_now > maximum:
            raise ApiError(
                422,
                "retention_policy",
                "Choose a duration allowed by the current workspace policy.",
            )
        authorize()
        now = datetime.now(UTC)
        owned_document_record(session, document_id, actor_id)
        # The locked document can expire while waiting for policy/authentication.
        if document.expires_at <= now:
            from app.accounts.access import ContentUnavailable

            raise ContentUnavailable("Expired content cannot be renewed.")
        expires = now + timedelta(days=body.days_from_now)
        if expires <= document.expires_at:
            raise ApiError(
                409,
                "retention_not_extended",
                "This duration would not extend the current retention date.",
            )
        document.expires_at = expires
        document.updated_at = now
        record_event(
            session,
            workspace_id=document.workspace_id,
            actor_id=actor_id,
            document_id=document.id,
            event_code="document_retention_renewed",
            now=now,
        )
        view = RetentionView(expires_at=expires, current_time=now, maximum_days=maximum)
        session.flush()
        refresh_document_access(session, document_id, actor_id, authorize, owner=True)
        if body.expected_expires_at <= datetime.now(UTC):
            from app.accounts.access import ContentUnavailable

            raise ContentUnavailable("Expired content cannot be renewed.")
        return view
