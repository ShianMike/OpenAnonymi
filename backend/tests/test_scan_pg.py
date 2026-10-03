"""Paste, file, and revision workflow on an explicit local PostgreSQL database."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts import VersionRef
from app.db.crypto import KeyRing
from app.db.models import (
    Decision,
    Document,
    Finding,
    Membership,
    ScanRun,
)
from app.db.repository import append_source_revision
from app.detection.rules import detect_suggestions as real_detect_suggestions
from tests.intake_support import _draft_body, _login


def test_scan_suggestions_are_unresolved_idempotent_and_settings_bound(intake_site):
    owner, other, engine, workspace_id, _owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    _login(other, "intake-other@example.invalid")
    source = "😀 Email alice@example.com, phone 650-253-2222; ref 12345678901234567890."
    created = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, source=source, phone_region="US"),
        headers=headers,
    )
    assert created.status_code == 201, created.text
    version = created.json()["version"]
    path = f"/api/v1/documents/{version['document_id']}/scan"
    assert owner.get(path).json()["status"] == "not_started"
    assert other.get(path).status_code == 404

    scanned = owner.post(path, json={"expected": version}, headers=headers)
    assert scanned.status_code == 200, scanned.text
    body = scanned.json()
    assert body["status"] == "completed"
    assert body["match_count"] == 2
    findings_path = f"/api/v1/documents/{version['document_id']}/findings"
    assert len(owner.get(findings_path).json()["findings"]) == 2
    assert body["version"]["decision_version"] == version["decision_version"] + 1
    assert [
        (item["category"], source[item["span"]["start"] : item["span"]["end"]])
        for item in body["suggestions"]
    ] == [
        ("email", "alice@example.com"),
        ("phone", "650-253-2222"),
    ]
    assert all(
        item["rule_id"] and item["rule_version"] and item["reason"] for item in body["suggestions"]
    )
    assert "alice@example.com" not in scanned.text
    with Session(engine) as session:
        assert (
            len(
                session.scalars(
                    select(Finding).where(Finding.document_id == version["document_id"])
                ).all()
            )
            == 2
        )
        assert (
            session.scalars(
                select(Decision).join(Finding).where(Finding.document_id == version["document_id"])
            ).all()
            == []
        )
    retried = owner.post(path, json={"expected": version}, headers=headers)
    assert retried.status_code == 200
    assert [item["finding_id"] for item in retried.json()["suggestions"]] == [
        item["finding_id"] for item in body["suggestions"]
    ]
    activity = owner.get(f"/api/v1/workspaces/{workspace_id}/activity")
    assert [entry["event_code"] for entry in activity.json()["own_events"]].count(
        "scan_completed"
    ) == 1
    assert "alice@example.com" not in activity.text

    changed = owner.put(
        f"/api/v1/documents/{version['document_id']}/scan-settings",
        json={"expected": body["version"], "categories": ["email"], "phone_region": "US"},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    new_version = changed.json()["version"]
    assert new_version["settings_version"] == version["settings_version"] + 1
    assert (
        owner.get(f"/api/v1/documents/{version['document_id']}/source").json()["status"] == "draft"
    )
    assert owner.get(path).json()["status"] == "not_started"
    assert owner.get(findings_path).json()["findings"] == []
    assert owner.post(path, json={"expected": version}, headers=headers).status_code == 409
    rescanned = owner.post(path, json={"expected": new_version}, headers=headers)
    assert rescanned.status_code == 200, rescanned.text
    assert [item["category"] for item in rescanned.json()["suggestions"]] == ["email"]
    assert [item["category"] for item in owner.get(findings_path).json()["findings"]] == ["email"]
    codes = [
        entry["event_code"]
        for entry in owner.get(f"/api/v1/workspaces/{workspace_id}/activity").json()["own_events"]
    ]
    assert codes.count("scan_completed") == 2
    assert codes.count("scan_settings_changed") == 1


def test_scan_failure_is_distinct_from_zero_matches_and_can_retry(intake_site, monkeypatch):
    owner, _other, _engine, workspace_id, _owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    created = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, source="No contact details here."),
        headers=headers,
    )
    version = created.json()["version"]
    path = f"/api/v1/documents/{version['document_id']}/scan"

    def fail_once(_source, _categories, _region):
        raise RuntimeError("synthetic detector failure")

    monkeypatch.setattr("app.detection.service.detect_suggestions", fail_once)
    failed = owner.post(path, json={"expected": version}, headers=headers)
    assert failed.status_code == 503
    assert "synthetic detector failure" not in failed.text
    state = owner.get(path).json()
    assert state["status"] == "failed"
    assert state["match_count"] is None
    assert state["failure_code"] == "detector_error"
    failure_events = owner.get(f"/api/v1/workspaces/{workspace_id}/activity").json()["own_events"]
    assert any(
        event["event_code"] == "scan_failed" and event["outcome"] == "failed"
        for event in failure_events
    )
    monkeypatch.setattr("app.detection.service.detect_suggestions", real_detect_suggestions)
    succeeded = owner.post(path, json={"expected": version}, headers=headers)
    assert succeeded.status_code == 200, succeeded.text
    assert succeeded.json()["status"] == "completed"
    assert succeeded.json()["match_count"] == 0
    assert succeeded.json()["suggestions"] == []
    assert succeeded.json()["attempt_count"] == 2
    assert (
        owner.get(f"/api/v1/documents/{version['document_id']}/source").json()["status"]
        == "needs_review"
    )


def test_late_scan_never_attaches_findings_to_new_source(intake_site, monkeypatch):
    owner, _other, engine, workspace_id, owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    created = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, source="Email alice@example.com"),
        headers=headers,
    )
    version = created.json()["version"]
    path = f"/api/v1/documents/{version['document_id']}/scan"

    def edit_during_scan(source, categories, region, language="en"):
        with Session(engine) as session:
            append_source_revision(
                session,
                document_id=UUID(version["document_id"]),
                actor_id=owner_id,
                expected=VersionRef.model_validate(version),
                source="Email bob@example.com",
                keys=KeyRing.from_settings(owner.app.state.settings),
                now=datetime.now(UTC),
            )
        return real_detect_suggestions(source, categories, region, language)

    monkeypatch.setattr("app.detection.service.detect_suggestions", edit_during_scan)
    late = owner.post(path, json={"expected": version}, headers=headers)
    assert late.status_code == 409, late.text
    assert owner.get(path).json()["status"] == "not_started"
    with Session(engine) as session:
        old_run = session.scalar(
            select(ScanRun).where(ScanRun.source_revision_id == version["source_revision_id"])
        )
        assert old_run.status == "superseded"
        assert session.scalars(select(Finding).where(Finding.scan_run_id == old_run.id)).all() == []


def test_abandoned_scan_lease_can_be_retried_without_duplicates(intake_site):
    owner, _other, engine, workspace_id, _owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    created = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, source="Email alice@example.com"),
        headers=headers,
    )
    version = created.json()["version"]
    with Session(engine) as session, session.begin():
        document = session.get(Document, UUID(version["document_id"]))
        document.status = "scanning"
        session.add(
            ScanRun(
                id=uuid4(),
                document_id=document.id,
                source_revision_id=UUID(version["source_revision_id"]),
                settings_version=version["settings_version"],
                detector_version="1",
                status="scanning",
                attempt_count=1,
                started_at=datetime.now(UTC) - timedelta(minutes=3),
            )
        )
    path = f"/api/v1/documents/{version['document_id']}/scan"
    interrupted = owner.get(path)
    assert interrupted.status_code == 200, interrupted.text
    assert interrupted.json()["status"] == "failed"
    assert interrupted.json()["failure_code"] == "scan_interrupted"
    assert (
        owner.get(f"/api/v1/documents/{version['document_id']}/source").json()["status"] == "failed"
    )
    completed = owner.post(path, json={"expected": version}, headers=headers)
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
    assert completed.json()["attempt_count"] == 2
    assert completed.json()["match_count"] == 1
    with Session(engine) as session:
        assert (
            len(
                session.scalars(
                    select(Finding).where(Finding.document_id == version["document_id"])
                ).all()
            )
            == 1
        )


def test_membership_revocation_during_scan_discards_result(intake_site, monkeypatch):
    owner, _other, engine, workspace_id, owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    created = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, source="Email alice@example.com"),
        headers=headers,
    )
    version = created.json()["version"]

    def revoke_during_scan(source, categories, region, language="en"):
        with Session(engine) as session, session.begin():
            membership = session.get(Membership, (workspace_id, owner_id))
            membership.revoked_at = datetime.now(UTC)
        return real_detect_suggestions(source, categories, region, language)

    monkeypatch.setattr("app.detection.service.detect_suggestions", revoke_during_scan)
    response = owner.post(
        f"/api/v1/documents/{version['document_id']}/scan",
        json={"expected": version},
        headers=headers,
    )
    assert response.status_code == 404
    with Session(engine) as session:
        run = session.scalar(
            select(ScanRun).where(ScanRun.source_revision_id == version["source_revision_id"])
        )
        assert run.status == "superseded"
        assert session.scalars(select(Finding).where(Finding.scan_run_id == run.id)).all() == []


def test_scan_overlap_requires_explicit_resolution_before_decision(intake_site):
    owner, _other, _engine, workspace_id, _owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    created = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, source="alice@example.com", categories=["email"]),
        headers=headers,
    )
    version = created.json()["version"]
    path = f"/api/v1/documents/{version['document_id']}/findings"
    manual = owner.post(
        path,
        json={"expected": version, "span": {"start": 0, "end": 5}, "category": "person"},
        headers=headers,
    ).json()
    version = manual["version"]
    manual_id = manual["findings"][0]["finding_id"]
    scanned = owner.post(
        f"/api/v1/documents/{version['document_id']}/scan",
        json={"expected": version},
        headers=headers,
    )
    assert scanned.status_code == 200, scanned.text
    current = owner.get(path).json()
    assert len(current["findings"]) == 2
    assert len(current["overlaps"]) == 1
    blocked_preview = owner.get(f"/api/v1/documents/{version['document_id']}/preview").json()
    assert blocked_preview["status"] == "conflict"
    assert blocked_preview["text"] is None
    assert (
        owner.post(
            f"/api/v1/documents/{version['document_id']}/complete",
            json={"expected": current["version"], "confirmed_preview": True},
            headers=headers,
        ).json()["code"]
        == "overlapping_findings"
    )
    blocked = owner.post(
        f"{path}/{manual_id}/decision",
        json={
            "expected": current["version"],
            "action": "label",
            "affected_finding_ids": [manual_id],
        },
        headers=headers,
    )
    assert blocked.status_code == 422
    assert blocked.json()["code"] == "overlapping_finding"
    automatic_id = next(
        row["finding_id"] for row in current["findings"] if row["origin"] == "automatic"
    )
    resolved = owner.post(
        f"{path}/{automatic_id}/remove",
        json={"expected": current["version"]},
        headers=headers,
    )
    assert resolved.status_code == 200
    assert resolved.json()["overlaps"] == []
    decided = owner.post(
        f"{path}/{manual_id}/decision",
        json={
            "expected": resolved.json()["version"],
            "action": "label",
            "affected_finding_ids": [manual_id],
        },
        headers=headers,
    )
    assert decided.status_code == 200, decided.text
