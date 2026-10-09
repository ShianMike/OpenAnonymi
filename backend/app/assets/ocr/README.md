# Local English OCR data

`eng.traineddata` and `LICENSE` are unmodified files from the official
[tessdata_fast 4.1.0 repository](https://github.com/tesseract-ocr/tessdata_fast),
pinned at `65727574dfcd264acbb0c3e07860e4e9e9b22185`. The adjacent manifest records
their exact source URLs, byte lengths and SHA256 values. The worker verifies the
model hash before use. Apache-2.0 license text is retained verbatim.

The runtime uses `tesserocr==2.10.0`, PDFium and Pillow from the backend lockfile.
On Windows CPython 3.11, uv selects the upstream-endorsed
[community wheel](https://github.com/simonflueckiger/tesserocr-windows_build)
containing Tesseract 5.5.2 and Leptonica 1.87.0. Its locked SHA256 is
`02f75202a13804dacaac111cc4375cdb7b0194217f7f36add30cbb57c37c002c`.
Linux uses the PyPI wheel selected by uv. Windows DLL versions do not establish
Linux runtime versions or container memory usage; those remain hosted CI gates.

The model ships with the application. OCR makes no model or recognition service
request. Each bounded job runs in a short-lived process with scrubbed environment,
binary input on stdin and extracted text on stdout. Native diagnostic output is
discarded. The worker creates no input/output files; FastAPI's ordinary multipart
upload handling may use an automatically closed temporary spool for large files.
