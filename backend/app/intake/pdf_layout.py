"""Raster pages and source coordinates produced only inside the bounded worker."""

import base64
import ctypes
import io
import math
from contextlib import closing


def capture_pdf(content, ocr_pages, api, rejected):
    import pypdfium2 as pdfium
    from tesserocr import RIL

    OcrRejected = rejected

    pages, chunks, offset, total_bytes, total_pixels = [], [], 0, 0, 0
    with pdfium.PdfDocument(content) as document:
        if not 1 <= len(document) <= 100:
            raise OcrRejected("pages")
        for index in range(len(document)):
            if index:
                chunks.append("\n\n")
                offset += 2
            with closing(document[index]) as page:
                width, height = page.get_size()
                if not all(math.isfinite(n) and n > 0 for n in (width, height)):
                    raise OcrRejected("pixels")
                scale = 150 / 72
                if math.ceil(width * scale) * math.ceil(height * scale) > 8_000_000:
                    raise OcrRejected("pixels")
                bitmap = page.render(scale=scale, draw_annots=False)
                try:
                    with bitmap.to_pil() as rendered, rendered.convert("RGB") as image:
                        total_pixels += image.width * image.height
                        if total_pixels > 100_000_000:
                            raise OcrRejected("layout")
                        marks = []
                        if index in ocr_pages:
                            api.SetImageBytes(
                                image.tobytes(), image.width, image.height, 3, image.width * 3
                            )
                            api.SetSourceResolution(150)
                            text = (api.GetUTF8Text() or "").rstrip("\n")
                            iterator = api.GetIterator()
                            cursor = 0
                            if iterator:
                                while True:
                                    word = (iterator.GetUTF8Text(RIL.WORD) or "").strip()
                                    if word:
                                        start = text.find(word, cursor)
                                        if start < 0:
                                            raise OcrRejected("layout")
                                        left, top, right, bottom = iterator.BoundingBox(RIL.WORD)
                                        marks.append(
                                            {
                                                "start": offset + start,
                                                "end": offset + start + len(word),
                                                "box": [left, top, right - left, bottom - top],
                                            }
                                        )
                                        cursor = start + len(word)
                                    if not iterator.Next(RIL.WORD):
                                        break
                            api.Clear()
                        else:
                            chars = []
                            with closing(page.get_textpage()) as textpage:
                                if textpage.count_chars() + offset > 100_000:
                                    raise OcrRejected("text")
                                for i in range(textpage.count_chars()):
                                    number = pdfium.raw.FPDFText_GetUnicode(textpage.raw, i)
                                    if not number:
                                        continue
                                    char = chr(number)
                                    if not char.isspace():
                                        left, bottom, right, top = textpage.get_charbox(i)
                                        points = []
                                        for x, y in (
                                            (left, bottom),
                                            (left, top),
                                            (right, bottom),
                                            (right, top),
                                        ):
                                            px, py = ctypes.c_int(), ctypes.c_int()
                                            if not pdfium.raw.FPDF_PageToDevice(
                                                page.raw,
                                                0,
                                                0,
                                                image.width,
                                                image.height,
                                                0,
                                                x,
                                                y,
                                                px,
                                                py,
                                            ):
                                                raise OcrRejected("layout")
                                            points.append((px.value, py.value))
                                        x = max(0, min(p[0] for p in points))
                                        y = max(0, min(p[1] for p in points))
                                        right = min(image.width, max(p[0] for p in points))
                                        bottom = min(image.height, max(p[1] for p in points))
                                        if right <= x or bottom <= y:
                                            raise OcrRejected("layout")
                                        marks.append(
                                            {
                                                "start": offset + len(chars),
                                                "end": offset + len(chars) + 1,
                                                "box": [x, y, right - x, bottom - y],
                                            }
                                        )
                                    chars.append(char)
                            text = "".join(chars)
                        buffer = io.BytesIO()
                        image.save(buffer, format="PNG")
                        data = buffer.getvalue()
                        total_bytes += len(data)
                        if total_bytes > 24 * 1024 * 1024:
                            raise OcrRejected("layout")
                        pages.append(
                            {
                                "width": image.width,
                                "height": image.height,
                                "points": [width, height],
                                "image": base64.b64encode(data).decode("ascii"),
                                "marks": marks,
                            }
                        )
                        chunks.append(text)
                        offset += len(text)
                        if offset > 100_000:
                            raise OcrRejected("text")
                finally:
                    bitmap.close()
    text = "".join(chunks)
    if not text.strip():
        raise OcrRejected("empty")
    return {"text": text, "layout": {"v": 1, "kind": "pdf", "pages": pages}}
