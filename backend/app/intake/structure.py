"""Content-free Word leaf spans, bounded layout validation and single-edit alignment."""

import re
from bisect import bisect_right
from copy import deepcopy

from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.contracts import MAX_CODE_POINTS
from app.intake.validation import SourceValidationError, validate_source

MAX_BLOCKS = 20_000
PLAIN_LAYOUT_NOTE = (
    "This document's layout is too complex; the Word download will use plain paragraphs."
)


class InvalidLayout(ValueError):
    pass


def leaves(layout):
    for block in layout["blocks"]:
        if block["kind"] == "paragraph":
            yield block
        else:
            for row in block["rows"]:
                for cell in row:
                    yield from cell


def joined_text(layout, source):
    """The same paragraph/row/cell separators as canonical text intake."""
    chunks = []
    for block in layout["blocks"]:
        if block["kind"] == "paragraph":
            chunks.append(source[block["start"] : block["end"]])
        else:
            chunks.extend(
                "\t".join("\n".join(source[p["start"] : p["end"]] for p in cell) for cell in row)
                for row in block["rows"]
            )
    return "\n".join(chunks)


def validate_layout(layout, length, source=None):
    if (
        not isinstance(layout, dict)
        or set(layout) != {"v", "blocks"}
        or type(layout["v"]) is not int
        or layout["v"] != 1
    ):
        raise InvalidLayout("Invalid protected layout.")
    if not isinstance(layout["blocks"], list) or len(layout["blocks"]) > MAX_BLOCKS:
        raise InvalidLayout("Invalid protected layout.")
    for block in layout["blocks"]:
        if not isinstance(block, dict) or block.get("kind") not in {"paragraph", "table"}:
            raise InvalidLayout("Invalid protected layout.")
        if block["kind"] == "table":
            if (
                set(block) != {"kind", "rows"}
                or not isinstance(block["rows"], list)
                or not block["rows"]
            ):
                raise InvalidLayout("Invalid protected layout.")
            for row in block["rows"]:
                if not isinstance(row, list) or not row:
                    raise InvalidLayout("Invalid protected layout.")
                for cell in row:
                    if (
                        not isinstance(cell, list)
                        or not cell
                        or any(not isinstance(p, dict) for p in cell)
                    ):
                        raise InvalidLayout("Invalid protected layout.")
    previous, count = 0, 0
    for block in leaves(layout):
        count += 1
        if count > MAX_BLOCKS or set(block) - {
            "kind",
            "start",
            "end",
            "role",
            "region",
            "level",
            "list_kind",
            "list_id",
        }:
            raise InvalidLayout("Invalid protected layout.")
        if (
            block.get("kind") != "paragraph"
            or block.get("role") not in {"normal", "title", "heading", "list_item"}
            or block.get("region") not in {"body", "header", "footer"}
        ):
            raise InvalidLayout("Invalid protected layout.")
        fields = {"kind", "start", "end", "role", "region"}
        if block["role"] == "heading":
            fields.add("level")
        elif block["role"] == "list_item":
            fields.update({"level", "list_kind", "list_id"})
        if set(block) != fields:
            raise InvalidLayout("Invalid protected layout.")
        start, end = block.get("start"), block.get("end")
        if type(start) is not int or type(end) is not int or not previous <= start <= end <= length:
            raise InvalidLayout("Invalid protected layout.")
        previous = end
        if block["role"] == "heading" and (
            type(block.get("level")) is not int or not 1 <= block["level"] <= 9
        ):
            raise InvalidLayout("Invalid protected layout.")
        if block["role"] == "list_item" and (
            block.get("list_kind") not in {"bullet", "number"}
            or type(block.get("level")) is not int
            or not 0 <= block["level"] <= 8
            or type(block.get("list_id")) is not int
            or not 0 <= block["list_id"] <= 2**31 - 1
        ):
            raise InvalidLayout("Invalid protected layout.")
    if not count or (source is not None and joined_text(layout, source) != source):
        raise InvalidLayout("Invalid protected layout.")
    return layout


