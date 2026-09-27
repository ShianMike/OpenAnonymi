"""Server-side source validation shared by paste and UTF-8 TXT intake."""

from dataclasses import dataclass
from unicodedata import category

from app.contracts import MAX_CODE_POINTS, MAX_UTF8_BYTES


class SourceValidationError(ValueError):
    """Safe input error that never embeds submitted text."""


@dataclass(frozen=True)
class ValidatedSource:
    text: str
    utf8_bytes: int
    code_points: int
    initial_bom_removed: bool


def validate_source(source: str) -> ValidatedSource:
    """Remove one initial BOM after checking raw limits; preserve all other characters."""
    try:
        raw = source.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise SourceValidationError("Input must be valid UTF-8 text.") from None
    if len(raw) > MAX_UTF8_BYTES:
        raise SourceValidationError("Input exceeds the 1 MiB UTF-8 limit.")
    if len(source) > MAX_CODE_POINTS:
        raise SourceValidationError("Input exceeds the 100,000-character limit.")
    bom_removed = source.startswith("\ufeff")
    text = source[1:] if bom_removed else source
    if not text.strip():
        raise SourceValidationError("Enter text that contains visible content.")
    if any(category(character) == "Cc" and character not in "\t\r\n" for character in text):
        raise SourceValidationError("Input contains an unsupported control character.")
    return ValidatedSource(
        text=text,
        utf8_bytes=len(text.encode("utf-8")),
        code_points=len(text),
        initial_bom_removed=bom_removed,
    )


def validate_txt_file(filename: str | None, content: bytes) -> ValidatedSource:
    """Use the filename only to check format; never keep it as a title or storage path."""
    if not filename or not filename.lower().endswith(".txt"):
        raise SourceValidationError("Choose one UTF-8 .txt file.")
    if len(content) > MAX_UTF8_BYTES:
        raise SourceValidationError("File exceeds the 1 MiB UTF-8 limit.")
    try:
        decoded = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise SourceValidationError("File must be encoded as UTF-8 text.") from None
    return validate_source(decoded)
