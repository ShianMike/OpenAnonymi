"""Exact reviewed-output bytes and source-to-preview offset mapping."""

from uuid import UUID

import pytest

from app.contracts import DecisionAction, SourceSpan
from app.transformations.engine import InvalidTransformation, TransformFinding, transform_text


def marked(
    number: int, start: int, end: int, action: DecisionAction | None, label: str | None = None
) -> TransformFinding:
    return TransformFinding(UUID(int=number), SourceSpan(start=start, end=end), action, label)


def test_ordered_replacement_preserves_unaffected_unicode_and_line_endings():
    source = "😀 Ada met Ada.\r\nA\u0301: ada@example.com!"
    first = source.index("Ada")
    second = source.index("Ada", first + 1)
    combining = source.index("A\u0301")
    email = source.index("ada@example.com")
    result = transform_text(
        source,
        [
            marked(2, second, second + 3, DecisionAction.REDACT),
            marked(1, first, first + 3, DecisionAction.LABEL, "PERSON_001"),
            marked(4, email, email + len("ada@example.com"), DecisionAction.REDACT),
            marked(3, combining, combining + 2, DecisionAction.KEEP),
        ],
    )
    expected = "😀 PERSON_001 met [REDACTED].\r\nA\u0301: [REDACTED]!"
    assert result.text == expected
    assert result.complete
    assert result.unresolved_ids == ()
    assert [item.finding_id.int for item in result.mappings] == [1, 2, 3, 4]
    assert result.mappings[0].preview_span == SourceSpan(start=2, end=12)
    assert result.mappings[1].preview_span.start == expected.index("[REDACTED]")
    assert result.mappings[3].preview_span.start == expected.index("[REDACTED]", 20)


def test_unresolved_repeated_token_remains_visible_and_adjacent_spans_have_no_gap():
    source = "Ada Ada"
    result = transform_text(
        source,
        [
            marked(1, 0, 3, DecisionAction.LABEL, "PERSON_001"),
            marked(2, 4, 7, None),
        ],
    )
    assert result.text == "PERSON_001 Ada"
    assert result.unresolved_ids == (UUID(int=2),)
    assert result.mappings[1].preview_span == SourceSpan(start=11, end=14)
    adjacent = transform_text(
        "AB",
        [
            marked(3, 0, 1, DecisionAction.LABEL, "PERSON_002"),
            marked(4, 1, 2, DecisionAction.REDACT),
        ],
    )
    assert adjacent.text == "PERSON_002[REDACTED]"
    assert adjacent.mappings[1].preview_span.start == len("PERSON_002")


def test_overlaps_and_missing_label_fail_before_output_is_available():
    with pytest.raises(InvalidTransformation, match="intersecting"):
        transform_text(
            "Alice",
            [marked(1, 0, 3, DecisionAction.REDACT), marked(2, 2, 5, DecisionAction.KEEP)],
        )
    with pytest.raises(InvalidTransformation, match="no group label"):
        transform_text("Alice", [marked(1, 0, 5, DecisionAction.LABEL)])
