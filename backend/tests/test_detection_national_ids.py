"""Source-confirmed formats and documented checksum fallback."""

import pytest

from app.detection.national_ids import detect_national_ids


@pytest.mark.parametrize('value,valid', [
    ('123-45-6789',True), ('000-45-6789',False), ('666-45-6789',False),
    ('900-45-6789',False), ('123-00-6789',False), ('123-45-0000',False),
    ('QQ123456A',False), ('AB 12 34 56 C',True), ('BG123456A',False),
    ('AB123456',False), ('AB123456E',False), ('AO123456A',False),
    ('S1234567D',True), ('S1234567A',False), ('T1234567J',True),
    ('F1234567N',True), ('G1234567X',True), ('M1234567A',True),
    ('000229-01-1234',True), ('990229-01-1234',False), ('901231-71-1234',True),
    ('901231-00-1234',False), ('900431-01-1234',False),
    ('901231011234',False), ('123456789',False), ('ab123456a',False),
])
def test_national_formats(value, valid):
    source = '😀 ID ' + value + ' end'
    rows = detect_national_ids(source)
    assert [source[x.span.start:x.span.end] for x in rows] == ([value] if valid else [])
    assert all(x.rule_version == '2' and x.reason for x in rows)


def test_m_prefix_is_honestly_format_only():
    assert 'checksum not verified' in detect_national_ids('M1234567A')[0].reason
