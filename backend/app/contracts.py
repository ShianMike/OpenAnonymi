"""Public review IDs, states, spans, and API response shapes."""

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

MAX_UTF8_BYTES = 1_048_576
MAX_CODE_POINTS = 100_000


class DocumentStatus(StrEnum):
    DRAFT = "draft"
    SCANNING = "scanning"
    NEEDS_REVIEW = "needs_review"
    READY = "ready"
    EXPORTED = "exported"
    FAILED = "failed"
    EXPIRED = "expired"
    DELETED = "deleted"


class FindingCategory(StrEnum):
    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    ADDRESS = "address"
    IDENTIFIER = "identifier"
    CUSTOM = "custom"
    EMAIL = "email"
    PHONE = "phone"


class DecisionAction(StrEnum):
    LABEL = "label"
    REDACT = "redact"
    KEEP = "keep"


class WorkspaceRole(StrEnum):
    MEMBER = "member"
    ADMINISTRATOR = "administrator"


class SourceSpan(BaseModel):
    """Half-open Unicode code point offsets into one immutable source revision."""

    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def require_non_empty(self) -> "SourceSpan":
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class VersionRef(BaseModel):
    document_id: UUID
    source_revision_id: UUID
    decision_version: int = Field(ge=0)
    settings_version: int = Field(ge=1)


class OwnershipContext(BaseModel):
    """Derived from server-side session and membership, never trusted from a request body."""

    actor_id: UUID
    workspace_id: UUID
    role: WorkspaceRole


class ConflictResponse(BaseModel):
    code: Literal["version_conflict"] = "version_conflict"
    message: str = "This review changed in another session. Reload before saving."
    current_version: VersionRef


class CompletionRef(BaseModel):
    version: VersionRef
    confirmed_at: datetime


class ErrorDetail(BaseModel):
    field: str
    issue: str


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str


class ServiceMetadata(BaseModel):
    name: str
    api_version: str
    source_max_utf8_bytes: int
    source_max_code_points: int
    document_statuses: list[DocumentStatus]
    finding_categories: list[FindingCategory]
    decision_actions: list[DecisionAction]


def service_metadata() -> ServiceMetadata:
    return ServiceMetadata(
        name="OpenAnonymi",
        api_version="v1",
        source_max_utf8_bytes=MAX_UTF8_BYTES,
        source_max_code_points=MAX_CODE_POINTS,
        document_statuses=list(DocumentStatus),
        finding_categories=list(FindingCategory),
        decision_actions=list(DecisionAction),
    )
