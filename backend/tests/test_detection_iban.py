"""Country length, grouped formats, mod-97, surrounding prose and near misses."""

import pytest

from app.detection.iban import detect_iban


@pytest.mark.parametrize('value,valid', [
    ('GB82 WEST 1234 5698 7654 32',True), ('GB82WEST12345698765432',True),
    ('DE89 3704 0044 0532 0130 00',True), ('NO93 8601 1117 947',True),
    ('GB83 WEST 1234 5698 7654 32',False), ('ZZ82WEST12345698765432',False),
    ('GB82  WEST 1234 5698 7654 32',False), ('GB82WEST123456987654321',False),
    ('gb82west12345698765432',False),
])
def test_iban(value, valid):
    source = '😀 Account ' + value + ' NEXT WORD'
    rows = detect_iban(source)
    assert [source[x.span.start:x.span.end] for x in rows] == ([value] if valid else [])
