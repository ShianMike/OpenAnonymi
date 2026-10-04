"""Repeated cell values keep separate raw spans, header scan and global limits."""

import pytest

from app.contracts import FindingCategory
from app.detection.columns import detect_columns
from app.detection.rules import DetectionLimitError
from app.intake.csv_structure import parse_csv


def test_repeated_quoted_and_unquoted_cells_remain_distinct_and_keep_never_skips_header():
    source = 'ada@example.test,Other\n"ada@example.test",ada@example.test\nada@example.test,"ada@example.test"\n'
    layout = parse_csv(source, ",", "true").layout
    findings = detect_columns(source, layout, [], {FindingCategory.EMAIL}, "GB", "en", [])
    assert len(findings) == 5
    assert len({(item.span.start, item.span.end) for item in findings}) == 5
    assert all(source[item.span.start : item.span.end] == "ada@example.test" for item in findings)
    rules = [{"column": 0, "mode": "keep", "keep_reason": "intended_disclosure"}]
    kept = detect_columns(source, layout, rules, {FindingCategory.EMAIL}, "GB", "en", [])
    assert len(kept) == 3 and kept[0].span.start == 0


def test_repeated_cells_count_individually_toward_the_global_suggestion_cap():
    source = "Email,Other\n" + "ada@example.test,Unmarked\n" * 1000
    layout = parse_csv(source).layout
    assert len(detect_columns(source, layout, [], {FindingCategory.EMAIL}, "GB", "en", [])) == 1000
    source = "Email,Other\n" + "ada@example.test,ada@example.test\n" * 501
    layout = parse_csv(source).layout
    with pytest.raises(DetectionLimitError, match="too_many_suggestions"):
        detect_columns(source, layout, [], {FindingCategory.EMAIL}, "GB", "en", [])
