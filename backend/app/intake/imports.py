"""Bounded, transient PDF/DOCX text extraction. No original file is persisted."""

import io
import logging
from dataclasses import dataclass, replace
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
class ImportedPagePreview:
    page_number: int
    data_url: str


@dataclass(frozen=True)
class ImportedText:
    source: ValidatedSource
    format: str
    pages: int | None
    notes: tuple[str, ...]
    layout: dict | None = None
    page_previews: tuple[ImportedPagePreview, ...] = ()


def _has_images(page, page_stream) -> bool:
    from pypdf.generic import ContentStream

    seen = set()
    inspected_bytes = 0

    def has_inline(stream):
        nonlocal inspected_bytes
        if stream is None:
            return False
        size = len(stream.get_data())
        inspected_bytes += size
        if size > MAX_PAGE_STREAM or inspected_bytes > 4 * MAX_PAGE_STREAM:
            raise SourceValidationError("PDF content is too complex. Choose a smaller document.")
        parsed = stream if isinstance(stream, ContentStream) else ContentStream(stream, page.pdf)
        return any(operator == b"INLINE IMAGE" for _operands, operator in parsed.operations)

    def visit(resources, stream, depth=0):
        if depth > 10 or len(seen) > 200:
            raise SourceValidationError("PDF content is too complex. Choose a smaller document.")
        if has_inline(stream):
            return True
        if not resources:
            return False
        resources = resources.get_object()
        objects = resources.get("/XObject")
        if objects is None:
            return False
        for reference in objects.get_object().values():
            value = reference.get_object()
            if id(value) in seen:
                continue
            seen.add(id(value))
            if value.get("/Subtype") == "/Image":
                return True
            if value.get("/Subtype") == "/Form" and visit(
                value.get("/Resources"), value, depth + 1
            ):
                return True
        return False

    return visit(page.get("/Resources"), page_stream)


def _pdf(content: bytes, include_previews: bool = False) -> ImportedText:
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
        pieces, chars, streams, ocr_pages = [], 0, 0, []
        for index, page in enumerate(reader.pages):
            stream = page.get_contents()
            streams += len(stream.get_data()) if stream is not None else 0
            if streams > 4 * MAX_PAGE_STREAM:
                raise SourceValidationError(
                    "PDF content is too complex. Export a smaller text document."
                )
            text = page.extract_text() or ""
            if not text.strip() or _has_images(page, stream):
                ocr_pages.append(index)
            chars += len(text) + 2
            if chars > MAX_CODE_POINTS:
                raise SourceValidationError("Extracted text exceeds the 100,000-character limit.")
            pieces.append(text.rstrip("\n"))
        previews = ()
        if ocr_pages:
            from app.intake.ocr import extract_ocr

            if len(ocr_pages) > 10:
                raise SourceValidationError("OCR supports at most 10 scanned pages per file.")
            result = extract_ocr(content, "pdf", tuple(ocr_pages), include_previews=include_previews)
            previews = tuple(ImportedPagePreview(**page) for page in result.get("page_previews", []))
            for index in ocr_pages:
                pieces[index] = result["pages"][str(index)]
        text = "\n\n".join(pieces)
        if not text.strip():
            raise SourceValidationError(
                "OCR found no readable text. Choose a clearer scan or paste the text."
            )
        notes = [
            "PDF reading order and spacing can differ. Check the extracted text before reviewing."
        ]
        if ocr_pages:
            notes.append(
                f"Local English OCR checked {len(ocr_pages)} scanned or illustrated pages. Correct missing or misread text before saving."
            )
        return ImportedText(validate_source(text), "pdf", count, tuple(notes), page_previews=previews)


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
    filename: str | None, content: bytes, csv_delimiter="auto", csv_header="auto",
    *, include_previews: bool = False,
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
    if suffix == ".md":
        return ImportedText(
            validate_txt_file("source.txt", content),
            "md",
            None,
            (
                "Markdown source is preserved. Formatting appears in the review; HTML, images and links stay inactive.",
            ),
        )
    if suffix == ".txt":
        return ImportedText(validate_txt_file(filename, content), "txt", None, ())
    images = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}
    if suffix not in {".pdf", ".docx", *images}:
        raise SourceValidationError(
            "Choose TXT, Markdown, CSV, PDF, DOCX, PNG, JPEG, TIFF or WebP."
        )
    if not content or len(content) > MAX_FILE_BYTES:
        raise SourceValidationError(
            "Documents and images must be nonempty and no larger than 8 MiB."
        )
    try:
        if suffix in images:
            from app.intake.ocr import extract_ocr

            result = extract_ocr(content, "image", include_previews=include_previews)
            return ImportedText(
                validate_source(result["text"]),
                "image",
                result["page_count"],
                (
                    "Local English OCR can miss or misread text. Correct the extracted text before saving.",
                ),
                page_previews=tuple(ImportedPagePreview(**page) for page in result.get("page_previews", [])),
            )
        return _pdf(content, include_previews) if suffix == ".pdf" else _docx(content)
    except SourceValidationError:
        raise
    except Exception:  # noqa: BLE001 -- parser errors must never disclose file content
        # No parser message/filename/object escapes into logs, responses or notes.
        raise SourceValidationError(
            "This document is damaged, encrypted or too complex to import. Try exporting it as UTF-8 TXT."
        ) from None


def edit_import(imported: ImportedText, text: str | None) -> ImportedText:
    """Validate the user's pre-save correction and recompute any retained structure."""
    if text is None or text == imported.source.text:
        return imported
    source = validate_source(text)
    layout = None
    if imported.format == "csv":
        from app.intake.csv_structure import CsvError, parse_csv

        layout = parse_csv(
            source.text,
            imported.layout["delimiter"],
            "true" if imported.layout["has_header"] else "false",
            remove_bom=False,
        ).layout
        if layout["columns"] != imported.layout["columns"]:
            raise CsvError("csv_structure_invalid", "Keep the same CSV column count before saving.")
    elif imported.layout is not None and imported.format == "docx":
        from app.intake.structure import realign_word

        layout = realign_word(imported.layout, imported.source.text, source.text)
    return replace(imported, source=source, layout=layout)