def _role(paragraph, numbering):
    name = paragraph.style.name if paragraph.style else ""
    if name == "Title":
        return {"role": "title"}
    if matched := re.fullmatch(r"Heading ([1-9])", name, re.IGNORECASE):
        return {"role": "heading", "level": int(matched[1])}
    matched = re.fullmatch(r"List (Bullet|Number)(?: ([2-9]))?", name, re.IGNORECASE)
    level = int(matched[2] or 1) - 1 if matched else 0
    num_pr = paragraph._p.find("./" + qn("w:pPr") + "/" + qn("w:numPr"))
    style, visited = paragraph.style, set()
    while num_pr is None and style is not None and style.style_id not in visited:
        visited.add(style.style_id)
        num_pr = style.element.find("./" + qn("w:pPr") + "/" + qn("w:numPr"))
        style = style.base_style
    num_id = num_pr.find(qn("w:numId")) if num_pr is not None else None
    try:
        list_id = int(num_id.get(qn("w:val"))) if num_id is not None else 0
        ilvl = num_pr.find(qn("w:ilvl")) if num_pr is not None else None
        level = int(ilvl.get(qn("w:val"))) if ilvl is not None else level
        if not 0 <= level <= 8 or not 0 <= list_id <= 2**31 - 1:
            return {"role": "normal"}
    except (TypeError, ValueError):
        return {"role": "normal"}
    if num_id is not None and list_id == 0:
        return {"role": "normal"}
    kind = None
    if list_id and numbering is not None:
        num = next(
            (n for n in numbering.findall(qn("w:num")) if n.get(qn("w:numId")) == str(list_id)),
            None,
        )
        abstract_id = num.find(qn("w:abstractNumId")) if num is not None else None
        abstract = next(
            (
                n
                for n in numbering.findall(qn("w:abstractNum"))
                if abstract_id is not None
                and n.get(qn("w:abstractNumId")) == abstract_id.get(qn("w:val"))
            ),
            None,
        )
        levels = abstract.findall(qn("w:lvl")) if abstract is not None else []
        definition = next(
            (n for n in levels if n.get(qn("w:ilvl")) == str(level)), levels[0] if levels else None
        )
        fmt = definition.find(qn("w:numFmt")) if definition is not None else None
        if fmt is not None:
            kind = "bullet" if fmt.get(qn("w:val")) == "bullet" else "number"
    if kind is None and matched:
        kind = "bullet" if matched[1].lower() == "bullet" else "number"
    return (
        {"role": "list_item", "list_kind": kind, "level": level, "list_id": list_id}
        if kind
        else {"role": "normal"}
    )


