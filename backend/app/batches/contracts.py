from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.contracts import FindingCategory, VersionRef

BatchDocumentState = Literal[
    "queued",
    "scanning",
    "scan_failed",
    "needs_review",
    "ready",
    "awaiting_approval",
    "approved",
    "exported",
    "expired",
    "deleted",
]
ExclusionReason = Literal[
    "not_confirmed",
    "stale_confirmation",
    "approval_required",
    "expired",
    "deleted",
    "scan_failed",
]


class CreateBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: UUID
    name: str | None = Field(default=None, max_length=200)
    categories: list[FindingCategory] = Field(
        default_factory=lambda: [FindingCategory.EMAIL, FindingCategory.PHONE]
    )
    phone_region: str = Field(default="PH", min_length=2, max_length=2)
    language: str = Field(default="en", min_length=2, max_length=2)
    preset_id: UUID | None = None
    retention_days: int | None = Field(default=None, ge=1, le=30)


class RuleRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    version: int = Field(ge=1)


class BatchSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    categories: list[FindingCategory]
    phone_region: str
    language: str
    preset_id: UUID | None
    preset_version: int | None
    preferred_action: Literal["label", "redact"]
    category_defaults: dict
    retention_days: int = Field(ge=1, le=30)
    custom_rules: list[RuleRef] = Field(default_factory=list)


class BatchDocumentView(BaseModel):
    id: UUID
    position: int
    title: str | None
    state: BatchDocumentState
    version: VersionRef | None
    expires_at: datetime
    last_error_code: str | None
    attempts: int


class BatchView(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str | None
    settings: BatchSettings
    uploaded_bytes: int
    created_at: datetime
    documents: list[BatchDocumentView]
    counts: dict[str, int]
    next_document_id: UUID | None
    processing: bool


class BatchListEntry(BaseModel):
    id: UUID
    name: str | None
    created_at: datetime
    document_count: int


class BatchList(BaseModel):
    own_batches: list[BatchListEntry]
    workspace_total: int | None = None


class DeleteBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: bool


class BatchOutputRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    mode: Literal["original", "txt"] = "original"


class OutputExclusion(BaseModel):
    document_id: UUID
    reason: ExclusionReason


class BatchEligibility(BaseModel):
    included_count: int
    total_count: int
    excluded: list[OutputExclusion]
