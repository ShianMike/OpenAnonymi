"""Bounded, transient PDF/DOCX text extraction. No original file is persisted."""

import io
import logging
from dataclasses import dataclass
from pathlib import PurePath
from zipfile import ZipFile

from app.contracts import MAX_CODE_POINTS
from app.intake.validation import (
    SourceValidationError,
    ValidatedSource,
    validate_source,
    validate_txt_file,
)

MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_EXPANDED_BYTES = 16 * 1024 * 1024
MAX_XML_BYTES = 4 * 1024 * 1024
MAX_PDF_PAGES = 100
MAX_PAGE_STREAM = 1024 * 1024

# Library recovery warnings can contain malformed PDF objects. Only our generic
# content-free errors reach logs or the API.
logging.getLogger("pypdf").setLevel(logging.CRITICAL)


@dataclass(frozen=True)
class ImportedText:
    source: ValidatedSource
    format: str
    pages: int | None
    notes: tuple[str, ...]
    layout: dict | None = None


def _pdf(content: bytes) -> ImportedText:
    from pypdf import Configuration, PdfReader, apply_configuration

    if not content.startswith(b"%PDF-"):
        raise SourceValidationError("This file does not contain a readable PDF.")
    config = Configuration(
        maximum_declared_stream_length=MAX_PAGE_STREAM,
        array_based_stream_maximum_output_length=MAX_PAGE_STREAM,
        lzw_maximum_output_length=MAX_PAGE_STREAM,
        run_length_maximum_output_length=MAX_PAGE_STREAM,
        zlib_maximum_output_length=MAX_PAGE_STREAM,
        zlib_maximum_recovery_input_length=MAX_PAGE_STREAM,
        jbig2_maximum_output_length=MAX_PAGE_STREAM,
        jbig2dec_binary=None,
        page_tree_maximum_entries=300,
        page_tree_maximum_depth=20,
        xform_maximum_invocations_per_extraction=100,
        image_maximum_buffer_size=MAX_PAGE_STREAM,
    )
    with apply_configuration(config):
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise SourceValidationError(
                "This PDF is encrypted. Upload an unlocked copy with selectable text."
            )
        count = len(reader.pages)
        if not 1 <= count <= MAX_PDF_PAGES:
            raise SourceValidationError("Choose a PDF with 1 to 100 pages.")
        pieces, chars, streams, empty = [], 0, 0, 0
        for page in reader.pages:
            stream = page.get_contents()
            streams += len(stream.get_data()) if stream is not None else 0
            if streams > 4 * MAX_PAGE_STREAM:
                raise SourceValidationError(
                    "PDF content is too complex. Export a smaller text document."
                )
            text = page.extract_text() or ""
            empty += not text.strip()
            chars += len(text) + 2
            if chars > MAX_CODE_POINTS:
                raise SourceValidationError("Extracted text exceeds the 100,000-character limit.")
            pieces.append(text.rstrip("\n"))
        text = "\n\n".join(pieces)
        if not text.strip():
            raise SourceValidationError(
                "No selectable text was found. Scanned PDFs need OCR before importing."
            )
        notes = [
            "PDF reading order and spacing can differ. Check the extracted text before reviewing."
        ]
        if empty:
            notes.append(
                f"{empty} pages contained no selectable text. Image-only content is not imported."
            )
        return ImportedText(validate_source(text), "pdf", count, tuple(notes))


def _docx(content: bytes) -> ImportedText:
    from lxml import etree

    if not content.startswith(b"PK"):
        raise SourceValidationError("This file does not contain a readable Word DOCX document.")
    with ZipFile(io.BytesIO(content)) as archive:
        entries = archive.infolist()
        if len(entries) > 2000 or sum(item.file_size for item in entries) > MAX_EXPANDED_BYTES:
            raise SourceValidationError("The Word document expands beyond the import limit.")
        if any(item.flag_bits & 1 for item in entries):
            raise SourceValidationError(
                "This Word document is encrypted. Upload an unlocked DOCX copy."
            )
        if len({item.filename for item in entries}) != len(entries):
            raise SourceValidationError("The Word document has conflicting archive entries.")
        names = archive.namelist()
        if "word/document.xml" not in names or "[Content_Types].xml" not in names:
            raise SourceValidationError("Choose a valid .docx document.")
        parts = [name for name in names if name.endswith((".xml", ".rels"))]
        for name in parts:
            if archive.getinfo(name).file_size > MAX_XML_BYTES:
                raise SourceValidationError("Word text data exceeds the import limit.")
            xml = archive.read(name)
            if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
                raise SourceValidationError("Word document contains unsupported XML declarations.")
            etree.fromstring(
                xml,
                parser=etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False),
            )
    from docx import Document

    from app.intake.structure import capture_word

    document = Document(io.BytesIO(content))
    source, layout, layout_notes = capture_word(document)
    notes = (
        (
            "Paragraphs, tables, headers and footers imported as text. Images, comments, text boxes and tracked changes may be omitted; check the preview.",
        )
        + layout_notes
        + (
            (
                "Word downloads keep basic headings, lists and tables. Header and footer text appears in the body.",
            )
            if layout
            else ()
        )
    )
    return ImportedText(source, "docx", None, notes, layout)


def extract_import(
    filename: str | None, content: bytes, csv_delimiter="auto", csv_header="auto"
) -> ImportedText:
    suffix = PurePath(filename or "").suffix.lower()
    if suffix == ".csv":
        from app.contracts import MAX_UTF8_BYTES
        from app.intake.csv_structure import parse_csv

        if not content or len(content) > MAX_UTF8_BYTES:
            raise SourceValidationError("CSV files must be nonempty and no larger than 1 MiB.")
        try:
            decoded = content.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise SourceValidationError("CSV files must be encoded as UTF-8 text.") from None
        parsed = parse_csv(decoded, csv_delimiter, csv_header)
        return ImportedText(parsed.source, "csv", None, (), parsed.layout)
    if suffix == ".txt":
        return ImportedText(validate_txt_file(filename, content), "txt", None, ())
    if suffix not in (".pdf", ".docx"):
        raise SourceValidationError("Choose one UTF-8 TXT or CSV, PDF, or Word DOCX file.")
    if not content or len(content) > MAX_FILE_BYTES:
        raise SourceValidationError("PDF and DOCX files must be nonempty and no larger than 8 MiB.")
    try:
        return _pdf(content) if suffix == ".pdf" else _docx(content)
    except SourceValidationError:
        raise
    except Exception:  # noqa: BLE001 -- parser errors must never disclose file content
        # No parser message/filename/object escapes into logs, responses or notes.
        raise SourceValidationError(
            "This document is damaged, encrypted or too complex to import. Try exporting it as UTF-8 TXT."
        ) from None
