"""Exact independently annotated synthetic positives, near misses and traps."""

import json
import os
from pathlib import Path

import pytest

from app.contracts import FindingCategory, SourceSpan
from app.detection.addresses import detect_addresses
from app.detection.dates import detect_dates
from app.detection.iban import detect_iban
from app.detection.identifiers import detect_identifiers
from app.detection.national_ids import detect_national_ids
from app.detection.rules import Suggestion, detect_suggestions, resolve_overlaps
from app.detection.secrets import detect_secrets
from app.detection.web import detect_urls, detect_web_identifiers

CORPORA = sorted((Path(__file__).parent / 'fixtures/detection_corpus').glob('*.json'))
REPORT = {}


def run(rule, source, region):
    if rule.startswith('date.'):
        return detect_dates(source, region)
    if rule.startswith('address.'):
        return detect_addresses(source)
    if rule.startswith('national_id.'):
        return detect_national_ids(source)
    if rule.startswith('secret.'):
        return detect_secrets(source)
    if rule.startswith('url.'):
        return detect_urls(source)
    if rule == 'identifier.iban':
        return detect_iban(source)
    if rule in {'identifier.ipv6', 'identifier.handle', 'identifier.username'}:
        return detect_web_identifiers(source)
    if rule.startswith('identifier.'):
        return detect_identifiers(source)
    return detect_suggestions(source, {FindingCategory.PHONE if rule.startswith('phone.') else FindingCategory.EMAIL}, region)


@pytest.mark.parametrize('path', CORPORA, ids=lambda p:p.stem)
def test_corpus_exact_ground_truth_and_no_network(path, monkeypatch):
    import requests
    monkeypatch.setattr(requests.sessions.Session,'request',lambda *a,**k:pytest.fail('Detection must stay local.'))
    corpus = json.loads(path.read_text(encoding='utf-8'))
    rule = corpus['rule_id']
    gold = predicted = correct = 0
    for row in corpus['rows']:
        actual = [{'start':x.span.start,'end':x.span.end,'category':x.category.value,'rule_id':x.rule_id} for x in run(rule,row['text'],row['region'])]
        gold += len(row['expected']); predicted += len(actual)
        correct += sum(item in row['expected'] for item in actual)
        assert actual == row['expected'], row['text']
    REPORT[rule] = {'cases':len(corpus['rows']),'gold':gold,'predicted':predicted,'correct':correct,'precision':correct/predicted if predicted else 1,'recall':correct/gold if gold else 1}


def test_corpus_report():
    target = os.getenv('OPENANONYMI_CORPUS_REPORT')
    if target:
        assert len(REPORT) == len(CORPORA)
        Path(target).write_text(json.dumps(REPORT,indent=2)+'\n',encoding='utf-8')


def test_longest_then_precedence_then_start():
    def item(start,end,category,rule='synthetic'):
        return Suggestion(SourceSpan(start=start,end=end),category,rule,'2','Synthetic comparison')
    url=item(0,30,FindingCategory.URL)
    secret=item(10,30,FindingCategory.SECRET)
    assert resolve_overlaps([secret,url]) == [url]
    same_span = [item(0,9,x) for x in (FindingCategory.PHONE,FindingCategory.EMAIL,FindingCategory.NATIONAL_ID,FindingCategory.SECRET)]
    assert resolve_overlaps(same_span) == [same_span[-1]]
    early, late = item(0,10,FindingCategory.DATE),item(5,15,FindingCategory.DATE)
    assert resolve_overlaps([late,early]) == [early]
    source='https://example.test/?token=Fictional7654'
    rows=detect_suggestions(source,{FindingCategory.URL,FindingCategory.SECRET},'US')
    assert len(rows)==1 and rows[0].rule_id=='url.query_token' and rows[0].span.end==len(source)
