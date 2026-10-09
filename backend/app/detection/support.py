"""Bounded suggestion builders and bundled factual validation data."""

import json
from functools import lru_cache
from pathlib import Path

from app.contracts import FindingCategory, SourceSpan
from app.detection.rules import Suggestion, _append


@lru_cache(maxsize=8)
def data(name: str):
    return json.loads((Path(__file__).parent / "data" / name).read_text(encoding="utf-8"))["values"]


def suggest(result, start, end, category: FindingCategory, rule: str, reason: str, *, date_format=None):
    _append(result, Suggestion(SourceSpan(start=start, end=end), category, rule, "2", reason, date_format))
