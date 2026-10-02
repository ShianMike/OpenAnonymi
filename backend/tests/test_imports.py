import io
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app.intake.imports import MAX_FILE_BYTES, extract_import
from app.intake.validation import SourceValidationError
from tests.import_fixtures import docx_sample, pdf_sample


def test_real_docx_order_unicode_headers_tables_and_metadata_omitted():
    imported = extract_import("a-fictional-document.docx", docx_sample())
    assert imported.format == "docx" and imported.pages is None
    assert (
        imported.source.text
        == "Fictional research note\n😀 Nora Caldwell; nora@example.com; café and 東京.\nCase\tCASE-123456\nA final fictional paragraph.\nFictional footer"
    )
    assert "metadata author" not in imported.source.text
    assert imported.notes


def test_pdf_selectable_text_and_honest_failure():
    imported = extract_import("sample.pdf", pdf_sample())
    assert imported.pages == 1 and "nora@example.com" in imported.source.text
    assert "metadata" not in imported.source.text
    for content, message in [
        (pdf_sample(empty=True), "OCR"),
        (pdf_sample(encrypted=True), "encrypted"),
        (pdf_sample(pages=101, empty=True), "100 pages"),
    ]:
        with pytest.raises(SourceValidationError, match=message):
            extract_import("sample.pdf", content)
    with pytest.raises(SourceValidationError):
        extract_import("inflated.pdf", pdf_sample(inflated=True))


def test_bounds_corruption_zip_expansion_and_txt_contract():
    for filename, content in [
        ("sample.pdf", b"not pdf"),
        ("sample.docx", b"not zip"),
        ("sample.pdf", b"%PDF-" + b"x" * MAX_FILE_BYTES),
        ("sample.xls", b"not supported"),
    ]:
        with pytest.raises(SourceValidationError):
            extract_import(filename, content)
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", "x" * 17_000_000)
        archive.writestr("[Content_Types].xml", "x")
    with pytest.raises(SourceValidationError, match="expands"):
        extract_import("bomb.docx", buffer.getvalue())
    assert extract_import("sample.txt", "😀\r\n東京".encode()).source.text == "😀\r\n東京"
    with pytest.raises(SourceValidationError, match="UTF-8"):
        extract_import("sample.txt", b"\xff")
