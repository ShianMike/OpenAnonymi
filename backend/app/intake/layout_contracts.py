"""Inert, versioned file previews; no original file containers or executable content."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.contracts import DecisionAction, VersionRef


class PageRegion(BaseModel):
    finding_id: UUID
    box: tuple[int, int, int, int]
    action: DecisionAction | None


class LayoutPage(BaseModel):
    width: int
    height: int
    points: tuple[float, float]
    image: str
    regions: list[PageRegion] = Field(default_factory=list)


class FileLayout(BaseModel):
    kind: Literal["txt", "pdf"]
    pages: list[LayoutPage] = Field(default_factory=list)


class FileLayoutView(BaseModel):
    version: VersionRef
    layout: FileLayout | None
