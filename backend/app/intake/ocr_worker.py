"""Short-lived single-thread PDF/image decoder and actual local Tesseract OCR."""

import base64
import hashlib
import io
import json
import math
import sys
import warnings
from pathlib import Path

from app.intake.process_limits import isolate_linux_worker, limit_linux_worker

MAX_PIXELS = 8_000_000
MAX_OCR_PAGES = 10
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_PREVIEW_BYTES = 192 * 1024
IMAGE_FORMATS = ("PNG", "JPEG", "TIFF", "WEBP")
DATA = Path(__file__).resolve().parents[1] / "assets/ocr"


class OcrRejected(ValueError):
    pass


def check_image(image):
    width, height = image.size
    if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
        raise OcrRejected("pixels")


def page_preview(image, page_number):
    # shortcut: previews are thumbnails; add on-demand rendering if full-resolution zoom is needed.
    with image.copy() as thumbnail:
        thumbnail.thumbnail((1600, 1600))
        while True:
            with io.BytesIO() as buffer:
                thumbnail.save(buffer, format="JPEG", quality=70)
                content = buffer.getvalue()
            if len(content) <= MAX_PREVIEW_BYTES:
                return {"page_number": page_number,
                        "data_url": "data:image/jpeg;base64," + base64.b64encode(content).decode("ascii")}
            thumbnail.thumbnail((max(1, thumbnail.width * 3 // 4), max(1, thumbnail.height * 3 // 4)))


def recognize(api, image, page_number=1, previews=None):
    from PIL import Image, ImageOps

    check_image(image)
    # Flatten transparency against white; embedded image metadata is discarded.
    with (
        ImageOps.exif_transpose(image) as oriented,
        oriented.convert("RGBA") as rgba,
        Image.new("RGB", oriented.size, "white") as plain,
        rgba.getchannel("A") as alpha,
    ):
        plain.paste(rgba, mask=alpha)
        # The engine receives bounded raw RGB, never an uploaded image container.
        pixels = plain.tobytes()
        api.SetImageBytes(pixels, plain.width, plain.height, 3, plain.width * 3)
        api.SetSourceResolution(200)
        value = api.GetUTF8Text() or ""
        api.Clear()
        if previews is not None:
            previews.append(page_preview(plain, page_number))
    if len(value) > 100_000 or len(value.encode("utf-8")) > 1024 * 1024:
        raise OcrRejected("text")
    return value.rstrip("\n")


def main():
    limit_linux_worker()
    try:
        from PIL import Image

        isolate_linux_worker()
        from tesserocr import OEM, PSM, PyTessBaseAPI

        Image.MAX_IMAGE_PIXELS = MAX_PIXELS
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        content = sys.stdin.buffer.read(MAX_FILE_BYTES + 1)
        if not content or len(content) > MAX_FILE_BYTES:
            raise OcrRejected("format")
        kind = sys.argv[-2]
        previews = [] if "--previews" in sys.argv[1:-2] else None
        manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
        entry = next(item for item in manifest["files"] if item["filename"] == "eng.traineddata")
        if hashlib.sha256((DATA / entry["filename"]).read_bytes()).hexdigest() != entry["sha256"]:
            raise OcrRejected("engine")
        with PyTessBaseAPI(path=str(DATA), lang="eng", oem=OEM.LSTM_ONLY, psm=PSM.AUTO) as api:
            if kind == "pdf":
                import pypdfium2

                indexes = [int(value) for value in sys.argv[-1].split(",") if value]
                if not 1 <= len(indexes) <= MAX_OCR_PAGES:
                    raise OcrRejected("pages")
                pieces = {}
                with pypdfium2.PdfDocument(content) as document:
                    for index in indexes:
                        if not 0 <= index < len(document):
                            raise OcrRejected("format")
                        page = document[index]
                        try:
                            width, height = page.get_size()
                            if (
                                not (math.isfinite(width) and math.isfinite(height))
                                or width <= 0
                                or height <= 0
                            ):
                                raise OcrRejected("pixels")
                            if (
                                math.ceil(width * 200 / 72) * math.ceil(height * 200 / 72)
                                > MAX_PIXELS
                            ):
                                raise OcrRejected("pixels")
                            bitmap = page.render(scale=200 / 72)
                            try:
                                image = bitmap.to_pil()
                                try:
                                    pieces[str(index)] = recognize(api, image, index + 1, previews)
                                finally:
                                    image.close()
                            finally:
                                bitmap.close()
                        finally:
                            page.close()
                result = {"pages": pieces}
                text = "\n\n".join(pieces.values())
            elif kind == "image":
                with Image.open(io.BytesIO(content), formats=IMAGE_FORMATS) as image:
                    if image.format not in IMAGE_FORMATS:
                        raise OcrRejected("format")
                    count = getattr(image, "n_frames", 1)
                    if count > MAX_OCR_PAGES:
                        raise OcrRejected("pages")
                    if count > 1 and image.format != "TIFF":
                        raise OcrRejected("format")
                    pieces = []
                    for index in range(count):
                        image.seek(index)
                        check_image(image)
                        pieces.append(recognize(api, image, index + 1, previews))
                text = "\n\n".join(pieces)
                result = {"text": text, "page_count": count}
            else:
                raise OcrRejected("format")
        if kind == "image" and not text.strip():
            raise OcrRejected("empty")
        if len(text) > 100_000 or len(text.encode("utf-8")) > 1024 * 1024:
            raise OcrRejected("text")
        if previews is not None:
            result["page_previews"] = previews
    except OcrRejected as error:
        result = {"error": str(error)}
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        result = {"error": "pixels"}
    except Image.UnidentifiedImageError:
        result = {"error": "format"}
    except Exception:  # noqa: BLE001 -- native/decoder messages never leave this worker
        result = {"error": "engine"}
    sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
