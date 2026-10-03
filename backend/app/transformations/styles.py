"""Pure deterministic replacements; no database, network, logs or random state."""

import hashlib
import hmac
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import phonenumbers as phones

from app.contracts import FindingCategory
from app.detection.dates import MONTH_NAMES, ParsedDate, parse_date

DATA = Path(__file__).with_name("data")
STAND_IN_CATEGORIES = frozenset(
    {"person", "organization", "location", "address", "email", "url", "phone"}
)
MASK_CATEGORIES = {
    "full": frozenset(
        category.value for category in FindingCategory if category != FindingCategory.DATE
    ),
    "last4": frozenset({"phone", "identifier", "national_id", "custom"}),
    "first_letters": frozenset({"person", "organization", "location", "address", "custom"}),
    "email_domain": frozenset({"email"}),
    "email_first": frozenset({"email"}),
    "url_host": frozenset({"url"}),
    "secret_prefix": frozenset({"secret"}),
}
ACTION_STYLES = {
    "label": frozenset({"token", "stand_in", "date_shift"}),
    "redact": frozenset({"token", "partial_mask", "generalize"}),
    "keep": frozenset({"token"}),
}
PREFIX = re.compile(
    r"^(?:github_pat_|gh[pousr]_|[sr]k_(?:live|test)_|xox[bp]-|xwfp-|xapp-|AKIA|ASIA)"
)


class StyleUnavailable(ValueError):
    def __init__(
        self, message="Choose an available style for this finding.", *, code="style_not_available"
    ):
        self.code = code
        super().__init__(message)


@lru_cache(maxsize=8)
def data(name: str):
    return json.loads((DATA / (name + ".json")).read_text(encoding="utf-8"))


def safe_replacement(value: str) -> str:
    if any(character in value for character in "\n\r\t\0"):
        raise StyleUnavailable("This style cannot replace a value that spans lines or cells.")
    return value


def _mask(value: str, exposed: set[int] | None = None) -> str:
    exposed = exposed or set()
    return "".join(
        character if not character.isalnum() or i in exposed else "*"
        for i, character in enumerate(value)
    )


def partial_mask(value: str, pattern: str) -> str:
    exposed: set[int] = set()
    if pattern == "last4":
        indices = [i for i, c in enumerate(value) if c.isalnum()]
        exposed = set(indices[-4:]) if len(indices) >= 8 else set()
    elif pattern == "first_letters":
        exposed = {match.start() for match in re.finditer(r"[^\W\d_]+", value)}
    elif pattern in {"email_domain", "email_first"}:
        local, at, domain = value.rpartition("@")
        if not at or not local or "." not in domain or any(c.isspace() for c in domain):
            raise StyleUnavailable("This value does not have an email shape.")
        if pattern == "email_domain":
            exposed = set(range(len(local) + 1, len(value)))
        else:
            exposed = {0} | set(range(value.rfind(".") + 1, len(value)))
    elif pattern == "url_host":
        try:
            parsed = urlsplit(value)
        except ValueError:
            raise StyleUnavailable("This value does not have a web address shape.") from None
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise StyleUnavailable("This value does not have a web address shape.")
        start = value.find("://") + 3
        end = min(
            [i for character in "/?#" if (i := value.find(character, start)) >= 0],
            default=len(value),
        )
        user_end = value.rfind("@", start, end)
        exposed = set(range(start)) | set(range(user_end + 1 if user_end >= start else start, end))
    elif pattern == "secret_prefix":
        match = PREFIX.match(value)
        exposed = set(range(match.end())) if match else set()
    elif pattern != "full":
        raise StyleUnavailable()
    return safe_replacement(_mask(value, exposed))


def stored_date(value: str, format_code: str | None) -> ParsedDate:
    try:
        parts = format_code.split(":") if format_code else []
        if len(parts) != 7:
            raise ValueError
        parsed = parse_date(value, "US" if parts[1] == "mdy" else "GB", birth=parts[-1] == "1")
        if parsed is None or parsed.format != format_code:
            raise ValueError
        return parsed
    except (ValueError, IndexError, AttributeError):
        raise StyleUnavailable(
            "This date could not be parsed; use a token or correct the finding."
        ) from None


def _ordinal(day: int) -> str:
    return "th" if 10 <= day % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def _case_like(value: str, original: str) -> str:
    if original.isupper():
        return value.upper()
    if original.islower():
        return value.lower()
    if original.istitle():
        return value.title()
    return "".join(
        character.upper() if original[min(i, len(original) - 1)].isupper() else character.lower()
        for i, character in enumerate(value)
    )


