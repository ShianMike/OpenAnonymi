"""Whole URLs remove embedded tokens; identifiers have exact token boundaries."""

import pytest

from app.detection.web import detect_urls, detect_web_identifiers


@pytest.mark.parametrize('value,expected,rule', [
    ('(https://example.test/a_(b)).', 'https://example.test/a_(b)', 'url.web'),
    ('www.example.test/path?token=fictional', 'www.example.test/path?token=fictional', 'url.query_token'),
    ('https://example.test:443/a?q=hello#part', 'https://example.test:443/a?q=hello#part', 'url.web'),
    ('https://example.test:99999/a',None,None), ('http://',None,None),
    ('https://example..test/a',None,None), ('https://example.test/' + 'a'*2048,None,None),
])
def test_urls(value, expected, rule):
    source = '😀 ' + value
    rows = detect_urls(source)
    assert [source[x.span.start:x.span.end] for x in rows] == ([expected] if expected else [])
    if rows:
        assert rows[0].rule_id == rule


def test_ipv6_handles_usernames_and_false_traps():
    source = '😀 [2001:db8::8] ::1 :: ::: bad2001:db8::8 2001:db8::8%eth0 @river.sage (@luna_8) @media @override @everyone email@example.test username: nora_71 login = sage-42'
    rows = detect_web_identifiers(source)
    assert [source[x.span.start:x.span.end] for x in rows] == ['2001:db8::8','@river.sage','@luna_8','nora_71','sage-42']


def test_mapped_ipv6_and_handle_length():
    source = '::ffff:192.0.2.9 @' + 'a'*31 + ' @.no @no. @yes '
    rows = detect_web_identifiers(source)
    assert [source[x.span.start:x.span.end] for x in rows] == ['::ffff:192.0.2.9','@yes']


@pytest.mark.parametrize("value", ["2001:db8::42", "::ffff:192.0.2.9"])
def test_ipv6_sentence_period_stays_outside_the_exact_address_span(value):
    source = "😀 System: " + value + ". Next sentence."
    rows = detect_web_identifiers(source)
    assert len(rows) == 1 and rows[0].rule_id == "identifier.ipv6"
    assert source[rows[0].span.start:rows[0].span.end] == value


@pytest.mark.parametrize("value", ["2001:db8::42.9", "2001:db8::42%eth0", "bad2001:db8::42", ":::."])
def test_ipv6_trimming_does_not_admit_invalid_or_partial_addresses(value):
    assert detect_web_identifiers(value) == []
