"""Bounded refusals and detector work on 100,000-code-point adversarial inputs."""

import json
import os
from pathlib import Path
from time import perf_counter

import pytest

from app.contracts import FindingCategory
from app.detection.rules import DetectionLimitError, detect_suggestions
from tests.test_detection_corpus import run

RULES = ['date.numeric','address.us','national_id.us_ssn','secret.key_value','url.web','identifier.iban','identifier.ipv6','identifier.ipv4','email.common_syntax','phone.libphonenumber_valid']
INPUTS = {'at':'@','pem':'-----BEGIN PRIVATE KEY-----\n','digits':'1234567890123456789 - ','colon':':','dots':'.'}
REPORT = {}


@pytest.mark.parametrize('rule', RULES)
@pytest.mark.parametrize('kind', INPUTS)
def test_adversarial_detector_budget(rule, kind):
    unit=INPUTS[kind]; source=(unit*(100_000//len(unit)+1))[:100_000]
    started=perf_counter(); failure=None
    try:
        run(rule,source,'US')
    except DetectionLimitError as exc:
        failure=exc.code
    elapsed=perf_counter()-started
    REPORT[f'{rule}/{kind}']={'code_points':len(source),'seconds':round(elapsed,6),'bounded_refusal':failure}
    assert elapsed<2


def test_performance_report():
    target=os.getenv('OPENANONYMI_DETECTOR_TIMING_REPORT')
    if target:
        assert len(REPORT)==len(RULES)*len(INPUTS)
        Path(target).write_text(json.dumps(REPORT,indent=2)+'\n',encoding='utf-8')


def test_global_suggestion_cap():
    with pytest.raises(DetectionLimitError,match='too_many_suggestions'):
        detect_suggestions('2026-10-03\n'*1001,{FindingCategory.DATE},'US')