def shift_date(value: str, format_code: str | None, offset: int) -> str:
    parsed = stored_date(value, format_code)
    if not 30 <= abs(offset) <= 365:
        raise StyleUnavailable()
    shifted = parsed.value + timedelta(days=offset)
    if not 1900 <= shifted.year <= 2100:
        raise StyleUnavailable(
            "The shifted date would be outside1900–2100.", code="date_shift_out_of_range"
        )
    kind, order, form, width, _ordinal_flag, _comma, _ = parsed.format.split(":")
    values = {"y": shifted.year, "m": shifted.month, "d": shifted.day}
    if kind == "n":
        return form.join(
            str(values[part]).zfill(int(size)) for part, size in zip(order, width, strict=True)
        )
    length, _case = form.split("-")
    month = MONTH_NAMES[shifted.month - 1]
    month = month[:3] if length == "short" else month
    # Preserve the actual separators, whitespace and letter case, including
    # mixed-case month names and uppercase ordinals; the stored code has no value.
    month_pattern = (
        r"\b(?:"
        + "|".join(
            sorted({*MONTH_NAMES, *(name[:3] for name in MONTH_NAMES)}, key=len, reverse=True)
        )
        + r")\b"
    )
    result = re.sub(
        month_pattern, lambda match: _case_like(month, match[0]), value, flags=re.IGNORECASE
    )
    count = 0

    def number(match):
        nonlocal count
        count += 1
        if count == 2:
            return str(shifted.year)
        suffix = re.search(r"[A-Za-z]+$", match[0])
        return str(shifted.day).zfill(int(width)) + (
            _case_like(_ordinal(shifted.day), suffix[0]) if suffix else ""
        )

    return safe_replacement(re.sub(r"[0-9]+(?:st|nd|rd|th)?", number, result, flags=re.IGNORECASE))


