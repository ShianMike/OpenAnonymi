"""Inspect real generated PDF streams, fonts, neutral metadata and resource limits."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from io import BytesIO
from threading import Event

import pypdfium2
import pytest
from pypdf import PdfReader

from app.exports import pdf as output


def read(payload):
    reader = PdfReader(BytesIO(payload))
    # PDFium also checks actual rendered text order after mixed RTL/LTR paragraphs.
    # pypdf 6.19 drops a leading neutral character after an RTL paragraph here.
    with pypdfium2.PdfDocument(payload) as document:
        paragraphs = []
        for index in range(len(document)):
            page = document[index]
            text = page.get_textpage()
            try:
                paragraphs.append(text.get_text_range().replace("\r\n", "\n"))
            finally:
                text.close()
                page.close()
    return reader, "\n".join(paragraphs)


def test_real_unicode_pdf_has_canonical_text_and_no_active_or_original_metadata():
    text = "Fictional 😀 東京 café Ελληνικά\nनमस्ते\nשלום\nمرحبا\n<literal> & EMAIL_001"
    payload = output.generate_pdf(text, datetime.now(UTC))
    reader, extracted = read(payload)
    assert extracted == text
    assert payload.startswith(b"%PDF-") and len(payload) < 100000
    assert reader.metadata.title == "Reviewed document"
    assert reader.metadata.producer == "OpenAnonymi"
    assert not reader.metadata.author
    root = reader.trailer["/Root"]
    assert not any(
        key in root for key in ("/OpenAction", "/AA", "/AcroForm", "/Names", "/Metadata")
    )
    assert all("/Annots" not in page for page in reader.pages)
    assert reader.attachments == {}


@pytest.mark.parametrize("prefix", ["مرحبا", "😀 東京"])
def test_fallback_only_paragraph_then_literal_punctuation_retains_correct_font(prefix):
    text = prefix + "\n<literal> & EMAIL_001"
    _, extracted = read(output.generate_pdf(text, datetime.now(UTC)))
    assert extracted == text


def test_long_pdf_wraps_and_paginates_without_losing_reviewed_words():
    text = "\n".join(
        f"Fictional row {index:04d}: EMAIL_001 " + "reviewed " * 12 for index in range(120)
    )
    reader, extracted = read(output.generate_pdf(text, datetime.now(UTC)))
    assert 2 <= len(reader.pages) < output.MAX_PAGES
    assert extracted.split() == text.split()


def test_unsupported_glyph_fails_closed_without_printing_source(caplog):
    source = "Sensitive-canary-UNSUPPORTED \U0010ffff"
    with pytest.raises(output.PdfUnavailable) as error:
        output.generate_pdf(source, datetime.now(UTC))
    assert "Download TXT or Word" in str(error.value)
    assert "Sensitive-canary" not in str(error.value) + caplog.text


def test_page_limit_is_enforced_during_actual_generation(monkeypatch):
    monkeypatch.setattr(output, "MAX_PAGES", 1)
    with pytest.raises(output.PdfUnavailable, match="page limit"):
        output.generate_pdf("Reviewed paragraph.\n" * 100, datetime.now(UTC))


def test_output_byte_limit_fails_closed(monkeypatch):
    monkeypatch.setattr(output, "MAX_PDF_BYTES", 1)
    with pytest.raises(output.PdfUnavailable, match="size limit"):
        output.generate_pdf("Reviewed text.", datetime.now(UTC))


def test_overlapping_real_pdf_render_is_bounded_and_slot_released(monkeypatch):
    entered, release = Event(), Event()
    original = output.ReviewedPDF.multi_cell

    def block_first(pdf, *args, **kwargs):
        entered.set()
        assert release.wait(10), "Concurrent PDF check timed out."
        return original(pdf, *args, **kwargs)

    monkeypatch.setattr(output.ReviewedPDF, "multi_cell", block_first)
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(output.generate_pdf, "Reviewed first.", datetime.now(UTC))
        try:
            assert entered.wait(10), "Actual PDF render never started."
            with pytest.raises(output.PdfUnavailable, match="busy"):
                output.generate_pdf("Concurrent source canary.", datetime.now(UTC))
        finally:
            release.set()
        assert read(first.result(timeout=10))[1] == "Reviewed first."
    assert read(output.generate_pdf("Reviewed next.", datetime.now(UTC)))[1] == "Reviewed next."
