# File layout behavior

New PDF imports keep page images and text coordinates, encrypted alongside the
source revision. The original PDF container is not stored. Reviewers can switch
between page layout and text, select positioned findings, navigate pages, and
zoom. Selecting a finding opens its page. Text view supports manual marking.
Changing the source requires a new upload so text offsets cannot drift away
from their page positions.

Reviewed PDF export uses the same processed images as the output preview.
Redactions replace the affected pixels; category labels and other replacement
styles are fitted into their original positions. A fresh PDF preserves page
sizes and page content at 150 dpi. Original text layers, forms, annotations,
attachments, scripts, and document metadata are omitted. The result is an
image-based PDF, without searchable/selectable text. For accessible text, use
the separate reviewed TXT export.

TXT imports and downloads keep tabs, spaces, line endings, and literal Markdown
characters. As in other text intake, one leading UTF-8 BOM is removed. Replacing
a value can change its length; TXT has no fixed page or column geometry.

PDF intake accepts up to 8 MiB, 100 pages, and 100,000 extracted characters.
Scanned or illustrated pages use local printed-English OCR, with a maximum of
10 OCR pages. Raster limits are 8 million pixels per page, 100 million pixels per
document, and 24 MiB of lossless page images. PDF downloads are capped at 16 MiB.
Oversized or unmappable files fail with a recoverable error. OCR can miss or
misread visible content: compare every page before confirming; use a clearer
source or a corrected text copy if the extraction is incomplete. OCR masks cover
whole recognized words that intersect a finding.

Existing reviews created before this feature have no retained page images;
reimport their PDF to enable page layout. Existing Word and image intake
keep their existing behavior. Excel workbooks are unsupported.

Layout access and export use the existing ownership/reviewer permissions,
version checks, confirmation gate, encryption, retention, and cleanup. Layout
responses are not cacheable. Page rendering runs in the bounded local worker.

## Implementation references

- [PDFium text and coordinate APIs](https://pdfium.googlesource.com/pdfium/+/refs/heads/main/public/fpdf_text.h)
  provide character positions; PDF-to-device conversion accounts for page rotation.
- [pypdfium2 Python API](https://pypdfium2.readthedocs.io/en/stable/python_api.html)
  documents rendering and PDFium's requirement to avoid concurrent calls across
  threads. Rendering uses a separate bounded process with explicit resource cleanup.
- [Adobe Acrobat redaction guidance](https://helpx.adobe.com/acrobat/desktop/protect-documents/redact-pdfs/redact.html)
  distinguishes removing visible content from removing hidden information.
  OpenAnonymi rebuilds the output from processed pixels instead of retaining source
  PDF objects or relying on a visual overlay.

Tests compare exported image pixels with the reviewed preview, check all four
page rotations, verify metadata and attachment removal, enforce source immutability,
exercise unauthorized/expired access, and check exact TXT whitespace.

CSV import, column controls and CSV export are no longer available. Historical
CSV review records retain encrypted storage and can be read and exported as TXT;
their stored layouts and audit history are preserved. New reviews accept text,
Markdown, Word, PDF and supported images.
