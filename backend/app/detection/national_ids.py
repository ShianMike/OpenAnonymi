"""Explicit national-ID formats; all matched values stay in protected source."""

import re
from datetime import date

from app.contracts import FindingCategory
from app.detection.support import data, suggest

SSN = re.compile(r"(?<!\w)([0-9]{3})-([0-9]{2})-([0-9]{4})(?!\w)")
NINO = re.compile(r"(?<!\w)([A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z])[ ]?[0-9]{2}[ ]?[0-9]{2}[ ]?[0-9]{2}[ ]?[A-D](?!\w)")
NRIC = re.compile(r"(?<!\w)([STFGM])([0-9]{7})([A-Z])(?!\w)")
MYKAD = re.compile(r"(?<!\w)([0-9]{2})([0-9]{2})([0-9]{2})-([0-9]{2})-[0-9]{4}(?!\w)")


def mykad_date(year, month, day):
    for century in (1900, 2000):
        try:
            date(century + year, month, day)
            return True
        except ValueError:
            pass
    return False


def detect_national_ids(source: str):
    result = []
    for match in SSN.finditer(source):
        area, group, serial = map(int, match.groups())
        if area in (0, 666) or area >= 900 or not group or not serial:
            continue
        suggest(result, match.start(), match.end(), FindingCategory.NATIONAL_ID, "national_id.us_ssn", "Hyphenated US Social Security number format with unassigned ranges excluded.")
    for match in NINO.finditer(source):
        if match[1] in {'BG', 'GB', 'KN', 'NK', 'NT', 'TN', 'ZZ'}:
            continue
        suggest(result, match.start(), match.end(), FindingCategory.NATIONAL_ID, "national_id.uk_nino", "UK National Insurance number format.")
    checksums = data("sg_nric_checksums.json")
    for match in NRIC.finditer(source):
        prefix = checksums['prefixes'].get(match[1])
        if prefix:
            total = sum(int(digit) * weight for digit, weight in zip(match[2], checksums['weights'], strict=True)) + prefix['offset']
            if match[3] != prefix['table'][total % 11]:
                continue
        suggest(result, match.start(), match.end(), FindingCategory.NATIONAL_ID, "national_id.sg_nric", "Singapore NRIC/FIN checksum format." if prefix else "Singapore NRIC/FIN format (M checksum not verified).")
    birth_codes = data("mykad_birth_codes.json")
    for match in MYKAD.finditer(source):
        if match[4] not in birth_codes or not mykad_date(*map(int, match.groups()[:3])):
            continue
        suggest(result, match.start(), match.end(), FindingCategory.NATIONAL_ID, "national_id.my_mykad", "Hyphenated Malaysian MyKad format with calendar date and official birth-place code.")
    return result
