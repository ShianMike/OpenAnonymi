from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.contracts import FindingCategory, SourceSpan, VersionRef


class RuleInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["phrase", "identifier"] = "phrase"
    expression: str = Field(min_length=1, max_length=160)
    category: FindingCategory = FindingCategory.CUSTOM
    case_sensitive: bool = False
    whole_word: bool = True
    enabled: bool = True

    @model_validator(mode="after")
    def validate_definition(self):
        if not self.name.strip() or not self.expression.strip():
            raise ValueError("Give the rule a name and a nonempty expression.")
        if any(
            ord(character) < 32 or 0xD800 <= ord(character) <= 0xDFFF
            for character in self.name + self.expression
        ):
            raise ValueError("Use a single line without control characters.")
        if self.kind == "identifier" and not any(symbol in self.expression for symbol in "#@"):
            raise ValueError("An identifier template needs # for a digit or @ for a letter.")
        return self


class RuleUpdate(RuleInput):
    expected_version: int = Field(ge=1)


class RuleView(RuleInput):
    id: UUID
    version: int
    updated_at: datetime


class RuleTestInput(BaseModel):
    rule: RuleInput
    text: str = Field(max_length=10_000)


class RuleTestMatch(BaseModel):
    span: SourceSpan
    text: str


class RuleTestView(BaseModel):
    matches: list[RuleTestMatch]
    match_count: int


class RuleSnapshotView(BaseModel):
    version: VersionRef
    rules: list[RuleView]
    update_available: bool


class RefreshRulesInput(BaseModel):
    expected: VersionRef
