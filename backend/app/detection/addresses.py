"""Postal anchors plus nearby street components; postal codes alone are ignored."""

import re

from app.contracts import FindingCategory
from app.detection.support import data, suggest

SG_POSTAL = re.compile(r"(?<!\w)[0-9]{6}(?!\w)")
US_POSTAL = re.compile(r"(?<![\w-])[0-9]{5}(?:-[0-9]{4})?(?![\w-])")
UK_POSTAL = re.compile(r"(?<!\w)(?:GIR ?0AA|[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][ABD-HJLNP-UW-Z]{2})(?!\w)", re.IGNORECASE)
SG_COMPONENT = re.compile(r"\b(?:Blk|Block)[ \t]+[0-9]{1,6}[A-Z]?\b|#[0-9]{2}-[0-9]{2,5}[A-Z]?\b|\b(?:[0-9]{1,6}[A-Z]?[ \t]+)?(?:[A-Za-z][A-Za-z'-]*[ \t]+){1,4}(?:Road|Street|Avenue|Drive|Crescent|Lane|Walk|Rise|Close|Way|Central|Link|Place|Park|Grove|Terrace)\b", re.IGNORECASE)
UK_COMPONENT = re.compile(r"(?<!\w)[0-9]{1,6}[A-Z]?[ \t]+(?:[A-Za-z][A-Za-z'.-]*[ \t]+){1,4}(?:Road|Street|Lane|Avenue|Close|Drive|Way|Gardens|Crescent|Place|Terrace|Court|Square|Hill|Grove|Mews|Row|Walk|Park)\b", re.IGNORECASE)
STREET_NAME = r"(?<!\w)[0-9]{1,6}[A-Z]?[ \t]+(?:[A-Za-z][A-Za-z'.-]*[ \t]+){1,4}"


def window(source, start):
    lower = max(0, start - 120)
    # At most this and the previous line; CRLF counts as one line.
    earlier = source.rfind('\n', lower, start)
    if earlier >= 0:
        previous = source.rfind('\n', lower, earlier)
        if previous >= 0:
            lower = previous + 1
    return lower, source[lower:start]


def detect_addresses(source: str, entities=()):
    result = []
    us_suffixes = '|'.join(data("us_street_suffixes.json"))
    us_street = re.compile(STREET_NAME + '(?:' + us_suffixes + r')\b', re.IGNORECASE)
    states = set(data("us_states.json"))
    sectors = set(data("sg_postal_sectors.json"))
    for match in SG_POSTAL.finditer(source):
        if match[0][:2] not in sectors:
            continue
        lower, before = window(source, match.start())
        component = SG_COMPONENT.search(before)
        if component:
            suggest(result, lower + component.start(), match.end(), FindingCategory.ADDRESS, "address.sg", "Singapore postal-sector format with a nearby street, block or unit component.")
    for match in US_POSTAL.finditer(source):
        lower, before = window(source, match.start())
        state = re.search(r'\b([A-Z]{2})[ ,\t\r\n]*$', before, re.IGNORECASE)
        if state is None or state[1].upper() not in states:
            continue
        component = us_street.search(before[:state.start()])
        if component is None:
            continue
        tail = before[component.end():state.start()]
        if not re.fullmatch(r"[A-Za-z0-9 ,.#'\t\r\n-]{0,70}", tail):
            continue
        suggest(result, lower + component.start(), match.end(), FindingCategory.ADDRESS, "address.us", "US street component, state or possession abbreviation and ZIP format.")
    for match in UK_POSTAL.finditer(source):
        lower, before = window(source, match.start())
        component = UK_COMPONENT.search(before)
        start = lower + component.start() if component else None
        if start is None:
            locations = [entity.span.start for entity in entities if entity.category == FindingCategory.LOCATION and lower <= entity.span.start < entity.span.end <= match.start()]
            if locations:
                start = min(locations)
        if start is not None:
            suggest(result, start, match.end(), FindingCategory.ADDRESS, "address.uk", "UK postcode format with a nearby street or English place suggestion.")
    return result
