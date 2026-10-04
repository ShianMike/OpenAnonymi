"""Actual fictional raster scans with metadata, plus image-only/mixed PDFs."""

from io import BytesIO
from pathlib import Path

from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

TEXT = "Fictional scan\nContact: nora@example.test\nCase number: ABC123"


def image_sample(format="PNG", size=(1600, 800), text=TEXT, frames=1):
    font = ImageFont.truetype(
        str(Path(__file__).resolve().parents[1] / "app/assets/fonts/NotoSans-Regular.ttf"), 42
    )
    with Image.new("RGB", size, "white") as image:
        ImageDraw.Draw(image).multiline_text((100, 100), text, font=font, fill="black", spacing=20)
        with BytesIO() as buffer:
            options = {}
            if format == "TIFF":
                options["compression"] = "tiff_deflate"
            if format == "PNG":
                metadata = PngImagePlugin.PngInfo()
                metadata.add_text("Author", "metadata-privacy-canary")
                options["pnginfo"] = metadata
            if frames > 1:
                options.update(save_all=True, append_images=[image] * (frames - 1))
            image.save(buffer, format=format, **options)
            return buffer.getvalue()


def scanned_pdf(*, pages=1, caption=False, selectable=False, wide=False):
    pdf = FPDF(format=(2000, 1000) if wide else "A4")
    pdf.set_author("metadata-privacy-canary")
    for _ in range(pages):
        pdf.add_page()
        if caption:
            pdf.set_font("Helvetica", size=14)
            pdf.text(20, 18, "Selectable caption above scan")
        pdf.image(BytesIO(image_sample()), x=15, y=30, w=180)
    if selectable:
        pdf.add_page()
        pdf.set_font("Helvetica", size=14)
        pdf.text(20, 40, "Selectable final page after scan")
    return bytes(pdf.output())


def inline_scan_pdf(*, in_form=False):
    """Real inline JPEG, optionally in a Form XObject, under a selectable caption."""
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, RectangleObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    resources = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    inline = (
        b"q 510 0 0 255 42 500 cm BI /W 1600 /H 800 /CS /RGB /BPC 8 /F /DCTDecode ID\n"
        + image_sample("JPEG")
        + b"\nEI Q\n"
    )
    caption = b"BT /F1 14 Tf 56 790 Td (Selectable caption above scan) Tj ET\n"
    if in_form:
        form = DecodedStreamObject()
        form.set_data(inline)
        form.update(
            {
                NameObject("/Type"): NameObject("/XObject"),
                NameObject("/Subtype"): NameObject("/Form"),
                NameObject("/BBox"): RectangleObject([0, 0, 595, 842]),
                NameObject("/Resources"): DictionaryObject(),
            }
        )
        resources[NameObject("/XObject")] = DictionaryObject(
            {NameObject("/Scan"): writer._add_object(form)}
        )
        inline = b"q /Scan Do Q\n"
    stream = DecodedStreamObject()
    stream.set_data(caption + inline)
    page[NameObject("/Contents")] = writer._add_object(stream)
    page[NameObject("/Resources")] = resources
    writer.add_metadata({"/Author": "metadata-privacy-canary"})
    with BytesIO() as output:
        writer.write(output)
        return output.getvalue()
