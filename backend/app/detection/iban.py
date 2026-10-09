"""National length plus ISO 7064 mod-97; never a bank validity check."""

import re

from app.contracts import FindingCategory
from app.detection.support import data, suggest

CANDIDATE = re.compile(r"(?<!\w)([A-Z]{2})[0-9]{2}")


def mod97(value: str):
    remainder = 0
    for char in value[4:] + value[:4]:
        encoded = char if char.isdigit() else str(ord(char) - ord('A') + 10)
        for digit in encoded:
            remainder = (remainder * 10 + int(digit)) % 97
    return remainder


def detect_iban(source: str):
    lengths = data("iban_lengths.json")
    result = []
    for match in CANDIDATE.finditer(source):
        length = lengths.get(match[1])
        if length is None:
            continue
        remaining = length - 4
        groups, tail = divmod(remaining, 4)
        spaced = r"(?: [A-Z0-9]{4}){" + str(groups) + "}"
        if tail:
            spaced += r" [A-Z0-9]{" + str(tail) + "}"
        body = re.match(r"(?:[A-Z0-9]{" + str(remaining) + "}|" + spaced + r")(?!\w)", source[match.end():match.end() + 50])
        if body is None:
            continue
        end = match.end() + body.end()
        value = source[match.start():end].replace(" ", "")
        if mod97(value) != 1:
            continue
        suggest(result, match.start(), end, FindingCategory.IDENTIFIER, "identifier.iban", "IBAN national length and checksum match; this does not verify an account.")
    return result
