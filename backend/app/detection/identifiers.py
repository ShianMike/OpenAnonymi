"""Bounded syntax/checksum suggestions for network and payment identifiers."""

import ipaddress
import re

from app.contracts import FindingCategory, SourceSpan
from app.detection.rules import MAX_SUGGESTIONS, DetectionLimitError, Suggestion

IP = re.compile(r"(?<![\w.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?!\w|\.[0-9])")
CARD = re.compile(r"(?<!\w)(?:[0-9][ -]?){12,18}[0-9](?!\w)")


def luhn(digits: str) -> bool:
    if len(set(digits)) <= 1:
        return False
    parity = len(digits) % 2
    total = 0
    for index, character in enumerate(digits):
        value = int(character)
        if index % 2 == parity:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def detect_identifiers(source: str) -> list[Suggestion]:
    result = []
    for pattern, kind in ((IP, "ipv4"), (CARD, "payment_checksum")):
        for match in pattern.finditer(source):
            if kind == "ipv4":
                try:
                    ipaddress.IPv4Address(match.group())
                except ValueError:
                    continue
            elif not luhn(re.sub(r"[^0-9]", "", match.group())):
                continue
            if len(result) >= MAX_SUGGESTIONS:
                raise DetectionLimitError("too_many_suggestions")
            result.append(
                Suggestion(
                    SourceSpan(start=match.start(), end=match.end()),
                    FindingCategory.IDENTIFIER,
                    f"identifier.{kind}",
                    "1",
                    "Valid IPv4 address syntax; review whether it identifies a system."
                    if kind == "ipv4"
                    else "Matches payment card length and checksum; validity does not imply a real account.",
                )
            )
    return result
