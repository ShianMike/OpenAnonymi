"""Authenticated CSV configuration and content spans, never accepted as source maps."""

from typing import Literal

from pydantic import BaseModel, Field

from app.contracts import VersionRef
from app.intake.column_rules import ColumnRule


class CsvCellView(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    quoted: bool


class CsvInfo(BaseModel):
    delimiter: Literal[",", ";", "\t", "|"]
    has_header: bool
    columns: int
    data_rows: int
    headers: list[str]
    rules: list[ColumnRule]
    cells: list[list[CsvCellView]]


class CsvSettingsView(CsvInfo):
    version: VersionRef


class CsvSettingsRequest(BaseModel):
    delimiter: Literal[",", ";", "\t", "|"]
    has_header: bool
    expected_settings_version: int = Field(ge=1)


class ColumnRulesRequest(BaseModel):
    rules: list[ColumnRule] = Field(max_length=50)
    expected_settings_version: int = Field(ge=1)
