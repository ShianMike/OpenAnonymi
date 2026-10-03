"""Calendar-validated dates with a content-free format for later replacement."""

import re
from dataclasses import dataclass
from datetime import date

from app.contracts import FindingCategory
from app.detection.support import suggest

MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")
MONTHS = {name.casefold(): i for i, name in enumerate(MONTH_NAMES, 1)}
MONTHS.update({name[:3].casefold(): i for i, name in enumerate(MONTH_NAMES, 1)})
MONTH = "(?:" + "|".join(sorted(MONTHS, key=len, reverse=True)) + ")"
NUMERIC = re.compile(r"(?<![\w./-])(?:[12][0-9]{3}-[0-9]{1,2}-[0-9]{1,2}|[0-9]{1,2}([/.-])[0-9]{1,2}\1[12][0-9]{3})(?![\w./-])")
NAMED = re.compile(r"(?<!\w)(?:[0-9]{1,2}(?:st|nd|rd|th)? " + MONTH + r" [12][0-9]{3}|" + MONTH + r" [0-9]{1,2}(?:st|nd|rd|th)?(?:,)? [12][0-9]{3})(?!\w)", re.IGNORECASE)
BIRTH = re.compile(r"\b(?:DOB|D\.O\.B\.|date of birth|birth date|birthdate|born|birthday)(?:\b|(?<=\.))", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedDate:
    value: date
    format: str
    birth: bool


def _valid(year, month, day):
    if not 1900 <= year <= 2100:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_date(value: str, region: str, *, birth: bool = False) -> ParsedDate | None:
    """Codes contain formatting only: kind:order:separator:widths:ordinal:comma:birth."""
    if len(value) > 40:
        return None
    if NUMERIC.fullmatch(value):
        parts = re.split(r"[/.-]", value)
        separator = next(c for c in value if c in "/.-")
        if len(parts[0]) == 4:
            order = "ymd"
            year, month, day = map(int, parts)
            parsed = _valid(year, month, day)
        else:
            a, b, year = map(int, parts)
            order = "mdy" if region == "US" else "dmy"
            parsed = _valid(year, a, b) if order == "mdy" else _valid(year, b, a)
            if parsed is None:
                order = "dmy" if order == "mdy" else "mdy"
                parsed = _valid(year, b, a) if order == "dmy" else _valid(year, a, b)
        if parsed:
            return ParsedDate(parsed, f"n:{order}:{separator}:{''.join(str(len(x)) for x in parts)}:0:0:{int(birth)}", birth)
        return None
    if not NAMED.fullmatch(value):
        return None
    month_text = re.search(MONTH, value, re.IGNORECASE)[0]
    numbers = re.findall(r"[0-9]+", value)
    day, year = map(int, numbers)
    parsed = _valid(year, MONTHS[month_text.casefold()], day)
    if parsed is None:
        return None
    order = "dmy" if value[0].isdigit() else "mdy"
    # Case and abbreviation are formatting, not the source month or date.
    form = "short" if len(month_text) == 3 else "long"
    case = "upper" if month_text.isupper() else "lower" if month_text.islower() else "title"
    ordinal = bool(re.search(r"[0-9](?:st|nd|rd|th)", value, re.IGNORECASE))
    if ordinal:
        suffix = "th" if 10 <= day % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        if re.search(r"[0-9](st|nd|rd|th)", value, re.IGNORECASE)[1].lower() != suffix:
            return None
    code = f"m:{order}:{form}-{case}:{len(numbers[0])}:{int(ordinal)}:{int(',' in value)}:{int(birth)}"
    return ParsedDate(parsed, code, birth)


def format_for_span(source: str, start: int, end: int, region: str) -> str | None:
    before = source[max(0, start - 40):start].rsplit("\n", 1)[-1].rsplit("\r", 1)[-1]
    parsed = parse_date(source[start:end], region, birth=bool(BIRTH.search(before)))
    return parsed.format if parsed else None


def detect_dates(source: str, region: str):
    result = []
    for pattern, kind, reason in ((NUMERIC, "numeric", "Calendar-valid numeric date."), (NAMED, "month_name", "Calendar-valid English month-name date.")):
        for match in pattern.finditer(source):
            code = format_for_span(source, match.start(), match.end(), region)
            if code is None:
                continue
            birth = code.endswith(":1")
            suggest(result, match.start(), match.end(), FindingCategory.DATE, "date.birth" if birth else f"date.{kind}", "Date of birth." if birth else reason, date_format=code)
    return result
