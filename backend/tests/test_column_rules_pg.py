from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.column_rules import DocumentColumnRules
from app.db.crypto import KeyRing, ProtectedValue
from app.db.models import Membership
from tests.csv_support import set_rules, upload_csv
from tests.intake_support import _login


def test_column_modes_fresh_scan_human_decisions_and_snapshot_copy(intake_site):
    owner, other, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    other_headers = _login(other, "intake-other@example.invalid")
    source = "Name,Email,Date\r\n Ada ,ada@example.test,2024-02-29\r\nAda,nora@example.test,2024-03-01\r\n"
    base, state, _ = upload_csv(owner, headers, workspace, source, "email,date")
    rules = [
        {
            "column": 0,
            "mode": "category",
            "category": "person",
            "default_action": "label",
            "style": "stand_in",
        },
        {"column": 1, "mode": "keep", "keep_reason": "intended_disclosure"},
    ]
    saved = set_rules(owner, headers, base, rules)
    assert saved.status_code == 200, saved.text
    version = saved.json()["version"]
    assert (
        version["settings_version"] == 2
        and version["decision_version"] > state["version"]["decision_version"]
    )
    assert owner.get(base + "/findings").json()["findings"] == []
    assert owner.get(base + "/scan").json()["status"] == "not_started"
    assert (
        other.put(
            base + "/column-rules",
            json={"expected_settings_version": 2, "rules": []},
            headers=other_headers,
        ).status_code
        == 404
    )
    response = owner.post(base + "/scan", json={"expected": version}, headers=headers)
    assert response.status_code == 200, response.text
    state = owner.get(base + "/findings").json()
    assert len(state["findings"]) == 4 and all(
        finding["action"] is None for finding in state["findings"]
    )
    people = [finding for finding in state["findings"] if finding["rule_id"] == "csv.column"]
    assert len(people) == 2 and all(
        source[finding["span"]["start"] : finding["span"]["end"]] == "Ada" for finding in people
    )
    assert not any(finding["category"] == "email" for finding in state["findings"])
    changed = owner.put(
        base + "/scan-settings",
        json={"expected": state["version"], "categories": ["date"], "phone_region": "US"},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    assert owner.get(base + "/column-rules").json()["rules"] == saved.json()["rules"]
    keys = KeyRing.from_settings(owner.app.state.settings)
    with Session(engine) as session:
        snapshots = session.scalars(
            select(DocumentColumnRules)
            .where(DocumentColumnRules.document_id == UUID(version["document_id"]))
            .order_by(DocumentColumnRules.settings_version)
        ).all()
        assert len(snapshots) == 3
        assert b"Email" not in snapshots[-1].rules_ciphertext
        assert "Email" in keys.decrypt_text(
            ProtectedValue(snapshots[-1].rules_ciphertext, snapshots[-1].key_id)
        )


@pytest.mark.parametrize("same_entity", [False, True])
def test_column_decision_exact_ids_independent_or_opt_in_labels_and_durable_undo(
    intake_site, same_entity
):
    owner, _, _, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    base, state, _ = upload_csv(
        owner,
        headers,
        workspace,
        "Name,Other\nAda,ada@example.test\nAda,ada@example.test\n",
        "email",
    )
    saved = set_rules(
        owner, headers, base, [{"column": 0, "mode": "category", "category": "person"}]
    )
    assert saved.status_code == 200
    scanned = owner.post(
        base + "/scan", json={"expected": saved.json()["version"]}, headers=headers
    )
    assert scanned.status_code == 200
    state = owner.get(base + "/findings").json()
    people = [row for row in state["findings"] if row["category"] == "person"]
    body = {
        "expected": state["version"],
        "action": "label",
        "affected_finding_ids": [row["finding_id"] for row in people],
        "same_text_same_entity": same_entity,
    }
    bad = owner.post(
        base + "/columns/0/decision",
        json={**body, "affected_finding_ids": [people[0]["finding_id"], str(uuid4())]},
        headers=headers,
    )
    assert bad.status_code == 422 and owner.get(base + "/findings").json() == state
    result = owner.post(base + "/columns/0/decision", json=body, headers=headers)
    assert result.status_code == 200, result.text
    saved = result.json()
    people = [row for row in saved["findings"] if row["category"] == "person"]
    assert len({row["label"] for row in people}) == (1 if same_entity else 2)
    assert all(row["action"] is None for row in saved["findings"] if row["category"] == "email")
    assert saved["undo_available"] == 1
    assert owner.post(base + "/columns/0/decision", json=body, headers=headers).status_code == 409
    undone = owner.post(base + "/review/undo", json={"expected": saved["version"]}, headers=headers)
    assert undone.status_code == 200, undone.text
    assert all(
        row["action"] is None and row["group_id"] is None for row in undone.json()["findings"]
    )


def test_preset_column_headers_encrypted_matched_normalized_and_versioned(intake_site):
    owner, _, engine, workspace, owner_id = intake_site
    with Session(engine) as session, session.begin():
        session.get(Membership, (workspace, owner_id)).role = "administrator"
    headers = _login(owner, "intake-owner@example.invalid")
    body = {
        "name": "CSV rules",
        "categories": ["email"],
        "phone_region": "GB",
        "column_rules": [
            {"column": 0, "header": " École ", "mode": "category", "category": "organization"},
            {"column": 1, "header": "Email", "mode": "keep", "keep_reason": "intended_disclosure"},
        ],
    }
    preset = owner.post(f"/api/v1/workspaces/{workspace}/presets", json=body, headers=headers)
    assert preset.status_code == 201, preset.text
    base, _, saved = upload_csv(
        owner,
        headers,
        workspace,
        "Email,Autre,ÉCOLE\nada@example.test,value,Aurora\n",
        preset=preset.json()["id"],
    )
    rules = saved["csv"]["rules"]
    assert [(rule["column"], rule["mode"]) for rule in rules] == [(0, "keep"), (2, "category")]
    assert owner.get(base + "/scan").json()["match_count"] == 1
    updated = owner.put(
        f"/api/v1/workspaces/{workspace}/presets/{preset.json()['id']}",
        json={**body, "column_rules": [], "expected_version": 1},
        headers=headers,
    )
    assert updated.status_code == 200 and updated.json()["version"] == 2
    assert owner.get(base + "/source").json()["csv"]["rules"] == rules
