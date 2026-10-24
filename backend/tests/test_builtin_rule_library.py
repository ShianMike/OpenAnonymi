"""The shipped library examples must work in the actual bounded rule matcher."""

import json
from pathlib import Path
from uuid import UUID

import pytest

from app.custom_rules.contracts import RuleInput
from app.custom_rules.matching import detect_custom, matches
from tests.intake_support import _draft_body
from tests.test_custom_rules_pg import admin_headers

LIBRARY = json.loads(
    (Path(__file__).resolve().parents[2] / "frontend/src/rules/builtInRules.json").read_text(
        encoding="utf-8"
    )
)


@pytest.mark.parametrize("template", LIBRARY, ids=lambda item: item["id"])
def test_library_formats_match_examples_but_not_near_misses_or_longer_ids(template):
    rule = RuleInput(
        name=template["name"], kind="identifier", expression=template["pattern"],
        category="identifier", whole_word=True, case_sensitive=False,
    )
    value = template["example"]
    source = f"🙂 {value}; {value.lower()}; {template['nearMiss']}; X{value}; {value}X."
    spans = matches(source, rule)
    assert [source[span.start:span.end] for span in spans] == [value, value.lower()]
    assert spans[0].start == 2
    suggestions = detect_custom(source, [(UUID(int=1), 1, rule)])
    assert [suggestion.span for suggestion in suggestions] == spans
    assert all(suggestion.category == "identifier" for suggestion in suggestions)


def test_every_library_template_can_be_tested_installed_and_scanned_as_a_saved_rule(intake_site):
    owner, _other, _engine, workspace, _user = intake_site
    headers = admin_headers(intake_site)
    path = f"/api/v1/workspaces/{workspace}/rules"
    for template in LIBRARY:
        definition = RuleInput(
            name=template["name"], kind="identifier", expression=template["pattern"],
            category="identifier", whole_word=True, case_sensitive=False, enabled=True,
        ).model_dump(mode="json")
        source = f"Fictional record: {template['example']}. Near match: {template['nearMiss']}."
        tested = owner.post(path + "/test", json={"rule": definition, "text": source}, headers=headers)
        assert tested.status_code == 200
        assert tested.json()["match_count"] == 1
        assert tested.json()["matches"][0]["text"] == template["example"]
        created = owner.post(path, json=definition, headers=headers)
        assert created.status_code == 201
        rule = created.json()
        draft = owner.post(
            "/api/v1/documents", headers=headers,
            json=_draft_body(workspace, source=source, categories=[]),
        )
        assert draft.status_code == 201
        version = draft.json()["version"]
        base = f"/api/v1/documents/{version['document_id']}"
        snapshot = owner.get(base + "/rules").json()
        assert any(item["id"] == rule["id"] and item["version"] == 1 for item in snapshot["rules"])
        scanned = owner.post(base + "/scan", json={"expected": version}, headers=headers)
        assert scanned.status_code == 200
        suggestions = scanned.json()["suggestions"]
        assert len(suggestions) == 1
        assert suggestions[0]["rule_id"] == f"workspace.{rule['id']}"
        assert suggestions[0]["rule_version"] == "1"
