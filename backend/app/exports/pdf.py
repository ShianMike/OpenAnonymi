"""Fresh text-only PDFs from reviewed text, using bundled fonts and no network."""

import hashlib
import io
import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from threading import BoundedSemaphore

from fontTools.ttLib import TTFont
from fpdf import FPDF
from fpdf.errors import FPDFException
from pypdf import PdfWriter

from app.exports.errors import PdfUnavailable

FONTS = Path(__file__).resolve().parents[1] / "assets/fonts"
MAX_PAGES = 200
MAX_PDF_BYTES = 16 * 1024 * 1024
_generation_slot = BoundedSemaphore(1)


class ReviewedPDF(FPDF):
    def add_page(self, *args, **kwargs):
        if self.page_no() >= MAX_PAGES:
            raise PdfUnavailable("This PDF exceeds the page limit. Download TXT or Word instead.")
        return super().add_page(*args, **kwargs)


@lru_cache(maxsize=1)
def _font_catalog():
    """Cache public font metadata only; each output has its own font subsets."""
    manifest = json.loads((FONTS / "manifest.json").read_text(encoding="utf-8"))
    entries = []
    for entry in manifest["fonts"]:
        path = FONTS / entry["filename"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise PdfUnavailable("PDF fonts are unavailable. Download TXT or Word instead.")
        with TTFont(path, lazy=True) as font:
            points = frozenset(font.getBestCmap())
            variable = "fvar" in font
        entries.append((entry["family"], path, points, variable))
    return tuple(entries)


def generate_pdf(text: str, now: datetime) -> bytes:
    """The caller supplies only the canonical authorized processed text."""
    if not _generation_slot.acquire(blocking=False):
        raise PdfUnavailable("PDF generation is busy. Try again shortly.")
    try:
        return _generate_pdf(text, now)
    finally:
        _generation_slot.release()


def _generate_pdf(text: str, now: datetime) -> bytes:
    try:
        catalog = _font_catalog()
        uncovered = {ord(char) for char in text if char not in "\n\r\t"}
        selected = []
        for family, path, points, variable in catalog:
            if not selected or uncovered.intersection(points):
                selected.append((family, path, variable))
                uncovered.difference_update(points)
        if uncovered:
            raise PdfUnavailable(
                "Some text cannot be rendered in this PDF. Download TXT or Word to preserve it."
            )
        pdf = ReviewedPDF()
        pdf.set_margins(18, 18, 18)
        pdf.set_auto_page_break(True, 18)
        pdf.set_title("Reviewed document")
        pdf.set_creator("OpenAnonymi")
        pdf.set_producer("OpenAnonymi")
        pdf.set_creation_date(now)
        for family, path, variable in selected:
            pdf.add_font(family, fname=path, variations={"wght": 400} if variable else None)
        pdf.set_font(selected[0][0], size=10)
        pdf.set_fallback_fonts([family for family, _, _ in selected[1:]])
        pdf.set_text_shaping(True, features={"liga": False})
        pdf.add_page()
        # PDF pages wrap paragraphs; TXT remains the exact whitespace-preserving format.
        display = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
        for paragraph in display.split("\n"):
            # Reassert the base font outside fallback text's saved graphics state.
            # Some PDF readers retain the last fallback font after Q; emit Tf again.
            pdf.set_font(selected[0][0], size=10.5)
            pdf.set_font(selected[0][0], size=10)
            pdf.multi_cell(
                w=0,
                h=5.5,
                text=paragraph,
                align="L",
                new_x="LMARGIN",
                new_y="NEXT",
                markdown=False,
                print_sh=True,
            )
        payload = bytes(pdf.output())
        if len(payload) > MAX_PDF_BYTES:
            raise PdfUnavailable("This PDF exceeds the size limit. Download TXT or Word instead.")
        # FPDF emits a viewer zoom OpenAction by default. Omit all opening actions.
        writer = PdfWriter(clone_from=io.BytesIO(payload))
        writer.root_object.pop("/OpenAction", None)
        with io.BytesIO() as cleaned:
            writer.write(cleaned)
            result = cleaned.getvalue()
        if len(result) > MAX_PDF_BYTES:
            raise PdfUnavailable("This PDF exceeds the size limit. Download TXT or Word instead.")
        return result
    except PdfUnavailable:
        raise
    except (OSError, ValueError, KeyError, FPDFException):
        raise PdfUnavailable(
            "PDF generation is unavailable. Download TXT or Word instead."
        ) from None
