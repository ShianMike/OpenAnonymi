"""Exact Unicode spans and bounded rule behavior over synthetic examples."""

import pytest

from app.contracts import FindingCategory
from app.detection.rules import DetectionLimitError, detect_suggestions


def test_email_and_phone_spans_preserve_unicode_and_repeated_occurrences():
    source = "😀 Alice: alice@example.com; phone 650-253-2222. Again alice@example.com!"
    suggestions = detect_suggestions(source, {FindingCategory.EMAIL, FindingCategory.PHONE}, "US")
    assert [
        (item.category.value, source[item.span.start : item.span.end]) for item in suggestions
    ] == [
        ("email", "alice@example.com"),
        ("phone", "650-253-2222"),
        ("email", "alice@example.com"),
    ]
    assert suggestions[0].span.start == source.index("alice@example.com")
    assert suggestions[0].span.start == 9
    assert all(item.rule_id and item.rule_version and item.reason for item in suggestions)


def test_region_and_categories_control_suggestions():
    source = "Email test@example.com; local 0917 123 4567; international +44 20 8366 1177."
    ph = detect_suggestions(source, {FindingCategory.PHONE}, "PH")
    assert [source[item.span.start : item.span.end] for item in ph] == [
        "0917 123 4567",
        "+44 20 8366 1177",
    ]
    us = detect_suggestions(source, {FindingCategory.PHONE}, "US")
    assert "0917 123 4567" not in [source[item.span.start : item.span.end] for item in us]
    email_only = detect_suggestions(source, {FindingCategory.EMAIL}, "PH")
    assert [item.category for item in email_only] == [FindingCategory.EMAIL]
    assert detect_suggestions(source, set(), "PH") == []


def test_long_digits_are_not_phone_suggestions_and_limits_are_explicit():
    source = "Reference 1234567890123456789012345. Call 650-253-2222."
    suggestions = detect_suggestions(source, {FindingCategory.PHONE}, "US")
    assert [source[item.span.start : item.span.end] for item in suggestions] == ["650-253-2222"]
    with pytest.raises(DetectionLimitError, match="too_many_phone_candidates"):
        detect_suggestions("1" * 20_001, {FindingCategory.PHONE}, "US")
    with pytest.raises(ValueError, match="region"):
        detect_suggestions("Call me", {FindingCategory.PHONE}, "ZZ")


def test_email_punctuation_boundaries_and_malformed_local_part():
    source = "(a.b+tag@example.co.uk), bad..dots@example.com; x@example.invalid!"
    suggestions = detect_suggestions(source, {FindingCategory.EMAIL}, "US")
    assert [source[item.span.start : item.span.end] for item in suggestions] == [
        "a.b+tag@example.co.uk",
        "x@example.invalid",
    ]


def test_markdown_email_wrappers_and_log_assignments_preserve_exact_spans():
    source = (
        "😀 Prepared by (`maya.ellison@example.com`)\n"
        "**billing@example.com** and *billing@example.com*\n"
        "```text\nuser=jordan.avery@example.net\n```\n"
        "![image](portrait@2x.png) bad..dots@example.com"
    )
    found = detect_suggestions(source, {FindingCategory.EMAIL}, "PH")
    assert [source[item.span.start:item.span.end] for item in found] == [
        "maya.ellison@example.com", "billing@example.com", "billing@example.com",
        "jordan.avery@example.net",
    ]
    assert found[0].span.start == source.index("maya.ellison@example.com")
