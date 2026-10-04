import csv
import io
import json
import random
from copy import deepcopy

import pytest

from app.intake.csv_structure import (
    CsvError,
    cell_offsets,
    parse_csv,
    span_cell,
    validate_csv_layout,
    value_span,
    values,
)
from app.intake.validation import SourceValidationError


@pytest.mark.parametrize("delimiter", [",", ";", "\t", "|"])
@pytest.mark.parametrize("newline", ["\r\n", "\n"])
def test_offsets_and_exact_unescaped_values_match_standard_reader(delimiter, newline):
    matrix = [
        ["Name", "Notes", "Other"],
        ["Nóra 李", 'Said "hello"', ""],
        ["Ada", "two\r\nlines\nand a\ttab", ",;|"],
        ["", "", "tail"],
    ]
    stream = io.StringIO(newline="")
    csv.writer(stream, delimiter=delimiter, lineterminator=newline).writerows(matrix)
    source = stream.getvalue()
    parsed = parse_csv(source, delimiter)
    assert parsed.source.text == source
    assert values(source, parsed.layout) == matrix
    assert values(source, parsed.layout) == list(
        csv.reader(io.StringIO(source, newline=""), delimiter=delimiter, strict=True)
    )
    assert parsed.layout["has_header"]
    assert "Nóra" not in json.dumps(parsed.layout)
    validate_csv_layout(parsed.layout, source)
    for record, row in enumerate(parsed.layout["records"]):
        for column, cell in enumerate(row):
            value, offsets = cell_offsets(source, cell)
            assert value == matrix[record][column] and len(offsets) == len(value) + 1
            assert offsets[0] == cell["start"] and offsets[-1] == cell["end"]
            for i, character in enumerate(value):
                raw = source[offsets[i] : offsets[i + 1]]
                assert raw == ('""' if character == '"' and cell["quoted"] else character)
                assert value_span(source, cell, offsets[i], offsets[i + 1]) == (i, i + 1)


def test_delimiter_precedence_unknown_and_ragged_record_number_only():
    assert parse_csv("a,b;c\n1,2;3\n").layout["delimiter"] == ","
    for delimiter in (";", "\t", "|"):
        assert (
            parse_csv(f"Name{delimiter}City\nAda{delimiter}Oslo").layout["delimiter"] == delimiter
        )
    with pytest.raises(CsvError) as unknown:
        parse_csv("Single\nValue")
    assert unknown.value.code == "csv_delimiter_unknown"
    assert values("Single\nValue", parse_csv("Single\nValue", ",", "false").layout) == [
        ["Single"],
        ["Value"],
    ]
    with pytest.raises(CsvError) as ragged:
        parse_csv("Name,City\nPRIVATE_VALUE\n", ",")
    assert ragged.value.code == "csv_ragged_rows" and "record 2" in str(ragged.value)
    assert "PRIVATE_VALUE" not in str(ragged.value)


@pytest.mark.parametrize(
    "first,expected",
    [
        ("Name,City", True),
        ("Name, name", False),
        ("Name,", False),
        ("123,City", False),
        ("-.3e+2,City", False),
        ("2024-02-29,City", False),
        ("March 4 2024,City", False),
        ("2024-02-30,City", True),
        ("École,École", False),
    ],
)
def test_header_detection_is_content_aware_without_mutating_source(first, expected):
    source = first + "\nAda,Oslo\n"
    parsed = parse_csv(source, ",")
    assert parsed.source.text == source and parsed.layout["has_header"] is expected
    assert parse_csv(source, ",", "true").layout["has_header"]
    assert not parse_csv(source, ",", "false").layout["has_header"]


@pytest.mark.parametrize("source", ['a,"unfinished', 'a,b"c\n', 'a,"b" x\n', "a,b\rc,d", 'a,"b""'])
def test_strict_syntax_errors_are_content_free(source):
    with pytest.raises(CsvError) as error:
        parse_csv(source, ",")
    assert error.value.code == "csv_structure_invalid" and source not in str(error.value)


