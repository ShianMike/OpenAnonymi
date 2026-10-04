"""Actual native local OCR, image/PDF bounds and pre-save structure corrections."""

import pytest

from app.intake.imports import edit_import, extract_import
from app.intake.validation import SourceValidationError
from tests.import_fixtures import docx_sample
from tests.ocr_fixtures import TEXT, image_sample, inline_scan_pdf, scanned_pdf


@pytest.mark.parametrize(
    "format,suffix", [("PNG", "png"), ("JPEG", "jpg"), ("TIFF", "tiff"), ("WEBP", "webp")]
)
def test_real_image_ocr_and_metadata_omission(format, suffix):
    imported = extract_import("fictional." + suffix, image_sample(format))
    assert imported.format == "image" and imported.pages == 1
    assert imported.source.text == TEXT
    assert "metadata-privacy-canary" not in imported.source.text
    assert "Local English OCR" in imported.notes[0]


def test_real_scanned_pdf_and_selectable_caption_are_read_in_page_order():
    imported = extract_import("fictional.pdf", scanned_pdf(caption=True, selectable=True))
    assert imported.format == "pdf" and imported.pages == 2
    assert (
        imported.source.text
        == "Selectable caption above scan\n\n" + TEXT + "\n\nSelectable final page after scan"
    )
    assert "metadata-privacy-canary" not in imported.source.text
    assert any("1 scanned" in note for note in imported.notes)


def test_actual_multiframe_tiff_text_order():
    imported = extract_import("scan.tif", image_sample("TIFF", frames=2))
    assert imported.pages == 2 and imported.source.text == TEXT + "\n\n" + TEXT


@pytest.mark.parametrize("in_form", [False, True])
def test_inline_image_with_selectable_caption_never_loses_scanned_private_text(in_form):
    imported = extract_import("inline.pdf", inline_scan_pdf(in_form=in_form))
    assert imported.source.text.startswith("Selectable caption above scan")
    assert TEXT in imported.source.text
    assert "metadata-privacy-canary" not in imported.source.text
    assert any("Local English OCR" in note for note in imported.notes)


@pytest.mark.parametrize(
    "kind", ["image_pixels", "pdf_pixels", "tiff_pages", "pdf_pages", "empty", "fake_image"]
)
def test_real_decoder_limits_and_honest_empty_errors(kind, caplog):
    filename, payload, expected = {
        "image_pixels": lambda: ("scan.png", image_sample(size=(6000, 2000)), "pixel"),
        "pdf_pixels": lambda: ("scan.pdf", scanned_pdf(wide=True), "pixel"),
        "tiff_pages": lambda: ("scan.tif", image_sample("TIFF", frames=11), "10 scanned"),
        "pdf_pages": lambda: ("scan.pdf", scanned_pdf(pages=11), "10 scanned"),
        "empty": lambda: ("scan.png", image_sample(text=""), "no readable"),
        "fake_image": lambda: ("scan.png", b"Sensitive-fake-image-source", "readable PNG"),
    }[kind]()
    with pytest.raises(SourceValidationError, match=expected) as failure:
        extract_import(filename, payload)
    assert "Sensitive-fake-image-source" not in str(failure.value) + caplog.text


def test_markdown_is_literal_utf8_text_and_editor_validates_source():
    text = "# Fictional 😀\n<script>alert('literal')</script>\n![No request](https://example.test/scan)"
    imported = extract_import("note.md", text.encode())
    assert imported.format == "md" and imported.source.text == text
    assert edit_import(imported, "Edited 😀\r\ntext").source.text == "Edited 😀\r\ntext"
    for invalid in ("", "x" * 100001, "control\x00source"):
        with pytest.raises(SourceValidationError):
            edit_import(imported, invalid)
    with pytest.raises(SourceValidationError, match="UTF-8"):
        extract_import("note.md", b"\xff")


def test_csv_correction_rebuilds_map_and_rejects_changed_columns():
    imported = extract_import("cells.csv", b"Name,Value\nFictional,nora@example.test\n")
    changed = edit_import(imported, "Name,Value\nEdited,corrected@example.test\n")
    assert changed.source.text.endswith("corrected@example.test\n")
    assert changed.layout["columns"] == 2 and changed.layout != imported.layout
    with pytest.raises(SourceValidationError):
        edit_import(imported, "Name,Value,Extra\nEdited,corrected@example.test,third\n")


def test_word_correction_realigns_or_simplifies_instead_of_retaining_stale_spans():
    imported = extract_import("note.docx", docx_sample())
    edited = edit_import(imported, "New fictional paragraph")
    assert edited.source.text == "New fictional paragraph" and edited.layout is None
