"""Local bounded URLs, IPv6, handles and contextual usernames."""

import ipaddress
import re
from urllib.parse import parse_qsl, urlsplit

from app.contracts import FindingCategory
from app.detection.support import suggest

KEY_NAMES = frozenset(["password", "passwd", "pwd", "pass", "secret", "client_secret", "secret_key", "api_key", "apikey", "api-key", "access_token", "auth_token", "token", "private_key"])
TOKEN_QUERY_NAMES = KEY_NAMES | {"sig", "signature", "code", "session", "sid", "key"}
URL = re.compile(r"(?<!\w)(?:https?://|www\.)[^\s<>\"\x00-\x1f]{1,2048}(?![^\s<>\"\x00-\x1f])", re.IGNORECASE)
IPV6 = re.compile(r"(?<![\w:.%])[0-9A-Fa-f:.]{2,45}(?![\w:.%])")
HANDLE = re.compile(r"(?<![^\s(\[{])@([A-Za-z0-9_](?:[A-Za-z0-9_.]{0,28}[A-Za-z0-9_])?)(?![A-Za-z0-9_.@-])")
AT_WORDS = frozenset(["media", "import", "charset", "font-face", "keyframes", "supports", "page", "namespace", "param", "return", "returns", "type", "override", "deprecated", "see", "since", "throws", "example", "todo", "here", "everyone", "channel", "all"])
USERNAME = re.compile(r"\b(?:username|user name|user id|userid|login|handle)[ \t]{0,12}[:=][ \t]{0,12}([A-Za-z0-9._-]{3,64})(?![\w.-])", re.IGNORECASE)


def trim_url(value: str):
    value = value.rstrip(".,;:!?'")
    while value and value[-1] in ")]}":
        closing = value[-1]
        opening = {')':'(', ']':'[', '}':'{'}[closing]
        if value.count(closing) <= value.count(opening):
            break
        value = value[:-1].rstrip(".,;:!?'")
    return value


def detect_urls(source: str):
    result = []
    for match in URL.finditer(source):
        value = trim_url(match[0])
        if len(value) > 2048:
            continue
        try:
            parsed = urlsplit("https://" + value if value.lower().startswith("www.") else value)
            host = parsed.hostname
            port = parsed.port
            if not host or port is not None and not 1 <= port <= 65535:
                continue
            if ":" in host:
                ipaddress.IPv6Address(host)
            elif not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?", host) or ".." in host:
                continue
            token = any(key.casefold() in TOKEN_QUERY_NAMES for key, _ in parse_qsl(parsed.query))
        except ValueError:
            continue
        suggest(result, match.start(), match.start() + len(value), FindingCategory.URL, "url.query_token" if token else "url.web", "Web address containing an access token in its query." if token else "Web address; review its host, path and query.")
    return result


def detect_web_identifiers(source: str):
    result = []
    for match in IPV6.finditer(source):
        if match[0].count(":") < 2:
            continue
        try:
            address = ipaddress.IPv6Address(match[0])
        except ValueError:
            continue
        if address.is_unspecified or address == ipaddress.IPv6Address("::1"):
            continue
        suggest(result, match.start(), match.end(), FindingCategory.IDENTIFIER, "identifier.ipv6", "Valid IPv6 address syntax; review whether it identifies a system.")
    for match in HANDLE.finditer(source):
        if match[1].casefold() in AT_WORDS:
            continue
        suggest(result, match.start(), match.end(), FindingCategory.IDENTIFIER, "identifier.handle", "Account handle; review whether it identifies a person.")
    for match in USERNAME.finditer(source):
        suggest(result, match.start(1), match.end(1), FindingCategory.IDENTIFIER, "identifier.username", "Username following an explicit account context.")
    return result