def test_cell_boundaries_and_both_sides_of_escaped_quotes():
    source = 'Name,Notes\r\nAda,"Said ""hi""\nthen left"\r\n'
    layout = parse_csv(source).layout
    cell = layout["records"][1][1]
    assert span_cell(layout, source, cell["start"], cell["end"])[:2] == (1, 1)
    for quote in [source.index('""'), source.rindex('""')]:
        for start, end in ((quote, quote + 1), (quote + 1, quote + 2)):
            with pytest.raises(CsvError) as error:
                span_cell(layout, source, start, end)
            assert error.value.code == "finding_splits_escape"
        assert span_cell(layout, source, quote, quote + 2)[:2] == (1, 1)
    for start, end in (
        (cell["start"] - 1, cell["end"]),
        (0, cell["end"]),
        (cell["start"], cell["end"] + 1),
    ):
        with pytest.raises(CsvError) as error:
            span_cell(layout, source, start, end)
        assert error.value.code == "finding_crosses_block"


def test_full_limits_include_50050_cells_and_1000_data_rows():
    source = ",".join(f"Col{i}" for i in range(50)) + "\n" + ("," * 49 + "\n") * 1000
    parsed = parse_csv(source)
    assert parsed.layout["columns"] == 50 and len(parsed.layout["records"]) == 1001
    assert sum(map(len, parsed.layout["records"])) == 50050
    validate_csv_layout(parsed.layout, source)
    cases = [
        (",".join(str(i) for i in range(51)), "csv_too_many_columns"),
        ("Name,City\n" + "a,b\n" * 1001, "csv_too_many_rows"),
        ("1,2\n" * 1001, "csv_too_many_rows"),
        ('"' + "a" * 10001 + '",b', "csv_cell_too_large"),
    ]
    for source, code in cases:
        with pytest.raises(CsvError) as error:
            parse_csv(source, ",")
        assert error.value.code == code
    cell = '"' + '""' * 10000 + '",b'
    assert len(values(cell, parse_csv(cell, ",", "false").layout)[0][0]) == 10000


def test_bom_unicode_empty_and_global_limits():
    parsed = parse_csv("\ufeffName,City\r\n李,Oslo\r\n")
    assert parsed.source.initial_bom_removed and not parsed.source.text.startswith("\ufeff")
    assert parse_csv("\ufeff\ufeffName,City").source.text.startswith("\ufeff")
    for source in ("", " \n", "a,\x00b", "a,\ud800", "a" * 100001):
        with pytest.raises(SourceValidationError):
            parse_csv(source, ",")
    assert values('"",', parse_csv('"",', ",", "false").layout) == [["", ""]]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda x: x.update(v=True),
        lambda x: x.update(columns=True),
        lambda x: x.update(extra="PRIVATE_VALUE"),
        lambda x: x.update(has_header=1),
        lambda x: x["records"][0][0].update(start=True),
        lambda x: x["records"][0][0].update(text="PRIVATE_VALUE"),
        lambda x: x["records"][0][0].update(end=1),
    ],
)
def test_closed_map_validation_rejects_stale_fields_and_bool_offsets(mutation):
    source = "Name,City\nAda,Oslo"
    layout = deepcopy(parse_csv(source).layout)
    mutation(layout)
    with pytest.raises(CsvError):
        validate_csv_layout(layout, source)


def test_owned_generated_records_cross_checked_with_csv_reader():
    rng = random.Random(20261004)
    alphabet = 'a李 é,;|\t\r\n"'
    for delimiter in (",", ";", "\t", "|"):
        for _ in range(25):
            matrix = [
                ["".join(rng.choice(alphabet) for _ in range(rng.randrange(16))) for _ in range(4)]
                for _ in range(6)
            ]
            stream = io.StringIO(newline="")
            csv.writer(stream, delimiter=delimiter, quoting=csv.QUOTE_ALL).writerows(matrix)
            source = stream.getvalue()
            parsed = parse_csv(source, delimiter, "false")
            assert (
                values(source, parsed.layout)
                == matrix
                == list(
                    csv.reader(io.StringIO(source, newline=""), delimiter=delimiter, strict=True)
                )
            )
