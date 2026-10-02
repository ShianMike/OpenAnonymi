"""Fixed-width templates and escaped literals; no executable user regex."""

import re
from uuid import UUID

from app.contracts import FindingCategory, SourceSpan
from app.custom_rules.contracts import RuleInput
from app.detection.rules import MAX_SUGGESTIONS, DetectionLimitError, Suggestion


def matches(source: str, rule: RuleInput, limit: int = MAX_SUGGESTIONS):
    expression = rule.expression
    if rule.kind == "identifier":
        pattern = "".join(
            "[0-9]"
            if character == "#"
            else "[A-Za-z]"
            if character == "@"
            else re.escape(character)
            for character in expression
        )
    else:
        pattern = re.escape(expression)
    if rule.whole_word:
        pattern = rf"(?<!\w){pattern}(?!\w)"
    result: list[SourceSpan] = []
    for match in re.finditer(pattern, source, 0 if rule.case_sensitive else re.IGNORECASE):
        if len(result) >= limit:
            raise DetectionLimitError("too_many_suggestions")
        result.append(SourceSpan(start=match.start(), end=match.end()))
    return result


def detect_custom(source: str, rules: list[tuple[UUID, int, RuleInput]]) -> list[Suggestion]:
    result = []
    for rule_id, version, rule in rules:
        for span in matches(source, rule):
            if len(result) >= MAX_SUGGESTIONS:
                raise DetectionLimitError("too_many_suggestions")
            result.append(
                Suggestion(
                    span,
                    FindingCategory(rule.category),
                    f"workspace.{rule_id}",
                    str(version),
                    "Matches a workspace phrase rule."
                    if rule.kind == "phrase"
                    else "Matches a workspace identifier template (# digit, @ letter).",
                )
            )
    return result
