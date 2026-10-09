"""Recognizable credentials and explicit context, with bounded candidate work."""

import re

from app.contracts import FindingCategory
from app.detection.support import suggest
from app.detection.web import KEY_NAMES

PATTERNS = (
    ("aws_access_key", re.compile(r"(?<!\w)(?:AKIA|ASIA)[A-Z0-9]{16}(?!\w)")),
    ("github_token", re.compile(r"(?<!\w)(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{22,255})(?!\w)")),
    ("stripe_key", re.compile(r"(?<!\w)(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{10,247}(?!\w)")),
    ("slack_token", re.compile(r"(?<![\w-])(?:xoxb|xwfp|xoxp|xapp)-[A-Za-z0-9-]{10,250}(?![\w-])")),
    ("jwt", re.compile(r"(?<![\w.-])eyJ[A-Za-z0-9_-]{8,4096}\.eyJ[A-Za-z0-9_-]{8,8192}\.[A-Za-z0-9_-]{8,4096}(?![\w.-])")),
)
CONTEXT = re.compile(r"(?<![\w-])(?:" + "|".join(sorted(KEY_NAMES, key=len, reverse=True)) + r")[ \t]{0,12}[:=][ \t]{0,12}[\"']?([^\s\"']{8,256})(?![^\s\"'])", re.IGNORECASE)
BEGIN = re.compile(r"(?m)^-----BEGIN (?:[A-Z ]{0,20})PRIVATE KEY-----[ \t]{0,8}\r?$", re.MULTILINE)
PLACEHOLDERS = frozenset(["changeme", "change-me", "password", "example", "redacted", "null", "none", "true", "false"])


def placeholder(value):
    value = value.casefold()
    return value in PLACEHOLDERS or set(value) <= {'*', 'x'} or value.startswith(('<', '${', '{{'))


def detect_secrets(source: str):
    result = []
    for rule, pattern in PATTERNS:
        for match in pattern.finditer(source):
            suggest(result, match.start(), match.end(), FindingCategory.SECRET, f"secret.{rule}", "Recognizable credential format; remove it and consider rotating the credential.")
    # Each search has a fixed 16 KiB window and rejects intervening BEGIN lines.
    for match in BEGIN.finditer(source):
        marker = match[0].rstrip(" \t\r").replace("BEGIN", "END", 1)
        end = source.find(marker, match.end(), min(len(source), match.start() + 16_384))
        if end < 0 or source.find("-----BEGIN ", match.end(), end) >= 0:
            continue
        if end and source[end - 1] != '\n' or end + len(marker) < len(source) and source[end + len(marker)] not in '\r\n':
            continue
        suggest(result, match.start(), end + len(marker), FindingCategory.SECRET, "secret.pem_private_key", "PEM private-key block; remove it and consider rotating the key.")
    for match in CONTEXT.finditer(source):
        if placeholder(match[1]):
            continue
        suggest(result, match.start(1), match.end(1), FindingCategory.SECRET, "secret.key_value", "Value following an explicit credential key; review and remove sensitive credentials.")
    return result
