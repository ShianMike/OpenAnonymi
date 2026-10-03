"""Street components required; same or previous line within 120 characters."""

import pytest

from app.detection.addresses import detect_addresses


@pytest.mark.parametrize('value,rule', [
    ('42 Maple Road, Brookvale, CA 90210','address.us'),
    ('42 Maple Rd Apt 3, Brookvale CA 90210-1234','address.us'),
    ('Blk 123 River Road #02-01, Singapore 123456','address.sg'),
    ('10 Rose Street, London SW1A 1AA','address.uk'),
    ('10 Rose Street\nLondon SW1A 1AA','address.uk'),
    ('90210',None), ('123456',None), ('SW1A 1AA',None),
    ('42 Maple Road, ZZ 90210',None), ('10 Rose Street SW1A 1CI',None),
    ('Blk 123 River Road, Singapore 993456',None),
    ('10 Rose Street\nneutral\nLondon SW1A 1AA',None),
])
def test_address_context(value, rule):
    source = '😀 ' + value
    rows = detect_addresses(source)
    assert [source[x.span.start:x.span.end] for x in rows] == ([value] if rule else [])
    if rows:
        assert rows[0].rule_id == rule
