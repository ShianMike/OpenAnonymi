"""Correction previews use actual bounded OCR output, without container metadata."""

import base64
import io
import os

import pytest
from PIL import Image

from app.intake.imports import extract_import
from app.intake.ocr_worker import MAX_PREVIEW_BYTES, page_preview
from tests.ocr_fixtures import image_sample, scanned_pdf


def assert_preview(page):
    assert page.data_url.startswith("data:image/jpeg;base64,")
    content = base64.b64decode(page.data_url.split(",", 1)[1], validate=True)
    assert len(content) <= MAX_PREVIEW_BYTES
    assert b"metadata-privacy-canary" not in content
    with Image.open(io.BytesIO(content)) as image:
        assert image.format == "JPEG" and image.mode == "RGB"
        assert max(image.size) <= 1600 and not image.getexif()


@pytest.mark.parametrize("format,suffix,frames", [
    ("PNG", "png", 1), ("JPEG", "jpg", 1), ("WEBP", "webp", 1), ("TIFF", "tiff", 2),
])
def test_actual_image_previews_follow_frame_order_and_are_opt_in(format, suffix, frames):
    content = image_sample(format, frames=frames)
    imported = extract_import("scan." + suffix, content, include_previews=True)
    assert "nora@example.test" in imported.source.text
    assert [page.page_number for page in imported.page_previews] == list(range(1, frames + 1))
    for page in imported.page_previews:
        assert_preview(page)
    assert extract_import("scan." + suffix, content).page_previews == ()


def test_mixed_pdf_previews_include_only_scanned_pages_in_document_order():
    imported = extract_import("scan.pdf", scanned_pdf(pages=2, selectable=True), include_previews=True)
    assert imported.pages == 3
    assert [page.page_number for page in imported.page_previews] == [1, 2]
    assert "Selectable final page after scan" in imported.source.text
    for page in imported.page_previews:
        assert_preview(page)


def test_noisy_preview_is_reduced_to_the_reply_budget():
    with Image.frombytes("RGB", (1600, 1600), os.urandom(1600 * 1600 * 3)) as image:
        preview = page_preview(image, 7)
    assert preview["page_number"] == 7
    content = base64.b64decode(preview["data_url"].split(",", 1)[1])
    assert len(content) <= MAX_PREVIEW_BYTES
    with Image.open(io.BytesIO(content)) as reduced:
        assert reduced.width < 1600
