"""Real file roundtrips: geometry, styles and removal of the actual hidden bytes."""

import base64
import io
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from PIL import Image, ImageChops
from pypdf import PdfReader, PdfWriter

from app.contracts import DecisionAction, SourceSpan
from app.exports.pdf import generate_layout_pdf
from app.intake.file_layout import review_file_layout, validate_file_layout
from app.intake.imports import edit_import, extract_import
from app.intake.structure import InvalidLayout
from app.intake.validation import SourceValidationError
from app.transformations.engine import ReplacementPlan, TransformFinding, transform_text
from tests.import_fixtures import pdf_sample
from tests.ocr_fixtures import scanned_pdf


def changed(imported, needle, action=DecisionAction.REDACT):
    start = imported.source.text.index(needle)
    return transform_text(
        imported.source.text,
        [
            TransformFinding(
                uuid4(),
                SourceSpan(start=start, end=start + len(needle)),
                action,
                "EMAIL_001" if action == DecisionAction.LABEL else None,
            )
        ],
    )


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_pdf_redaction_removes_pixels_and_original_objects_at_every_rotation(rotation):
    writer = PdfWriter(clone_from=io.BytesIO(pdf_sample()))
    writer.pages[0].rotate(rotation)
    writer.add_attachment("private-canary.txt", b"private attachment canary")
    buffer = io.BytesIO()
    writer.write(buffer)
    imported = extract_import("example.pdf", buffer.getvalue())
    preview = changed(imported, "nora@example.com")
    layout = review_file_layout(
        imported.layout, imported.source.text, preview.text, preview.mappings
    )
    assert len(layout["pages"][0]["regions"]) == 1
    original = Image.open(
        io.BytesIO(base64.b64decode(imported.layout["pages"][0]["image"]))
    ).convert("RGB")
    reviewed = Image.open(io.BytesIO(base64.b64decode(layout["pages"][0]["image"]))).convert("RGB")
    assert ImageChops.difference(original, reviewed).getbbox() is not None
    for region in layout["pages"][0]["regions"]:
        x, y, w, h = region["box"]
        assert reviewed.crop((x, y, x + w, y + h)).getextrema() == ((0, 0), (0, 0), (0, 0))
    payload = generate_layout_pdf(layout, datetime.now(UTC))
    reader = PdfReader(io.BytesIO(payload))
    assert reader.pages[0].extract_text() == "" and not reader.attachments
    assert not reader.metadata.author
    assert tuple(float(n) for n in reader.pages[0].mediabox[2:]) == tuple(
        layout["pages"][0]["points"]
    )
    assert b"nora@example.com" not in payload and b"private attachment canary" not in payload
    assert (
        ImageChops.difference(reader.pages[0].images[0].image.convert("RGB"), reviewed).getbbox()
        is None
    )


def test_positions_are_validated_and_source_cannot_drift_away_from_the_layout():
    imported = extract_import("example.pdf", pdf_sample())
    with pytest.raises(SourceValidationError, match="original layout"):
        edit_import(imported, imported.source.text + "new text")
    imported.layout["pages"][0]["marks"][0]["end"] = 100_001
    with pytest.raises(InvalidLayout):
        validate_file_layout(imported.layout, imported.source.text)


def test_scanned_pdf_masks_the_recognized_word_and_preserves_other_pages():
    imported = extract_import("scan.pdf", scanned_pdf(caption=True, selectable=True))
    preview = changed(imported, "nora")
    layout = review_file_layout(
        imported.layout, imported.source.text, preview.text, preview.mappings
    )
    assert len(layout["pages"]) == 2
    page = layout["pages"][0]
    assert len(page["regions"]) == 1
    start = imported.source.text.index("nora")
    word = next(mark for mark in imported.layout["pages"][0]["marks"] if mark["start"] == start)
    assert imported.source.text[word["start"]:word["end"]] == "nora@example.test"
    assert page["regions"][0]["box"] == word["box"]
    x, y, w, h = word["box"]
    with Image.open(io.BytesIO(base64.b64decode(page["image"]))) as image:
        assert image.crop((x, y, x + w, y + h)).getextrema() == ((0, 0), (0, 0), (0, 0))
    assert layout["pages"][1]["image"] == imported.layout["pages"][1]["image"]
    output = PdfReader(io.BytesIO(generate_layout_pdf(layout, datetime.now(UTC))))
    for index, page in enumerate(layout["pages"]):
        with Image.open(io.BytesIO(base64.b64decode(page["image"]))) as image:
            assert ImageChops.difference(output.pages[index].images[0].image, image).getbbox() is None
        assert not output.pages[index].extract_text()


@pytest.mark.parametrize("suffix", ["xlsx", "xls", "xlsm"])
def test_excel_formats_are_not_supported(suffix):
    with pytest.raises(SourceValidationError, match="Choose TXT"):
        extract_import("example." + suffix, b"PK synthetic unsupported workbook")


def test_txt_keeps_tabs_spaces_crlf_and_literal_markdown():
    text = "# Literal heading\r\n\tColumn A    Column B\r\n\r\n  nora@example.test  "
    imported = extract_import("example.txt", text.encode())
    assert imported.source.text == text and imported.layout["kind"] == "txt"
    assert edit_import(imported, text + "\r\n").layout["kind"] == "txt"


def test_pdf_partial_masks_and_labels_match_the_canonical_preview():
    imported = extract_import("example.pdf", pdf_sample())
    start = imported.source.text.index("nora@example.com")
    finding = TransformFinding(
        uuid4(), SourceSpan(start=start, end=start + 16), DecisionAction.REDACT, None
    )
    preview = transform_text(
        imported.source.text, [finding], ReplacementPlan({finding.finding_id: "n***@example.com"})
    )
    layout = review_file_layout(
        imported.layout, imported.source.text, preview.text, preview.mappings
    )
    page = layout["pages"][0]
    image = Image.open(io.BytesIO(base64.b64decode(page["image"]))).convert("RGB")
    x, y, w, h = page["regions"][0]["box"]
    assert image.crop((x, y, x + w, y + h)).getextrema() == ((0, 255), (0, 255), (0, 255))
    original = Image.open(
        io.BytesIO(base64.b64decode(imported.layout["pages"][0]["image"]))
    ).convert("RGB")
    assert ImageChops.difference(original, image).getbbox() is not None
    output = PdfReader(io.BytesIO(generate_layout_pdf(layout, datetime.now(UTC))))
    assert (
        ImageChops.difference(output.pages[0].images[0].image.convert("RGB"), image).getbbox()
        is None
    )
