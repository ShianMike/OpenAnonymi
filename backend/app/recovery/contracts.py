"""The only content-bearing recovery contract is encrypted before persistence."""

from datetime import datetime
from uuid import UUID

from phonenumbers import SUPPORTED_REGIONS
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.contracts import MAX_CODE_POINTS, MAX_UTF8_BYTES, FindingCategory, VersionRef


class RecoveryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(max_length=MAX_CODE_POINTS)
    title: str | None = Field(default=None, max_length=200)
    categories: list[FindingCategory] = Field(default_factory=list, max_length=8)
    phone_region: str = Field(default="PH", min_length=2, max_length=2)
    retention_days: int = Field(default=7, ge=1, le=30)
    preset_id: UUID | None = None
    base_version: VersionRef | None = None

    @model_validator(mode="after")
    def validate_working_text(self) -> "RecoveryPayload":
        try:
            encoded = self.source.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            raise ValueError("Input must be valid UTF-8 text.") from None
        if len(encoded) > MAX_UTF8_BYTES:
            raise ValueError("Input exceeds the 1 MiB UTF-8 limit.")
        if self.phone_region not in SUPPORTED_REGIONS:
            raise ValueError("Choose a supported phone region.")
        return self


class RecoveryWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0)
    document_id: UUID | None = None
    payload: RecoveryPayload


class RecoveryMetadata(BaseModel):
    id: UUID
    workspace_id: UUID
    document_id: UUID | None
    version: int
    updated_at: datetime
    expires_at: datetime


class RecoveryView(RecoveryMetadata):
    payload: RecoveryPayload
