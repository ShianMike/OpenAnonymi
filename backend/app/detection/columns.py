"""Detect on unescaped CSV cells, then map suggestions back to raw source spans."""

from dataclasses import replace

from app.contracts import FindingCategory, SourceSpan
from app.detection.dates import format_for_span
from app.detection.rules import (
    DETECTOR_VERSION,
    MAX_SUGGESTIONS,
    DetectionLimitError,
    Suggestion,
    detect_suggestions,
)
from app.intake.csv_structure import cell_offsets


def detect_columns(source, layout, rules, categories, region, language, custom_rules):
    from app.custom_rules.matching import detect_custom

    configured = {rule["column"]: rule for rule in rules}
    # Identical logical cells have identical detector inputs within this scan.
    # Keep a bounded request-local cache; remap every occurrence independently.
    scanned_cells: dict[str, tuple[Suggestion, ...]] = {}
    result = []
    for record, row in enumerate(layout["records"]):
        for column, cell in enumerate(row):
            value, offsets = cell_offsets(source, cell)
            if not value.strip():
                continue
            rule = configured.get(column) if record or not layout["has_header"] else None
            if rule is not None and rule["mode"] == "keep":
                continue
            if rule is not None and rule["mode"] == "category":
                start = len(value) - len(value.lstrip())
                end = len(value.rstrip())
                category = FindingCategory(rule["category"])
                detected = [
                    Suggestion(
                        SourceSpan(start=start, end=end),
                        category,
                        "csv.column",
                        DETECTOR_VERSION,
                        "Column category rule; review each cell.",
                        format_for_span(value, start, end, region)
                        if category == FindingCategory.DATE
                        else None,
                    )
                ]
            else:
                detected = scanned_cells.get(value)
                if detected is None:
                    detected = tuple(
                        detect_suggestions(value, categories, region, language)
                    ) + tuple(
                        detect_custom(
                            value, [(rule.id, rule.version, rule) for rule in custom_rules]
                        )
                    )
                    if len(scanned_cells) < 128:
                        scanned_cells[value] = detected
            for suggestion in detected:
                result.append(
                    replace(
                        suggestion,
                        span=SourceSpan(
                            start=offsets[suggestion.span.start], end=offsets[suggestion.span.end]
                        ),
                    )
                )
                if len(result) > MAX_SUGGESTIONS:
                    raise DetectionLimitError("too_many_suggestions")
    return result
