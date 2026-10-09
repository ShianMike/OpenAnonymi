"""Closed CSV column choices; header names are protected content."""

from typing import Literal

from pydantic import Field, model_validator

from app.contracts import FindingCategory
from app.intake.csv_structure import CsvError, cell_value, normalized_header
from app.transformations.contracts import StyleChoice
from app.transformations.styles import validate_style


class ColumnRule(StyleChoice):
    column: int = Field(ge=0, le=49)
    header: str = Field(default="", max_length=1000, repr=False)
    mode: Literal["scan", "category", "keep"] = "scan"
    category: FindingCategory | None = None
    default_action: Literal["label", "redact", "keep"] = "label"
    keep_reason: Literal["false_match", "intended_disclosure"] | None = None

    @model_validator(mode="after")
    def valid_mode(self):
        if self.mode == "category":
            if self.category is None:
                raise ValueError("Choose a category for this column.")
            validate_style(self.default_action, self.style, self.style_option, self.category)
            if self.default_action == "keep" and self.keep_reason is None:
                raise ValueError("Choose a reason for Keep.")
        elif self.category is not None or self.style != "token" or self.style_option is not None:
            raise ValueError("Category and replacement styles require Category mode.")
        if self.mode == "keep" and self.keep_reason is None:
            raise ValueError("Choose a reason for Keep.")
        if self.mode != "keep" and self.default_action != "keep" and self.keep_reason is not None:
            raise ValueError("A reason applies only to Keep.")
        return self


def validate_rules(rules: list[dict]) -> list[dict]:
    if not isinstance(rules, list) or len(rules) > 50:
        raise CsvError("csv_column_rules_invalid", "Configure at most 50 CSV columns.")
    try:
        result = [ColumnRule.model_validate(rule).model_dump(mode="json") for rule in rules]
    except ValueError:
        raise CsvError(
            "csv_column_rules_invalid",
            "Choose valid CSV column modes, categories, styles and Keep reasons.",
        ) from None
    if len({rule["column"] for rule in result}) != len(result):
        raise CsvError("csv_column_rules_invalid", "Configure each column only once.")
    return sorted(result, key=lambda rule: rule["column"])


def bind_rules(rules: list[dict], source: str, layout: dict) -> list[dict]:
    result = validate_rules(rules)
    for rule in result:
        if rule["column"] >= layout["columns"]:
            raise CsvError("csv_column_rules_invalid", "A configured column is outside this CSV.")
        rule["header"] = (
            cell_value(source, layout["records"][0][rule["column"]]) if layout["has_header"] else ""
        )
    return validate_rules(result)


def match_preset(rules: list[dict], source: str, layout: dict) -> list[dict]:
    if not layout["has_header"]:
        return []
    headers = [normalized_header(cell_value(source, cell)) for cell in layout["records"][0]]
    candidates = {}
    for rule in validate_rules(rules):
        name = normalized_header(rule["header"])
        if name:
            if name in candidates:
                raise CsvError("csv_column_rules_invalid", "Preset column names must be distinct.")
            candidates[name] = rule
    result = []
    for column, header in enumerate(headers):
        if header and headers.count(header) == 1 and header in candidates:
            result.append({**candidates[header], "column": column})
    return bind_rules(result, source, layout)
