from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

NotificationCode = Literal[
    "review_assigned",
    "review_unassigned",
    "approval_requested",
    "review_approved",
    "approval_invalidated",
    "comment_added",
]


class NotificationView(BaseModel):
    id: UUID
    workspace_id: UUID
    document_id: UUID | None
    actor_id: UUID | None
    event_code: NotificationCode
    created_at: datetime
    read_at: datetime | None
    document_available: bool
    title: str | None


class NotificationPage(BaseModel):
    items: list[NotificationView]
    next_cursor: UUID | None


class UnreadCount(BaseModel):
    count: int


class ReadAllResult(BaseModel):
    changed: int


class NotificationPreferences(BaseModel):
    notification_emails: Literal["off", "immediate"]
    notification_emails_available: bool


class UpdateNotificationPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notification_emails: Literal["off", "immediate"]
