"""Bounded file geometry tied to immutable source offsets."""

import base64
import io
import math
from bisect import bisect_left, bisect_right
from copy import deepcopy

from PIL import Image, ImageDraw, ImageFont

from app.intake.structure import InvalidLayout

MAX_LAYOUT_BYTES = 24 * 1024 * 1024


def validate_file_layout(layout, source):
    if not isinstance(layout, dict) or layout.get("v") != 1:
        raise InvalidLayout("Invalid protected file layout.")
    kind = layout.get("kind")
    if kind == "txt":
        return layout
    if kind != "pdf":
        raise InvalidLayout("Invalid protected file layout.")
    spans = []
    pages = layout.get("pages", [])
    if not 1 <= len(pages) <= 100:
        raise InvalidLayout("Invalid protected page count.")
    size = 0
    for page in pages:
        width, height = page["width"], page["height"]
        if not all(type(n) is int and n > 0 for n in (width, height)) or width * height > 8_000_000:
            raise InvalidLayout("Invalid protected page dimensions.")
        if not all(
            isinstance(n, (int, float)) and math.isfinite(n) and n > 0 for n in page["points"]
        ):
            raise InvalidLayout("Invalid protected page size.")
        data = base64.b64decode(page["image"], validate=True)
        size += len(data)
        if not data.startswith(b"\x89PNG\r\n\x1a\n") or size > MAX_LAYOUT_BYTES:
            raise InvalidLayout("Invalid protected page image.")
        for mark in page["marks"]:
            spans.append((mark["start"], mark["end"]))
            x, y, w, h = mark["box"]
            if not all(type(n) is int for n in (x, y, w, h)) or not (
                0 <= x < x + w <= width and 0 <= y < y + h <= height
            ):
                raise InvalidLayout("Invalid protected text position.")
    previous = 0
    for start, end in spans:
        if (
            type(start) is not int
            or type(end) is not int
            or not previous <= start < end <= len(source)
        ):
            raise InvalidLayout("Invalid protected text range.")
        if source[previous:start].strip():
            raise InvalidLayout("File text has no review position.")
        previous = end
    if len(spans) > 100_000 or source[previous:].strip():
        raise InvalidLayout("File text has no review position.")
    return layout


def file_blocks(layout):
    if layout["kind"] == "txt":
        return None
    items = [
        {"start": p["marks"][0]["start"], "end": p["marks"][-1]["end"]}
        for p in layout["pages"]
        if p["marks"]
    ]
    return {
        "v": 1,
        "blocks": [
            {
                "kind": "paragraph",
                "role": "normal",
                "region": "body",
                "start": item["start"],
                "end": item["end"],
            }
            for item in items
            if item["start"] < item["end"]
        ],
    }


def page_regions(page, mappings):
    regions = []
    marks = page["marks"]
    starts, ends = [mark["start"] for mark in marks], [mark["end"] for mark in marks]
    for mapping in mappings:
        boxes = [
            m["box"]
            for m in marks[
                bisect_right(ends, mapping.source_span.start) : bisect_left(
                    starts, mapping.source_span.end
                )
            ]
        ]
        if boxes:
            # Findings are constrained to one source line; include punctuation in the same mask.
            left, top = min(box[0] for box in boxes), min(box[1] for box in boxes)
            right = max(x + w for x, y, w, h in boxes)
            bottom = max(y + h for x, y, w, h in boxes)
            regions.append(
                {
                    "finding_id": str(mapping.finding_id),
                    "box": [left, top, right - left, bottom - top],
                    "action": mapping.action,
                }
            )
    return regions


def review_file_layout(layout, source, text=None, mappings=()):
    if layout is None:
        return None
    result = deepcopy(layout)
    by_id = {str(mapping.finding_id): mapping for mapping in mappings}
    if result["kind"] == "pdf":
        for page in result["pages"]:
            regions = page_regions(page, mappings)
            if text is not None:
                with (
                    Image.open(io.BytesIO(base64.b64decode(page["image"]))) as original,
                    original.convert("RGB") as image,
                ):
                    draw = ImageDraw.Draw(image)
                    labeled = set()
                    for region in regions:
                        if region["action"] not in {"label", "redact"}:
                            continue
                        x, y, w, h = region["box"]
                        mapping = by_id[region["finding_id"]]
                        label = text[mapping.preview_span.start : mapping.preview_span.end]
                        solid_mask = region["action"] == "redact" and label == "[REDACTED]"
                        draw.rectangle(
                            (
                                max(0, x - 2),
                                max(0, y - 2),
                                min(image.width, x + w + 2),
                                min(image.height, y + h + 2),
                            ),
                            fill="black" if solid_mask else "white",
                        )
                        if not solid_mask and label and region["finding_id"] not in labeled:
                            from app.exports.errors import PdfUnavailable
                            from app.exports.pdf import _font_catalog

                            required = {ord(c) for c in label}
                            path = next(
                                (
                                    path
                                    for _, path, points, _ in _font_catalog()
                                    if required <= points
                                ),
                                None,
                            )
                            if path is None:
                                raise PdfUnavailable(
                                    "This replacement cannot be fitted into the PDF. Use a category label or export TXT."
                                )
                            font = ImageFont.truetype(str(path), size=32)
                            left, top, right, bottom = font.getbbox(label)
                            with Image.new(
                                "RGB", (max(1, right - left), max(1, bottom - top)), "white"
                            ) as label_image:
                                ImageDraw.Draw(label_image).text(
                                    (-left, -top), label, font=font, fill="black"
                                )
                                ratio = min(w / label_image.width, h / label_image.height)
                                with label_image.resize(
                                    (
                                        max(1, round(label_image.width * ratio)),
                                        max(1, round(label_image.height * ratio)),
                                    ),
                                    Image.Resampling.LANCZOS,
                                ) as fitted:
                                    image.paste(fitted, (x, y))
                            labeled.add(region["finding_id"])
                    buffer = io.BytesIO()
                    image.save(buffer, format="PNG")
                    page["image"] = base64.b64encode(buffer.getvalue()).decode("ascii")
            page.pop("marks")
            page["regions"] = regions
    return result