def capture_word(document):
    """Return validated text and an integer/enum-only map; never retain upload parts."""
    try:
        numbering = document.part.numbering_part.element
    except KeyError:
        numbering = None
    blocks, roles = [], {}

    def role(block):
        # A Word style is shared by many paragraphs. Resolving its inherited
        # numbering against the full styles/numbering XML for every leaf made
        # otherwise valid large documents take minutes to import.
        properties = block._p.pPr
        style = properties.find(qn("w:pStyle")) if properties is not None else None
        numbering_properties = properties.find(qn("w:numPr")) if properties is not None else None
        key = (
            style.get(qn("w:val")) if style is not None else None,
            str(numbering_properties.xml) if numbering_properties is not None else None,
        )
        if key not in roles:
            roles[key] = _role(block, numbering)
        return roles[key]

    def paragraph(text, region, role=None):
        return {
            "kind": "paragraph",
            "region": region,
            **(role or {"role": "normal"}),
            "_text": text,
        }

    def cell_paragraphs(container, region, depth):
        if depth > 12:
            raise SourceValidationError("Word tables are nested beyond the import limit.")
        for block in container.iter_inner_content():
            if isinstance(block, Paragraph):
                yield paragraph(block.text, region, role(block))
            elif isinstance(block, Table):
                for row in block.rows:
                    seen, texts = set(), []
                    for cell in row.cells:
                        if cell._tc not in seen:
                            seen.add(cell._tc)
                            texts.append(
                                "\n".join(
                                    p["_text"] for p in cell_paragraphs(cell, region, depth + 1)
                                )
                            )
                    yield paragraph("\t".join(texts), region)

    def container_blocks(container, region, empty=True):
        for block in container.iter_inner_content():
            if isinstance(block, Paragraph):
                if empty or block.text.strip():
                    blocks.append(paragraph(block.text, region, role(block)))
            elif isinstance(block, Table):
                rows = []
                for row in block.rows:
                    seen, cells = set(), []
                    for cell in row.cells:
                        if cell._tc not in seen:
                            seen.add(cell._tc)
                            cells.append(
                                list(cell_paragraphs(cell, region, 1)) or [paragraph("", region)]
                            )
                    if cells:
                        rows.append(cells)
                if rows:
                    blocks.append({"kind": "table", "rows": rows})

    seen = set()
    for region in ("header", "body", "footer"):
        if region == "body":
            container_blocks(document, region)
            continue
        for section in document.sections:
            for prefix in ("", "first_page_", "even_page_"):
                part = getattr(section, prefix + region)
                if part.part.partname not in seen:
                    seen.add(part.part.partname)
                    container_blocks(part, region, empty=False)
    chunks, cursor = [], 0

    def emit(block):
        nonlocal cursor
        text = block.pop("_text")
        block["start"], block["end"] = cursor, cursor + len(text)
        chunks.append(text)
        cursor += len(text)
        if cursor > MAX_CODE_POINTS + 1:
            raise SourceValidationError("Extracted text exceeds the 100,000-character limit.")

    def separator(value):
        nonlocal cursor
        chunks.append(value)
        cursor += len(value)

    for index, block in enumerate(blocks):
        if index:
            separator("\n")
        if block["kind"] == "paragraph":
            emit(block)
        else:
            for r, row in enumerate(block["rows"]):
                if r:
                    separator("\n")
                for c, cell in enumerate(row):
                    if c:
                        separator("\t")
                    for p, leaf in enumerate(cell):
                        if p:
                            separator("\n")
                        emit(leaf)
    raw = "".join(chunks)
    text = raw.strip("\n")
    if not text.strip():
        raise SourceValidationError("No text was found in this Word document.")
    validated = validate_source(text)
    trim = len(raw) - len(raw.lstrip("\n")) + int(validated.initial_bom_removed)
    layout = {"v": 1, "blocks": blocks}
    for leaf in leaves(layout):
        leaf["start"] = max(0, min(len(validated.text), leaf["start"] - trim))
        leaf["end"] = max(0, min(len(validated.text), leaf["end"] - trim))
    while (
        blocks and blocks[0]["kind"] == "paragraph" and blocks[0]["start"] == blocks[0]["end"] == 0
    ):
        blocks.pop(0)
    while (
        blocks
        and blocks[-1]["kind"] == "paragraph"
        and blocks[-1]["start"] == blocks[-1]["end"] == len(validated.text)
    ):
        blocks.pop()
    # The final text strips outer line feeds, including blank paragraphs inside
    # an edge table cell. Remove just those clipped leaves/rows so the map still
    # reconstructs the exact validated text with its structural separators.
    for edge, boundary in ((0, 0), (-1, len(validated.text))):
        if not blocks or blocks[edge]["kind"] != "table":
            continue
        rows = blocks[edge]["rows"]
        while True:
            row = rows[edge]
            cell = row[edge]
            while len(cell) > 1 and cell[edge]["start"] == cell[edge]["end"] == boundary:
                cell.pop(edge)
            if len(rows) > 1 and len(row) == 1 and cell[0]["start"] == cell[0]["end"] == boundary:
                rows.pop(edge)
            else:
                break
    try:
        validate_layout(layout, len(validated.text), validated.text)
    except InvalidLayout:
        return validated, None, (PLAIN_LAYOUT_NOTE,)
    return validated, layout, ()


def allows_span(layout, source, start, end):
    if layout is None:
        return True
    return not any(char in source[start:end] for char in "\n\t") and any(
        block["start"] <= start < end <= block["end"] for block in leaves(layout)
    )


def realign_word(layout, old, new):
    if layout is None:
        return None
    if old == new:
        return deepcopy(layout)
    prefix = 0
    while prefix < min(len(old), len(new)) and old[prefix] == new[prefix]:
        prefix += 1
    suffix = 0
    while suffix < min(len(old), len(new)) - prefix and old[-suffix - 1] == new[-suffix - 1]:
        suffix += 1
    old_end, new_end = len(old) - suffix, len(new) - suffix
    if any(c in old[prefix:old_end] + new[prefix:new_end] for c in "\n\t"):
        return None
    result, delta, touched = deepcopy(layout), len(new) - len(old), False
    for block in leaves(result):
        if not touched and block["start"] <= prefix <= old_end <= block["end"]:
            block["end"] += delta
            touched = True
        elif touched:
            block["start"] += delta
            block["end"] += delta
    if not touched:
        return None
    validate_layout(result, len(new), new)
    return result


def output_layout(layout, mappings, text):
    """Translate only canonical preview boundaries; never generate a second replacement."""
    if layout is None:
        return None
    ordered = sorted(mappings, key=lambda item: item.source_span.end)
    ends, shifts, total = [], [0], 0
    for item in ordered:
        ends.append(item.source_span.end)
        total += (item.preview_span.end - item.preview_span.start) - (
            item.source_span.end - item.source_span.start
        )
        shifts.append(total)
    result = deepcopy(layout)
    for block in leaves(result):
        block["start"] += shifts[bisect_right(ends, block["start"])]
        block["end"] += shifts[bisect_right(ends, block["end"])]
    validate_layout(result, len(text), text)
    return result