def generalize_date(value: str, format_code: str | None, pattern: str, created: date) -> str:
    parsed = stored_date(value, format_code)
    if pattern == "year":
        return str(parsed.value.year)
    if pattern == "month_year":
        if parsed.format.startswith("m:"):
            month = MONTH_NAMES[parsed.value.month - 1]
            month = month[:3] if ":short-" in parsed.format else month
            return f"{month} {parsed.value.year}"
        return (
            f"{parsed.value.year}-{parsed.value.month:02}"
            if ":ymd:" in parsed.format
            else f"{parsed.value.month:02}/{parsed.value.year}"
        )
    if pattern == "age_band" and parsed.birth and parsed.value <= created:
        age = (
            created.year
            - parsed.value.year
            - ((created.month, created.day) < (parsed.value.month, parsed.value.day))
        )
        if age < 18:
            return "aged under 18"
        if age >= 90:
            return "aged 90 or over"
        lower = max(18, (age // 10) * 10)
        return f"aged {lower}–{(age // 10) * 10 + 9}"
    raise StyleUnavailable("Age bands require a parsed birth date no later than this document.")


def validate_style(
    action: str,
    style: str,
    option: str | None,
    category: str,
    *,
    value: str | None = None,
    date_format: str | None = None,
    region: str = "US",
    offset: int | None = None,
    created: date | None = None,
):
    if style not in ACTION_STYLES.get(action, ()):
        raise StyleUnavailable()
    if style in {"token", "stand_in", "date_shift"} and option is not None:
        raise StyleUnavailable()
    if style == "stand_in":
        if category not in STAND_IN_CATEGORIES:
            raise StyleUnavailable("Fictional stand-ins are not available for this category.")
        if category == "phone" and value is not None and phone_candidate(value, region, 0) is None:
            raise StyleUnavailable(
                "No verified fictional phone range is available; choose a partial mask."
            )
    elif style == "partial_mask":
        if category not in MASK_CATEGORIES.get(option, ()):
            raise StyleUnavailable()
        if value is not None:
            partial_mask(value, option)
    elif style == "date_shift":
        if category != "date":
            raise StyleUnavailable()
        if value is not None:
            stored_date(value, date_format)
            if offset is not None:
                shift_date(value, date_format, offset)
    elif style == "generalize":
        if category != "date" or option not in {"month_year", "year", "age_band"}:
            raise StyleUnavailable()
        if value is not None:
            generalize_date(value, date_format, option, created or date.min)


def phone_candidate(original: str, region: str, index: int) -> str | None:
    try:
        parsed = phones.parse(original, region)
        if not phones.is_valid_number(parsed):
            return None
    except phones.NumberParseException:
        return None
    ranges = data("fictional_phone_ranges")
    if parsed.country_code == 1:
        block = ranges["NANP"]
        value = (
            str(parsed.national_number)[:3]
            + block["exchange"]
            + str(block["line_min"] + index % (block["line_max"] - block["line_min"] + 1)).zfill(4)
        )
    else:
        target = phones.region_code_for_number(parsed)
        options = ranges.get(target, [])
        if not options:
            return None
        kind = phones.number_type(parsed)
        name = (
            "mobile"
            if kind in (phones.PhoneNumberType.MOBILE, phones.PhoneNumberType.FIXED_LINE_OR_MOBILE)
            else "geographic"
        )
        options = [item for item in options if item["kind"] == name] or options
        item = options[index % len(options)]
        value = item.get("number") or item["prefix"] + str(
            index // len(options) % (10 ** item["digits"])
        ).zfill(item["digits"])
    return "+" + str(parsed.country_code) + value


def format_phone(candidate: str, original: str) -> str:
    parsed = phones.parse(candidate, None)
    mode = (
        phones.PhoneNumberFormat.INTERNATIONAL
        if original.lstrip().startswith("+")
        else phones.PhoneNumberFormat.NATIONAL
    )
    return safe_replacement(phones.format_number(parsed, mode))


@dataclass(frozen=True)
class StandInGroup:
    id: UUID
    category: str
    label: str
    originals: tuple[str, ...]


def _candidate(seed: bytes, group: StandInGroup, attempt: int, region: str) -> str | None:
    digest = hmac.new(
        seed, f"standin:v1:{group.category}:{group.id}:{attempt}".encode(), hashlib.sha256
    ).digest()
    indices = [int.from_bytes(digest[i : i + 4], "big") for i in range(0, 32, 4)]

    def word(name, index):
        words = data(name)["values"]
        return words[indices[index] % len(words)]

    category = group.category
    given, family = word("given_names", 0), word("family_names", 1)
    if category == "person":
        return f"{given} {family}"
    if category == "organization":
        return f"{word('organization_first', 0)} {word('organization_second', 1)} {word('organization_suffixes', 2)}"
    if category == "location":
        return word("places", 0)
    if category == "address":
        return f"{1 + indices[0] % 9999} {word('street_names', 1)} {('Road', 'Street', 'Lane', 'Way', 'Avenue', 'Drive')[indices[2] % 6]}, {word('places', 3)}"
    if category == "email":
        return f"{given.lower()}.{family.lower()}@example.{('com', 'org', 'net')[indices[2] % 3]}"
    if category == "url":
        return f"https://example.org/{word('organization_second', 0).lower()}-{indices[1] % 100000}"
    if category == "phone" and group.originals:
        return phone_candidate(group.originals[0], region, indices[0])
    return None


def normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _phone_key(value: str, region: str) -> str | None:
    try:
        return phones.format_number(phones.parse(value, region), phones.PhoneNumberFormat.E164)
    except phones.NumberParseException:
        return None


def stand_ins(
    seed: bytes, groups: Sequence[StandInGroup], source: str, region: str
) -> dict[UUID, str | None]:
    if len(seed) != 32:
        raise StyleUnavailable()
    originals = {normalized(value) for group in groups for value in group.originals}
    original_phones = {
        _phone_key(value, region)
        for group in groups
        if group.category == "phone"
        for value in group.originals
    }
    normalized_source = normalized(source)
    used: set[str] = set()
    result = {}
    for group in sorted(groups, key=lambda item: (item.label, str(item.id))):
        for attempt in range(50):
            value = _candidate(seed, group, attempt, region)
            if value is None:
                break
            if group.category == "phone" and _phone_key(value, region) in original_phones:
                continue
            comparable = normalized(value)
            if comparable in originals or comparable in used or comparable in normalized_source:
                continue
            # Also compare the national rendering of a phone stand-in.
            national = (
                normalized(format_phone(value, group.originals[0]))
                if group.category == "phone"
                else comparable
            )
            if national in originals or national in normalized_source or national in used:
                continue
            result[group.id] = safe_replacement(value)
            used.update({comparable, national})
            break
        else:
            result[group.id] = None
        result.setdefault(group.id, None)
    return result
