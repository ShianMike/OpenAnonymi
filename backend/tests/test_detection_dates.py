"""Exact spans and stable formatting, including region ambiguity and manual dates."""

from datetime import date

import pytest

from app.detection.dates import detect_dates, parse_date


@pytest.mark.parametrize('value,region,expected', [
    ('2024-02-29','US',date(2024,2,29)), ('2023-02-29','US',None),
    ('2100-02-29','PH',None), ('1899-12-31','US',None), ('2101-01-01','PH',None),
    ('3/4/2026','US',date(2026,3,4)), ('3/4/2026','PH',date(2026,4,3)),
    ('13.4.2026','US',date(2026,4,13)), ('4-13-2026','GB',date(2026,4,13)),
    ('31/4/2026','PH',None), ('3 October 2026','GB',date(2026,10,3)),
    ('3rd October 2026','PH',date(2026,10,3)), ('October 3, 2026','US',date(2026,10,3)),
    ('3th October 2026','PH',None), ('11st October 2026','PH',None),
    ('Oct 3, 2026','US',date(2026,10,3)), ('3 Oct 2026','PH',date(2026,10,3)),
    ('October 2026','US',None), ('3/4/26','US',None), ('12:34:56','US',None),
])
def test_calendar_formats(value, region, expected):
    parsed = parse_date(value, region)
    assert (parsed.value if parsed else None) == expected


def test_birth_context_and_format_do_not_store_values():
    source = '😀 DOB: 03/04/2026; appointment 2026-10-03\nBorn yesterday.\n3 October 2026'
    rows = detect_dates(source, 'US')
    assert [source[x.span.start:x.span.end] for x in rows] == ['03/04/2026','2026-10-03','3 October 2026']
    assert rows[0].rule_id == 'date.birth'
    assert rows[0].date_format == 'n:mdy:/:224:0:0:1'
    assert rows[1].date_format == 'n:ymd:-:422:0:0:1'  # Same-line DOB within 40 characters.
    assert rows[2].rule_id == 'date.month_name'
    assert all('2026' not in x.date_format for x in rows)
