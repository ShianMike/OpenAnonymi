"""Fresh reviewed Word packages with a closed parts allowlist and neutral metadata."""

import io
import posixpath
from datetime import UTC
from zipfile import ZIP_DEFLATED, ZipFile

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches
from docx.table import _Cell
from docx.text.paragraph import Paragraph
from lxml import etree

from app.intake.structure import InvalidLayout, validate_layout

MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PARTS_ALLOWLIST = frozenset(
    {
        "[Content_Types].xml",
        "_rels/.rels",
        "docProps/app.xml",
        "docProps/core.xml",
        "word/_rels/document.xml.rels",
        "word/document.xml",
        "word/fontTable.xml",
        "word/numbering.xml",
        "word/settings.xml",
        "word/styles.xml",
        "word/stylesWithEffects.xml",
        "word/theme/theme1.xml",
        "word/webSettings.xml",
    }
)


def _child(parent, name, **values):
    node = OxmlElement("w:" + name)
    for key, value in values.items():
        node.set(qn("w:" + key), str(value))
    parent.append(node)
    return node


def _text(paragraph, text):
    # python-docx normally changes CR into a break. A literal XML character
    # reference preserves canonical CRLF text when a downloaded file is read back.
    run = OxmlElement("w:r")
    paragraph._p.append(run)
    pieces, start = [], 0
    for index, char in enumerate(text):
        if char not in "\n\t":
            continue
        pieces.append((text[start:index], "br" if char == "\n" else "tab"))
        start = index + 1
    pieces.append((text[start:], None))
    for value, boundary in pieces:
        if value:
            node = _child(run, "t")
            node.set(qn("xml:space"), "preserve")
            node.text = value
        if boundary:
            _child(run, boundary)


def _abstract_numbering(document, kind):
    root = document.part.numbering_part.element
    number = (
        max(
            (int(node.get(qn("w:abstractNumId"))) for node in root.findall(qn("w:abstractNum"))),
            default=-1,
        )
        + 1
    )
    abstract = OxmlElement("w:abstractNum")
    abstract.set(qn("w:abstractNumId"), str(number))
    _child(abstract, "multiLevelType", val="multilevel")
    for level in range(9):
        node = _child(abstract, "lvl", ilvl=level)
        _child(node, "start", val=1)
        _child(node, "numFmt", val="bullet" if kind == "bullet" else "decimal")
        _child(node, "lvlText", val="•" if kind == "bullet" else f"%{level + 1}.")
        _child(node, "lvlJc", val="left")
        properties = _child(node, "pPr")
        _child(properties, "ind", left=360 * (level + 1), hanging=360)
    first_num = root.find(qn("w:num"))
    root.insert(root.index(first_num) if first_num is not None else len(root), abstract)
    return number


def _list_number(document, abstract, number):
    root = document.part.numbering_part.element
    node = _child(root, "num", numId=number)
    _child(node, "abstractNumId", val=abstract)
    for level in range(9):
        override = _child(node, "lvlOverride", ilvl=level)
        _child(override, "startOverride", val=1)
    return number


def _body_paragraph(document, section):
    node = OxmlElement("w:p")
    # Insert beside the cached final section node. Searching the growing body
    # for that node on each insertion becomes quadratic for valid large inputs.
    if section is None:
        document._element.body.append(node)
    else:
        section.addprevious(node)
    return Paragraph(node, document._body)


