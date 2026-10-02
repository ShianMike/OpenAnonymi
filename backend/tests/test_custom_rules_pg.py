"""Rule authorization, encrypted versions, bounded matching and snapshot isolation."""

from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.custom_rules.contracts import RuleInput
from app.custom_rules.matching import matches
from app.db.crypto import KeyRing, ProtectedValue
from app.db.custom_rules import DocumentRuleSnapshot, RuleVersion
from app.db.models import Membership
from app.db.rotate_keys import rotate_rules
from tests.intake_support import _draft_body, _login


def admin_headers(intake_site):
    owner, _other, engine, workspace, user = intake_site
    with Session(engine) as session, session.begin():
        session.get(Membership, (workspace, user)).role = "administrator"
    return _login(owner, "intake-owner@example.invalid")


RULE = {
    "name": "Case references",
    "kind": "identifier",
    "expression": "CASE-######",
    "category": "identifier",
    "enabled": True,
    "case_sensitive": False,
    "whole_word": True,
}


def test_rules_protected_authorized_versioned_and_snapshot_bound(intake_site):
    owner, other, engine, workspace, _user = intake_site
    headers = admin_headers(intake_site)
    member = _login(other, "intake-other@example.invalid")
    path = f"/api/v1/workspaces/{workspace}/rules"
    assert other.post(path, json=RULE, headers=member).status_code == 404
    assert (
        owner.post(path, json=RULE, headers={"Origin": "http://localhost:5173"}).status_code == 403
    )
    created = owner.post(path, json=RULE, headers=headers)
    assert created.status_code == 201, created.text
    rule = created.json()
    assert other.get(path).json()[0]["expression"] == RULE["expression"]
    source = "😀 CASE-123456, case-555555, XCASE-234567 and TICKET-654321."
    test = other.post(path + "/test", json={"rule": RULE, "text": source}, headers=member)
    assert test.status_code == 200, test.text
    assert [item["text"] for item in test.json()["matches"]] == ["CASE-123456", "case-555555"]
    saved = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace, source=source, categories=[]),
        headers=headers,
    ).json()
    base = f"/api/v1/documents/{saved['version']['document_id']}"
    assert other.get(base + "/rules").status_code == 404
    assert owner.get(base + "/rules").json()["rules"][0]["version"] == 1
    updated_body = {**RULE, "expression": "TICKET-######", "expected_version": 1}
    updated = owner.put(path + "/" + rule["id"], json=updated_body, headers=headers)
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2
    assert owner.put(path + "/" + rule["id"], json=updated_body, headers=headers).status_code == 409
    state = owner.get(base + "/rules").json()
    assert state["update_available"] and state["rules"][0]["expression"] == "CASE-######"
    scanned = owner.post(
        base + "/scan", json={"expected": saved["version"]}, headers=headers
    ).json()
    assert len(scanned["suggestions"]) == 2
    assert all(item["rule_version"] == "1" for item in scanned["suggestions"])
    assert "CASE-123456" not in str(scanned)
    settings = owner.put(
        base + "/scan-settings",
        json={"expected": scanned["version"], "categories": [], "phone_region": "US"},
        headers=headers,
    ).json()
    assert owner.get(base + "/rules").json()["rules"][0]["version"] == 1
    assert (
        owner.put(base + "/rules", json={"expected": saved["version"]}, headers=headers).status_code
        == 409
    )
    refreshed = owner.put(base + "/rules", json={"expected": settings["version"]}, headers=headers)
    assert refreshed.status_code == 200, refreshed.text
    assert not refreshed.json()["update_available"]
    new_version = refreshed.json()["version"]
    assert owner.get(base + "/source").json()["status"] == "draft"
    assert owner.get(base + "/findings").json()["findings"] == []
    assert (
        owner.post(
            base + "/complete",
            json={"expected": new_version, "confirmed_preview": True},
            headers=headers,
        ).status_code
        == 422
    )
    rescanned = owner.post(base + "/scan", json={"expected": new_version}, headers=headers).json()
    assert len(rescanned["suggestions"]) == 1 and rescanned["suggestions"][0]["rule_version"] == "2"
    assert owner.get(base + "/source").json()["text"] == source
    activity = owner.get(f"/api/v1/workspaces/{workspace}/activity").text
    assert RULE["name"] not in activity and "CASE-######" not in activity
    with Session(engine) as session:
        rows = session.scalars(
            select(RuleVersion).where(RuleVersion.rule_id == UUID(rule["id"]))
        ).all()
        assert len(rows) == 2 and all(b"CASE" not in row.payload_ciphertext for row in rows)
        old = owner.app.state.settings.content_keys["test"].get_secret_value().encode()
        from cryptography.fernet import Fernet

        keys = KeyRing("new", {"test": old, "new": Fernet.generate_key()})
        assert rotate_rules(session, keys) == 2
        session.commit()
        assert all(
            keys.decrypt_text(ProtectedValue(row.payload_ciphertext, row.payload_key_id))
            for row in rows
        )
        assert session.scalars(
            select(DocumentRuleSnapshot).where(
                DocumentRuleSnapshot.document_id == UUID(saved["version"]["document_id"])
            )
        ).all()


def test_literal_templates_and_test_limits(intake_site):
    owner, _other, _engine, workspace, _user = intake_site
    headers = admin_headers(intake_site)
    path = f"/api/v1/workspaces/{workspace}/rules/test"
    phrase = {**RULE, "kind": "phrase", "expression": "東京.café (a+)+", "category": "address"}
    text = "😀 東京.café (a+)+; 東京.café (a+)+!"
    body = owner.post(path, json={"rule": phrase, "text": text}, headers=headers)
    assert body.status_code == 200 and body.json()["match_count"] == 2
    assert body.json()["matches"][0]["span"] == {"start": 2, "end": 2 + len(phrase["expression"])}
    assert (
        owner.post(
            path, json={"rule": RULE, "text": "CASE-123456 " * 101}, headers=headers
        ).status_code
        == 422
    )
    assert (
        owner.post(path, json={"rule": RULE, "text": "x" * 10001}, headers=headers).status_code
        == 422
    )
    with pytest.raises(ValueError):
        RuleInput(**{**RULE, "expression": "a+"})
    assert matches("AB-12 and xx-34", RuleInput(**{**RULE, "expression": "@@-##"}))
