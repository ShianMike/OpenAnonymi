"""Real saved scans, labels, version invalidation, defaults and manual date undo."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts import AUTOMATIC_CATEGORIES, LABEL_PREFIXES, FindingCategory
from app.db.models import Finding, ScanRun
from tests.intake_support import _draft_body, _login


def test_category_contract_and_legacy_prefixes():
    assert set(LABEL_PREFIXES) == set(FindingCategory)
    assert len(set(LABEL_PREFIXES.values())) == len(FindingCategory)
    assert AUTOMATIC_CATEGORIES == set(FindingCategory) - {FindingCategory.CUSTOM}
    for category in list(FindingCategory)[:8]:
        assert LABEL_PREFIXES[category] == category.value.upper()
    assert LABEL_PREFIXES[FindingCategory.NATIONAL_ID] == 'ID'


def test_opt_in_scan_labels_formats_and_completed_scan_stay_stable(intake_site):
    owner, _, engine, workspace, _ = intake_site
    headers = _login(owner, 'intake-owner@example.invalid')
    source = '😀 DOB: 3 October 2026\nURL https://example.test/path\npassword=Fictional765!\nID 123-45-6789'
    default = owner.post('/api/v1/documents', json=_draft_body(workspace, source=source), headers=headers).json()
    old_base = '/api/v1/documents/' + default['version']['document_id']
    assert owner.get(old_base+'/source').json()['categories'] == ['email','phone']
    scanned_default = owner.post(old_base+'/scan', json={'expected':default['version']}, headers=headers).json()
    assert all(x['category'] not in {'date','url','secret','national_id'} for x in scanned_default['suggestions'])
    categories = ['date','url','secret','national_id']
    created = owner.post('/api/v1/documents', json=_draft_body(workspace, source=source, categories=categories), headers=headers)
    assert created.status_code == 201
    version = created.json()['version']; base = '/api/v1/documents/'+version['document_id']
    scan = owner.post(base+'/scan', json={'expected':version}, headers=headers).json()
    assert {x['category'] for x in scan['suggestions']} == set(categories)
    findings = owner.get(base+'/findings').json()
    assert all(x['action'] is None for x in findings['findings'])
    with Session(engine) as session:
        row = session.scalar(select(Finding).where(Finding.document_id == UUID(version['document_id']), Finding.category == 'date'))
        assert row.date_format == 'm:dmy:long-title:1:0:0:1'
        assert session.scalar(select(ScanRun.detector_version).where(ScanRun.id == row.scan_run_id)) == '2'
    current = findings['version']
    labels = set()
    for item in findings['findings']:
        response = owner.post(base+'/findings/'+item['finding_id']+'/decision', json={'expected':current,'action':'label','affected_finding_ids':[item['finding_id']]}, headers=headers)
        assert response.status_code == 200
        current = response.json()['version']
        labels.update(x['label'] for x in response.json()['findings'] if x['label'])
    assert labels == {'DATE_001','URL_001','SECRET_001','ID_001'}
    completed = owner.post(base+'/complete', json={'expected':current,'confirmed_preview':True}, headers=headers)
    assert completed.status_code == 200
    assert owner.post(base+'/scan', json={'expected':current}, headers=headers).json() == {**scan,'version':current}
    assert owner.get(old_base+'/source').json()['categories'] == ['email','phone']
    changed = owner.put(base+'/scan-settings', json={'expected':current,'categories':categories,'phone_region':'US','language':'en'}, headers=headers)
    assert changed.status_code == 200
    saved = owner.get(base+'/source').json()
    assert saved['language'] == 'en' and saved['status'] == 'draft'
    assert saved['version']['settings_version'] == current['settings_version'] + 1
    assert owner.get(base+'/scan').json()['status'] == 'not_started'
    assert owner.get(base+'/preview').json()['version'] == saved['version']
    assert owner.post(base+'/complete', json={'expected':saved['version'],'confirmed_preview':True}, headers=headers).status_code == 422


def test_manual_date_parser_correction_and_durable_undo(intake_site):
    owner, _, engine, workspace, _ = intake_site
    headers = _login(owner, 'intake-owner@example.invalid')
    source = 'DOB 3/4/2026 then impossible 31/2/2026'
    created = owner.post('/api/v1/documents', json=_draft_body(workspace,source=source,categories=[]), headers=headers).json()
    version = created['version']; base = '/api/v1/documents/'+version['document_id']
    span = {'start':4,'end':12}
    marked = owner.post(base+'/findings', json={'expected':version,'span':span,'category':'date'}, headers=headers).json()
    item = marked['findings'][0]; fid = item['finding_id']
    with Session(engine) as session:
        assert session.get(Finding, UUID(fid)).date_format == 'n:dmy:/:114:0:0:1'
    revised = owner.put(base+'/findings/'+fid, json={'expected':marked['version'],'span':span,'category':'custom'}, headers=headers).json()
    with Session(engine) as session:
        assert session.get(Finding, UUID(fid)).date_format is None
    undone = owner.post(base+'/review/undo', json={'expected':revised['version']}, headers=headers)
    assert undone.status_code == 200
    with Session(engine) as session:
        assert session.get(Finding, UUID(fid)).date_format == 'n:dmy:/:114:0:0:1'
    start = source.index('31/2/2026')
    invalid = owner.post(base+'/findings', json={'expected':undone.json()['version'],'span':{'start':start,'end':start+9},'category':'date'}, headers=headers)
    assert invalid.status_code == 200
    with Session(engine) as session:
        assert session.scalar(select(Finding).where(Finding.document_id == UUID(version['document_id']), Finding.start_offset == start)).date_format is None


def test_language_gate_rejects_unadopted_languages(intake_site):
    owner, _, _, workspace, _ = intake_site
    headers = _login(owner, 'intake-owner@example.invalid')
    for language in ('de','es','fr','it','nl','pt'):
        bad = owner.post('/api/v1/documents', json=_draft_body(workspace,language=language), headers=headers)
        assert bad.status_code == 422
    created = owner.post('/api/v1/documents', json=_draft_body(workspace,source='Nora Caldwell works at Microsoft in London.',categories=['person','organization','location'],language='en'), headers=headers).json()
    version = created['version']; base = '/api/v1/documents/'+version['document_id']
    scanned = owner.post(base+'/scan',json={'expected':version},headers=headers)
    assert scanned.status_code == 200
    assert any(x['category'] == 'person' for x in scanned.json()['suggestions'])
    assert all(x['rule_id'].startswith('local.en_core_web_sm.') for x in scanned.json()['suggestions'])
    assert all(x['reason'].startswith('English') for x in scanned.json()['suggestions'])
    assert owner.put(base+'/scan-settings',json={'expected':version,'categories':[],'phone_region':'PH','language':'de'},headers=headers).status_code == 422


def test_workspace_rules_survive_exact_builtin_overlap_and_parse_dates(intake_site):
    from tests.test_custom_rules_pg import RULE, admin_headers

    owner, _, engine, workspace, _ = intake_site
    headers=admin_headers(intake_site)
    rule_path=f'/api/v1/workspaces/{workspace}/rules'
    for name,expression,category in [('ID mirror','123-45-6789','national_id'),('Birth date','3 October 2026','date')]:
        response=owner.post(rule_path,json={**RULE,'name':name,'kind':'phrase','expression':expression,'category':category},headers=headers)
        assert response.status_code==201
    created=owner.post('/api/v1/documents',json=_draft_body(workspace,source='DOB 3 October 2026. ID 123-45-6789',categories=['national_id']),headers=headers).json()
    version=created['version']; base='/api/v1/documents/'+version['document_id']
    scanned=owner.post(base+'/scan',json={'expected':version},headers=headers)
    assert scanned.status_code==200
    assert len(scanned.json()['suggestions'])==3
    findings=owner.get(base+'/findings').json()
    assert len(findings['overlaps'])==1
    assert owner.get(base+'/preview').json()['status']=='conflict'
    with Session(engine) as session:
        date_row=session.scalar(select(Finding).where(Finding.document_id==UUID(version['document_id']),Finding.category=='date'))
        assert date_row.date_format=='m:dmy:long-title:1:0:0:1'
