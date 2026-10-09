import csv
import io
from uuid import uuid4

import pytest

from app.contracts import DecisionAction, SourceSpan
from app.exports.csv_export import FORMULA_LEADS, generate_csv
from app.intake.csv_review import logical_finding_values, reviewed_cells
from app.intake.csv_structure import parse_csv
from app.transformations.engine import ReplacementPlan, TransformFinding, transform_text


@pytest.mark.parametrize("delimiter", [",", ";", "\t", "|"])
def test_formula_safe_and_unmodified_round_trip_all_leads_quotes_unicode_newlines(delimiter):
    records = [
        [character + 'SUM(1,2)";|value' for character in "=+-@\t\r\n＝＋－＠"],
        ["李, Oslo", 'Said "hi"', "two\r\nlines", "", " safe", "'already quoted", "  =literal"],
    ]
    safe = generate_csv(records, delimiter)
    exact = generate_csv(records, delimiter, "unmodified")
    assert safe.payload.startswith(b"\xef\xbb\xbf") and safe.prefixed_cells == 11
    assert not exact.payload.startswith(b"\xef\xbb\xbf") and exact.prefixed_cells == 0
    read_safe = list(
        csv.reader(io.StringIO(safe.payload.decode("utf-8-sig"), newline=""), delimiter=delimiter)
    )
    read_exact = list(
        csv.reader(io.StringIO(exact.payload.decode("utf-8"), newline=""), delimiter=delimiter)
    )
    assert read_exact == records
    assert read_safe == [
        ["'" + value if value and value[0] in FORMULA_LEADS else value for value in row]
        for row in records
    ]
    assert exact.payload.endswith(b"\r\n") and exact.payload.startswith(b'"')


def test_canonical_mapping_replacement_quotes_are_ordinary_cell_text():
    source = 'Name,Notes\r\n"Nora ""Q""","Said ""hello""\nthere"\r\n'
    layout = parse_csv(source).layout
    finding_id = uuid4()
    cell = layout["records"][1][0]
    finding = TransformFinding(
        finding_id,
        SourceSpan(start=cell["start"], end=cell["end"]),
        DecisionAction.LABEL,
        "PERSON_001",
    )
    logical = logical_finding_values(source, layout, [(finding_id, cell["start"], cell["end"])])
    assert logical[finding_id] == 'Nora "Q"'
    replacement = 'Fictional "Q", Inc; |'
    preview = transform_text(source, [finding], ReplacementPlan({finding_id: replacement}))
    cells = reviewed_cells(source, layout, preview.text, preview.mappings)
    assert cells == (("Name", "Notes"), (replacement, 'Said "hello"\nthere'))
    payload = generate_csv(cells, ",", "unmodified").payload
    assert list(csv.reader(io.StringIO(payload.decode(), newline=""))) == [
        list(row) for row in cells
    ]
    assert (
        preview.text[preview.mappings[0].preview_span.start : preview.mappings[0].preview_span.end]
        == replacement
    )
