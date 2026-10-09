"""Authored credentials, bounded PEM blocks and placeholders."""

import pytest

from app.detection.secrets import detect_secrets


@pytest.mark.parametrize('value,rule', [
    ('AKIA'+'A1'*8,'aws_access_key'), ('ASIA'+'B2'*8,'aws_access_key'),
    ('ghp_'+'A1'*18,'github_token'), ('github_pat_'+'B2_'*10,'github_token'),
    ('sk_test_'+'Ab1'*8,'stripe_key'), ('rk_live_'+'Bc2'*8,'stripe_key'),
    ('xoxb-'+'1-2-'*5,'slack_token'), ('xwfp-'+'a-b-'*5,'slack_token'),
    ('xoxp-'+'1-2-'*5,'slack_token'), ('xapp-'+'c-d-'*5,'slack_token'),
    ('eyJ'+'Ab1'*5+'.eyJ'+'Bc2'*5+'.'+'Cd3'*5,'jwt'),
])
def test_credential_prefixes(value, rule):
    source = '😀 Credential ' + value + ' end'
    rows = detect_secrets(source)
    assert any(source[x.span.start:x.span.end] == value and x.rule_id == 'secret.'+rule for x in rows)


def test_context_value_only_and_placeholder_traps():
    source = 'password="Fictional7!" api_key: Testing7654 token=changeme secret=xxxxxxxxxx pwd=${SECRET_VALUE} pass=<placeholder> token=redacted private_key={{template}} pk_test_Ab12Cd34Ef56'
    rows = detect_secrets(source)
    assert [source[x.span.start:x.span.end] for x in rows] == ['Fictional7!','Testing7654']


def test_pem_matching_marker_and_bound():
    block = '-----BEGIN RSA PRIVATE KEY-----\nsynthetic bytes only\n-----END RSA PRIVATE KEY-----'
    rows = detect_secrets(block)
    assert len(rows) == 1 and rows[0].span.start == 0 and rows[0].span.end == len(block)
    assert detect_secrets(block.replace('END RSA','END EC')) == []
    assert detect_secrets(block.replace('synthetic bytes only','A'*16384)) == []
    assert detect_secrets('-----BEGIN PRIVATE KEY-----\n' * 2000) == []