def _write_layout(document, layout, text):
    abstracts, instances = {}, {}
    section = document._element.body.sectPr
    next_number = (
        max(
            (
                int(node.get(qn("w:numId")))
                for node in document.part.numbering_part.element.findall(qn("w:num"))
            ),
            default=0,
        )
        + 1
    )

    def paragraph(block, container, existing=None):
        nonlocal next_number
        role = block["role"]
        if role in {"title", "heading"} and container is document:
            result = document.add_heading(level=0 if role == "title" else block["level"])
        else:
            result = (
                existing
                if existing is not None
                else (
                    _body_paragraph(document, section)
                    if container is document
                    else container.add_paragraph()
                )
            )
            if role in {"title", "heading"}:
                result.style = "Title" if role == "title" else f"Heading {block['level']}"
        if role == "list_item":
            kind, level = block["list_kind"], block["level"]
            base = "List Bullet" if kind == "bullet" else "List Number"
            name = base if not level else f"{base} {level + 1}"
            if name not in document.styles:
                style = document.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
                style.base_style = document.styles[base]
                style.paragraph_format.left_indent = Inches(0.25 * (level + 1))
                style.paragraph_format.first_line_indent = Inches(-0.25)
            result.style = name
            if kind not in abstracts:
                abstracts[kind] = _abstract_numbering(document, kind)
            key = (kind, block["list_id"])
            if key not in instances:
                instances[key] = _list_number(document, abstracts[kind], next_number)
                next_number += 1
            properties = result._p.get_or_add_pPr().get_or_add_numPr()
            properties.get_or_add_ilvl().val = level
            properties.get_or_add_numId().val = instances[key]
        _text(result, text[block["start"] : block["end"]])

    for block in layout["blocks"]:
        if block["kind"] == "paragraph":
            paragraph(block, document)
            continue
        rows = block["rows"]
        width = max(len(row) for row in rows)
        # Build actual cells one row at a time. A wide short row must not allocate
        # rows×maximum_columns cells for the entire irregular table.
        table = document.add_table(rows=0, cols=width, style="Table Grid")
        for row in rows:
            tr = _child(table._tbl, "tr")
            if len(row) < width:
                _child(_child(tr, "trPr"), "gridAfter", val=width - len(row))
            for cell_blocks in row:
                tc = _child(tr, "tc")
                _child(_child(tc, "tcPr"), "tcW", w=max(1, 9360 // width), type="dxa")
                _child(tc, "p")
                cell = _Cell(tc, table)
                for index, block in enumerate(cell_blocks):
                    paragraph(block, cell, cell.paragraphs[0] if index == 0 else None)


def _neutral_package(raw):
    output = io.BytesIO()
    with ZipFile(io.BytesIO(raw)) as source, ZipFile(output, "w", ZIP_DEFLATED) as target:
        unexpected = set(source.namelist()) - PARTS_ALLOWLIST
        if any(not name.startswith(("customXml/", "docProps/thumbnail.")) for name in unexpected):
            raise InvalidLayout("Word output contains an unsupported package part.")
        for name in sorted(PARTS_ALLOWLIST):
            data = source.read(name)
            if name == "docProps/app.xml":
                data = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>OpenAnonymi</Application></Properties>'
            elif name.endswith(".rels"):
                root = etree.fromstring(data)
                owner = posixpath.dirname(posixpath.dirname(name))
                for relation in list(root):
                    if relation.get("TargetMode") == "External":
                        raise InvalidLayout("Word output contains an external relationship.")
                    target_name = posixpath.normpath(
                        posixpath.join(owner, relation.get("Target", ""))
                    ).lstrip("/")
                    if target_name not in PARTS_ALLOWLIST:
                        root.remove(relation)
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            elif name == "[Content_Types].xml":
                root = etree.fromstring(data)
                for node in list(root):
                    if (
                        node.get("PartName")
                        and node.get("PartName").lstrip("/") not in PARTS_ALLOWLIST
                    ) or node.get("Extension") in {"jpeg", "jpg"}:
                        root.remove(node)
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            target.writestr(name, data)
    return output.getvalue()


def generate_word(text, layout, now):
    document = Document()
    if layout is None:
        section = document._element.body.sectPr
        for line in text.split("\n"):
            _text(_body_paragraph(document, section), line)
    else:
        validate_layout(layout, len(text), text)
        _write_layout(document, layout, text)
    core = document.core_properties
    for name in (
        "title",
        "author",
        "last_modified_by",
        "subject",
        "keywords",
        "comments",
        "category",
        "content_status",
        "identifier",
        "language",
        "version",
    ):
        setattr(core, name, "")
    core.revision = 1
    core.created = core.modified = now.astimezone(UTC).replace(tzinfo=None)
    printed = core._element.find(qn("cp:lastPrinted"))
    if printed is not None:
        core._element.remove(printed)
    buffer = io.BytesIO()
    document.save(buffer)
    return _neutral_package(buffer.getvalue())
