"""Bounded CSV parsing with code-point spans into the exact uploaded source.

Maps contain only syntax and positions. Unescaped values and their offset maps
are derived transiently; they never become plaintext persistence columns.
"""

import re
from bisect import bisect_left
from dataclasses import dataclass, field, replace
from typing import Literal
from unicodedata import normalize

from app.detection.dates import parse_date
from app.intake.validation import SourceValidationError, ValidatedSource, validate_source

DELIMITERS = (",", ";", "\t", "|")
Delimiter = Literal["auto", ",", ";", "\t", "|"]
Header = Literal["auto", "true", "false"]
MAX_COLUMNS = 50
MAX_DATA_ROWS = 1000
MAX_CELL_POINTS = 10000
MAX_CELLS = (MAX_DATA_ROWS + 1) * MAX_COLUMNS
NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")


class CsvError(SourceValidationError):
    """Content-free error with an explicit client-recoverable reason code."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ParsedCsv:
    source: ValidatedSource = field(repr=False)
    layout: dict = field(repr=False)


def _invalid(record: int):
    return CsvError(
        "csv_structure_invalid",
        f"CSV syntax is invalid at record {record}. Use quoted fields and doubled inner quotes.",
    )


def _tokenize(source: str, delimiter: str) -> list[list[dict]]:
    """Single bounded pass; LF and CRLF are accepted outside quoted fields."""
    records, row = [], []
    index, length = 0, len(source)
    while True:
        record = len(records) + 1
        quoted = index < length and source[index] == '"'
        if quoted:
            index += 1
        start, count = index, 0
        while index < length:
            character = source[index]
            if quoted:
                if character == '"':
                    if index + 1 < length and source[index + 1] == '"':
                        index += 2
                    else:
                        break
                else:
                    index += 1
            else:
                if character in (delimiter, "\r", "\n"):
                    break
                if character == '"':
                    raise _invalid(record)
                index += 1
            count += 1
            if count > MAX_CELL_POINTS:
                raise CsvError(
                    "csv_cell_too_large", "Each CSV cell must be 10,000 characters or fewer."
                )
        end = index
        if quoted:
            if index == length:
                raise _invalid(record)
            index += 1
            if index < length and source[index] not in (delimiter, "\r", "\n"):
                raise _invalid(record)
        row.append({"start": start, "end": end, "quoted": quoted})
        if len(row) > MAX_COLUMNS:
            raise CsvError("csv_too_many_columns", "CSV files can have at most 50 columns.")
        if index < length and source[index] == delimiter:
            index += 1
            continue
        # Python's csv.reader treats a completely blank record as zero fields.
        # Preserve that behavior so a blank record cannot silently shift cells.
        if len(row) == 1 and start == end and not quoted:
            row = []
        records.append(row)
        if len(records) > MAX_DATA_ROWS + 1:
            raise CsvError("csv_too_many_rows", "CSV files can have at most 1,000 data rows.")
        if index == length:
            break
        if source[index] == "\r":
            if index + 1 == length or source[index + 1] != "\n":
                raise _invalid(record)
            index += 2
        else:
            index += 1
        if index == length:
            break
        row = []
    width = len(records[0])
    for record, cells in enumerate(records, 1):
        if len(cells) != width:
            raise CsvError("csv_ragged_rows", f"CSV record {record} has a different column count.")
    if not width:
        raise _invalid(1)
    return records


def cell_value(source: str, cell: dict) -> str:
    raw = source[cell["start"] : cell["end"]]
    return raw.replace('""', '"') if cell["quoted"] else raw


def cell_offsets(source: str, cell: dict) -> tuple[str, tuple[int, ...]]:
    """Each unescaped code-point boundary maps to its exact raw-source boundary."""
    if not cell["quoted"]:
        return cell_value(source, cell), tuple(range(cell["start"], cell["end"] + 1))
    pieces, boundaries = [], [cell["start"]]
    index = cell["start"]
    while index < cell["end"]:
        pieces.append(source[index])
        index += 2 if source[index] == '"' else 1
        boundaries.append(index)
    return "".join(pieces), tuple(boundaries)


def values(source: str, layout: dict) -> list[list[str]]:
    return [[cell_value(source, cell) for cell in row] for row in layout["records"]]


def normalized_header(value: str) -> str:
    return normalize("NFC", value).strip().casefold()


def _has_header(source: str, first: list[dict]) -> bool:
    names = [cell_value(source, cell).strip() for cell in first]
    distinct = {normalized_header(value) for value in names}
    return (
        all(names)
        and len(distinct) == len(names)
        and not any(NUMBER.fullmatch(value) or parse_date(value, "PH") for value in names)
    )


def parse_csv(
    source: str, delimiter: Delimiter = "auto", header: Header = "auto", *, remove_bom=True
) -> ParsedCsv:
    if delimiter not in ("auto", *DELIMITERS) or header not in ("auto", "true", "false"):
        raise CsvError(
            "csv_structure_invalid", "Choose a supported CSV delimiter and header setting."
        )
    validated = validate_source(source)
    if not remove_bom and validated.initial_bom_removed:
        validated = replace(
            validated,
            text=source,
            utf8_bytes=len(source.encode("utf-8")),
            code_points=len(source),
            initial_bom_removed=False,
        )
    text = validated.text
    if delimiter == "auto":
        records, failures = None, []
        for candidate in DELIMITERS:
            try:
                parsed = _tokenize(text, candidate)
            except CsvError as exc:
                failures.append(exc)
                continue
            if len(parsed[0]) >= 2:
                delimiter, records = candidate, parsed
                break
        if records is None:
            limits = [
                exc
                for exc in failures
                if exc.code in ("csv_cell_too_large", "csv_too_many_columns", "csv_too_many_rows")
            ]
            if limits:
                raise limits[0]
            raise CsvError(
                "csv_delimiter_unknown",
                "CSV delimiter could not be detected. Choose comma, semicolon, tab, or pipe.",
            )
    else:
        records = _tokenize(text, delimiter)
    has_header = _has_header(text, records[0]) if header == "auto" else header == "true"
    if len(records) - int(has_header) > MAX_DATA_ROWS:
        raise CsvError("csv_too_many_rows", "CSV files can have at most 1,000 data rows.")
    return ParsedCsv(
        validated,
        {
            "v": 1,
            "delimiter": delimiter,
            "has_header": has_header,
            "columns": len(records[0]),
            "records": records,
        },
    )


def validate_csv_layout(layout: dict, source: str) -> None:
    """Closed schema plus exact reconstruction prevents stale or content-bearing maps."""
    invalid = CsvError("csv_structure_invalid", "Protected CSV structure is invalid.")
    if not isinstance(layout, dict) or set(layout) != {
        "v",
        "delimiter",
        "has_header",
        "columns",
        "records",
    }:
        raise invalid
    if type(layout["v"]) is not int or layout["v"] != 1 or type(layout["columns"]) is not int:
        raise invalid
    if layout["delimiter"] not in DELIMITERS or type(layout["has_header"]) is not bool:
        raise invalid
    if type(layout["records"]) is not list or not 1 <= len(layout["records"]) <= MAX_DATA_ROWS + 1:
        raise invalid
    for row in layout["records"]:
        if type(row) is not list or not 1 <= len(row) <= MAX_COLUMNS:
            raise invalid
        for cell in row:
            if not isinstance(cell, dict) or set(cell) != {"start", "end", "quoted"}:
                raise invalid
            if (
                type(cell["start"]) is not int
                or type(cell["end"]) is not int
                or type(cell["quoted"]) is not bool
            ):
                raise invalid
            if not 0 <= cell["start"] <= cell["end"] <= len(source):
                raise invalid
    expected = parse_csv(
        source, layout["delimiter"], "true" if layout["has_header"] else "false", remove_bom=False
    )
    if expected.source.text != source or expected.layout != layout:
        raise invalid


def span_cell(layout: dict, source: str, start: int, end: int) -> tuple[int, int, dict]:
    """Return the containing cell, rejecting syntax crossings and split escapes."""
    for record, row in enumerate(layout["records"]):
        for column, cell in enumerate(row):
            if cell["start"] <= start < end <= cell["end"]:
                if cell["quoted"]:
                    _, offsets = cell_offsets(source, cell)
                    for offset in (start, end):
                        index = bisect_left(offsets, offset)
                        if index == len(offsets) or offsets[index] != offset:
                            raise CsvError(
                                "finding_splits_escape",
                                "A finding cannot split a doubled CSV quote.",
                            )
                return record, column, cell
    raise CsvError("finding_crosses_block", "A finding must stay inside one CSV cell.")


def value_span(source: str, cell: dict, start: int, end: int) -> tuple[int, int]:
    """Translate an already cell-bounded raw finding into unescaped positions."""
    _, offsets = cell_offsets(source, cell)
    left, right = bisect_left(offsets, start), bisect_left(offsets, end)
    if (
        left >= len(offsets)
        or right >= len(offsets)
        or offsets[left] != start
        or offsets[right] != end
    ):
        raise CsvError("finding_splits_escape", "A finding cannot split a doubled CSV quote.")
    return left, right
