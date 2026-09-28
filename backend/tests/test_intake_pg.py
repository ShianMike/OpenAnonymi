"""Paste, file, and revision workflow on an explicit local PostgreSQL database."""

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.accounts.security import hash_password
from app.cleanup.service import purge_unavailable_content
from app.config import Settings
from app.contracts import VersionRef
from app.db.crypto import KeyRing
from app.db.models import (
    AuditEvent,
    Decision,
    Document,
    ExportEvent,
    Finding,
    Membership,
    ScanRun,
    SourceRevision,
    User,
    Workspace,
)
from app.db.repository import append_source_revision
from app.detection.rules import detect_suggestions as real_detect_suggestions
from app.factory import create_app

ORIGIN = "http://localhost:5173"
PASSWORD = "synthetic-intake-password"


@pytest.fixture
def intake_site():
    raw_url = os.getenv("PRIVACY_REVIEW_TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("set PRIVACY_REVIEW_TEST_DATABASE_URL for the local database gate")
    url = make_url(raw_url)
    if url.host not in ("127.0.0.1", "localhost") or url.port not in (5433, 5434):
        pytest.fail("intake test requires a local database on port 5433 or 5434")
    engine = create_engine(raw_url, pool_pre_ping=True, hide_parameters=True)
    workspace_id, owner_id, other_id = uuid4(), uuid4(), uuid4()
    with Session(engine) as session, session.begin():
        session.add(
            Workspace(id=workspace_id, name="Intake test workspace", content_retention_days=7)
        )
        session.add_all(
            [
                User(
                    id=owner_id,
                    email="intake-owner@example.invalid",
                    password_hash=hash_password(PASSWORD),
                ),
                User(
                    id=other_id,
                    email="intake-other@example.invalid",
                    password_hash=hash_password(PASSWORD),
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                Membership(workspace_id=workspace_id, user_id=owner_id, role="member"),
                Membership(workspace_id=workspace_id, user_id=other_id, role="member"),
            ]
        )
    settings = Settings(
        database_url=raw_url,
        allowed_origins=[ORIGIN],
        environment="test",
        active_key_id="test",
        content_keys={"test": Fernet.generate_key().decode()},
        _env_file=None,
    )
    try:
        with (
            TestClient(create_app(settings, engine=engine)) as owner,
            TestClient(create_app(settings, engine=engine)) as other,
        ):
            yield owner, other, engine, workspace_id, owner_id
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(Document).where(Document.workspace_id == workspace_id))
            session.execute(delete(Membership).where(Membership.workspace_id == workspace_id))
            session.execute(delete(Workspace).where(Workspace.id == workspace_id))
            session.execute(delete(User).where(User.id.in_([owner_id, other_id])))
        engine.dispose()


def _login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/sign-in",
        json={"email": email, "password": PASSWORD},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 200
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def _draft_body(workspace_id, **overrides):
    return {
        "workspace_id": str(workspace_id),
        "source": "Synthetic owner 😀\r\nsecond line",
        "title": "Synthetic optional title",
        "categories": ["email", "phone"],
        "phone_region": "PH",
        "retention_days": 3,
        **overrides,
    }


def test_paste_save_reopen_revision_and_stale_conflict(intake_site):
    owner, other, engine, workspace_id, _owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    _login(other, "intake-other@example.invalid")
    defaults = owner.get(f"/api/v1/documents/intake-defaults/{workspace_id}")
    assert defaults.status_code == 200
    assert defaults.json()["content_retention_days"] == 7

    created = owner.post("/api/v1/documents", json=_draft_body(workspace_id), headers=headers)
    assert created.status_code == 201, created.text
    version = created.json()["version"]
    assert created.json()["status"] == "draft"
    assert "Synthetic owner" not in created.text
    document_id = version["document_id"]
    path = f"/api/v1/documents/{document_id}/source"
    reopened = owner.get(path)
    assert reopened.status_code == 200
    assert reopened.json()["text"] == "Synthetic owner 😀\r\nsecond line"
    assert reopened.json()["title"] == "Synthetic optional title"
    assert reopened.json()["categories"] == ["email", "phone"]
    assert reopened.json()["phone_region"] == "PH"
    assert reopened.headers["Cache-Control"] == "no-store"
    assert other.get(path).status_code == 404
    with Session(engine) as session:
        revision = session.get(SourceRevision, version["source_revision_id"])
        assert revision is not None
        assert b"Synthetic owner" not in revision.source_ciphertext
        assert (
            session.get(Document, version["document_id"]).title_ciphertext
            != b"Synthetic optional title"
        )

    changed_text = "Synthetic owner 😀\r\nchanged line"
    edited = owner.put(
        path,
        json={"expected": version, "source": changed_text},
        headers=headers,
    )
    assert edited.status_code == 200
    next_version = edited.json()["version"]
    assert next_version["source_revision_id"] != version["source_revision_id"]
    assert next_version["decision_version"] == version["decision_version"] + 1
    assert owner.get(path).json()["text"] == changed_text
    with Session(engine) as session:
        revisions = session.scalars(
            select(SourceRevision).where(SourceRevision.document_id == document_id)
        ).all()
        assert {row.revision_number for row in revisions} == {1, 2}
    stale = owner.put(
        path,
        json={"expected": version, "source": "Stale data"},
        headers=headers,
    )
    assert stale.status_code == 409
    assert stale.json()["current_version"] == next_version
    assert owner.get(path).json()["text"] == changed_text
    assert (
        other.put(
            path,
            json={"expected": next_version, "source": "Intrusion"},
            headers={
                "Origin": ORIGIN,
                "X-CSRF-Token": other.get("/api/v1/auth/session").json()["csrf_token"],
            },
        ).status_code
        == 404
    )


def test_file_intake_and_rejections(intake_site):
    owner, other, engine, workspace_id, _owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    _login(other, "intake-other@example.invalid")
    path = "/api/v1/documents/from-file"
    data = {
        "workspace_id": str(workspace_id),
        "title": "",
        "categories": "email,phone",
        "phone_region": "PH",
        "retention_days": "2",
    }
    valid = owner.post(
        path,
        data=data,
        files={"file": ("synthetic.txt", b"\xef\xbb\xbfHello\r\nworld", "text/plain")},
        headers=headers,
    )
    assert valid.status_code == 201, valid.text
    source = owner.get(f"/api/v1/documents/{valid.json()['version']['document_id']}/source")
    assert source.json()["text"] == "Hello\r\nworld"
    assert source.json()["title"] is None
    for filename, content in (
        ("synthetic.pdf", b"Hello"),
        ("synthetic.txt", b"\xff"),
        ("synthetic.txt", b" \r\n"),
        ("synthetic.txt", b"Hello\x00world"),
        ("synthetic.txt", b"x" * 1_048_577),
    ):
        rejected = owner.post(
            path,
            data=data,
            files={"file": (filename, content, "application/octet-stream")},
            headers=headers,
        )
        assert rejected.status_code == 422, rejected.text
        assert filename not in rejected.text
    multiple = owner.post(
        path,
        data=data,
        files=[
            ("file", ("one.txt", b"One", "text/plain")),
            ("file", ("two.txt", b"Two", "text/plain")),
        ],
        headers=headers,
    )
    assert multiple.status_code == 422
    assert other.get(f"/api/v1/documents/intake-defaults/{uuid4()}").status_code == 404
    with Session(engine) as session:
        assert (
            len(
                session.scalars(select(Document).where(Document.workspace_id == workspace_id)).all()
            )
            == 1
        )


def test_paste_validation_and_expiry_limit(intake_site):
    owner, _other, engine, workspace_id, _owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    for source in ("", " \r\n", "x" * 100_001, "Hello\x1bworld"):
        response = owner.post(
            "/api/v1/documents",
            json=_draft_body(workspace_id, source=source),
            headers=headers,
        )
        assert response.status_code in (422, 400)
        assert "Synthetic optional title" not in response.text
    too_long = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, retention_days=8),
        headers=headers,
    )
    assert too_long.status_code == 422
    unsupported_region = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, phone_region="ZZ"),
        headers=headers,
    )
    assert unsupported_region.status_code == 422
    with Session(engine) as session:
        assert (
            session.scalars(select(Document).where(Document.workspace_id == workspace_id)).all()
            == []
        )


def test_content_intake_refuses_to_save_without_encryption_key(intake_site):
    _owner, _other, engine, workspace_id, _owner_id = intake_site
    settings = Settings(
        database_url=os.environ["PRIVACY_REVIEW_TEST_DATABASE_URL"],
        allowed_origins=[ORIGIN],
        environment="test",
        _env_file=None,
    )
    with TestClient(create_app(settings, engine=engine)) as client:
        headers = _login(client, "intake-owner@example.invalid")
        response = client.post(
            "/api/v1/documents",
            json=_draft_body(workspace_id),
            headers=headers,
        )
        assert response.status_code == 503
        assert "Synthetic owner" not in response.text
    with Session(engine) as session:
        assert (
            session.scalars(select(Document).where(Document.workspace_id == workspace_id)).all()
            == []
        )


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

    def edit_during_scan(source, categories, region):
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
        return real_detect_suggestions(source, categories, region)

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

    def revoke_during_scan(source, categories, region):
        with Session(engine) as session, session.begin():
            membership = session.get(Membership, (workspace_id, owner_id))
            membership.revoked_at = datetime.now(UTC)
        return real_detect_suggestions(source, categories, region)

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


def test_manual_finding_boundary_correction_removal_and_overlap(intake_site):
    owner, other, engine, workspace_id, _owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    _login(other, "intake-other@example.invalid")
    source = "😀 Alice wrote alice@example.com. Alice called."
    created = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, source=source, categories=[]),
        headers=headers,
    )
    version = created.json()["version"]
    path = f"/api/v1/documents/{version['document_id']}/findings"
    assert owner.get(path).json()["findings"] == []
    assert other.get(path).status_code == 404
    first_start = source.index("Alice")
    added = owner.post(
        path,
        json={
            "expected": version,
            "span": {"start": first_start, "end": first_start + len("Alice")},
            "category": "person",
        },
        headers=headers,
    )
    assert added.status_code == 200, added.text
    first = added.json()["findings"][0]
    assert source[first["span"]["start"] : first["span"]["end"]] == "Alice"
    assert first["action"] is None
    assert first["origin"] == "manual"
    next_version = added.json()["version"]
    assert next_version["decision_version"] == version["decision_version"] + 1
    assert (
        owner.get(f"/api/v1/documents/{version['document_id']}/source").json()["status"]
        == "needs_review"
    )

    overlap = owner.post(
        path,
        json={
            "expected": next_version,
            "span": {"start": first_start + 1, "end": first_start + 4},
            "category": "custom",
        },
        headers=headers,
    )
    assert overlap.status_code == 422
    assert overlap.json()["code"] == "overlapping_finding"
    assert owner.get(path).json()["version"] == next_version
    whitespace = owner.post(
        path,
        json={
            "expected": next_version,
            "span": {"start": first_start - 1, "end": first_start},
            "category": "person",
        },
        headers=headers,
    )
    assert whitespace.status_code == 422

    correction = owner.put(
        f"{path}/{first['finding_id']}",
        json={
            "expected": next_version,
            "span": {"start": first_start, "end": first_start + 4},
            "category": "person",
        },
        headers=headers,
    )
    assert correction.status_code == 200, correction.text
    corrected_version = correction.json()["version"]
    assert correction.json()["findings"][0]["span"]["end"] == first_start + 4
    assert corrected_version["decision_version"] == next_version["decision_version"] + 1
    stale = owner.put(
        f"{path}/{first['finding_id']}",
        json={
            "expected": next_version,
            "span": {"start": first_start, "end": first_start + 5},
            "category": "person",
        },
        headers=headers,
    )
    assert stale.status_code == 409
    assert stale.json()["current_version"] == corrected_version
    denied = other.post(
        f"{path}/{first['finding_id']}/remove",
        json={"expected": corrected_version},
        headers={
            "Origin": ORIGIN,
            "X-CSRF-Token": other.get("/api/v1/auth/session").json()["csrf_token"],
        },
    )
    assert denied.status_code == 404
    removed = owner.post(
        f"{path}/{first['finding_id']}/remove",
        json={"expected": corrected_version},
        headers=headers,
    )
    assert removed.status_code == 200
    assert removed.json()["findings"] == []
    assert (
        removed.json()["version"]["decision_version"] == corrected_version["decision_version"] + 1
    )
    with Session(engine) as session:
        finding = session.get(Finding, UUID(first["finding_id"]))
        assert finding.removed_at is not None


def test_exact_matches_groups_and_decisions_are_versioned_and_owner_scoped(intake_site):
    owner, other, _engine, workspace_id, _owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    _login(other, "intake-other@example.invalid")
    source = "😀 Alice met Alice. Alicia met Alice."
    created = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, source=source, categories=[]),
        headers=headers,
    )
    version = created.json()["version"]
    path = f"/api/v1/documents/{version['document_id']}/findings"
    first = source.index("Alice")
    added = owner.post(
        path,
        json={
            "expected": version,
            "span": {"start": first, "end": first + 5},
            "category": "person",
        },
        headers=headers,
    ).json()
    version = added["version"]
    first_id = added["findings"][0]["finding_id"]
    matches_path = f"{path}/{first_id}/exact-matches"
    offered = owner.get(matches_path)
    assert offered.status_code == 200
    assert [source[span["start"] : span["end"]] for span in offered.json()["spans"]] == [
        "Alice",
        "Alice",
    ]
    assert other.get(matches_path).status_code == 404
    second_span = offered.json()["spans"][0]
    second = owner.post(
        matches_path, json={"expected": version, "span": second_span}, headers=headers
    )
    assert second.status_code == 200, second.text
    version = second.json()["version"]
    second_id = second.json()["findings"][1]["finding_id"]
    stale = owner.post(
        matches_path, json={"expected": added["version"], "span": second_span}, headers=headers
    )
    assert stale.status_code == 409
    assert (
        owner.post(
            matches_path,
            json={
                "expected": version,
                "span": {"start": source.index("Alicia"), "end": source.index("Alicia") + 6},
            },
            headers=headers,
        ).json()["code"]
        == "not_exact_match"
    )

    first_decision = owner.post(
        f"{path}/{first_id}/decision",
        json={
            "expected": version,
            "action": "label",
            "affected_finding_ids": [first_id],
        },
        headers=headers,
    )
    assert first_decision.status_code == 200, first_decision.text
    version = first_decision.json()["version"]
    label = first_decision.json()["findings"][0]["label"]
    assert label == "PERSON_001"
    assert first_decision.json()["findings"][1]["label"] is None
    assert (
        owner.post(
            f"{path}/{second_id}/decision",
            json={
                "expected": version,
                "action": "keep",
                "affected_finding_ids": [second_id],
            },
            headers=headers,
        ).json()["code"]
        == "keep_reason_required"
    )
    merged = owner.post(
        f"{path}/{second_id}/merge",
        json={
            "expected": version,
            "target_finding_id": first_id,
        },
        headers=headers,
    )
    assert merged.status_code == 200, merged.text
    version = merged.json()["version"]
    assert {item["label"] for item in merged.json()["findings"]} == {label}
    wrong_scope = owner.post(
        f"{path}/{first_id}/decision",
        json={
            "expected": version,
            "action": "redact",
            "group_scope": True,
            "affected_finding_ids": [first_id],
        },
        headers=headers,
    )
    assert wrong_scope.status_code == 422
    group_decision = owner.post(
        f"{path}/{first_id}/decision",
        json={
            "expected": version,
            "action": "redact",
            "group_scope": True,
            "affected_finding_ids": [first_id, second_id],
        },
        headers=headers,
    )
    assert group_decision.status_code == 200, group_decision.text
    version = group_decision.json()["version"]
    assert {item["action"] for item in group_decision.json()["findings"]} == {"redact"}
    split = owner.post(f"{path}/{second_id}/split", json={"expected": version}, headers=headers)
    assert split.status_code == 200, split.text
    version = split.json()["version"]
    assert {item["label"] for item in split.json()["findings"]} == {label, "PERSON_002"}
    keep = owner.post(
        f"{path}/{second_id}/decision",
        json={
            "expected": version,
            "action": "keep",
            "keep_reason": "intended_disclosure",
            "affected_finding_ids": [second_id],
        },
        headers=headers,
    )
    assert keep.status_code == 200, keep.text
    assert keep.json()["findings"][1]["keep_reason"] == "intended_disclosure"
    version = keep.json()["version"]
    alias_start = source.index("Alicia")
    alias = owner.post(
        path,
        json={
            "expected": version,
            "span": {"start": alias_start, "end": alias_start + 6},
            "category": "person",
        },
        headers=headers,
    ).json()
    alias_id = next(
        row["finding_id"] for row in alias["findings"] if row["span"]["start"] == alias_start
    )
    alias_label = owner.post(
        f"{path}/{alias_id}/decision",
        json={
            "expected": alias["version"],
            "action": "label",
            "affected_finding_ids": [alias_id],
        },
        headers=headers,
    ).json()
    assert (
        next(row["label"] for row in alias_label["findings"] if row["finding_id"] == alias_id)
        == "PERSON_003"
    )
    variant_merge = owner.post(
        f"{path}/{alias_id}/merge",
        json={"expected": alias_label["version"], "target_finding_id": first_id},
        headers=headers,
    )
    assert variant_merge.status_code == 200, variant_merge.text
    labels = {row["finding_id"]: row["label"] for row in variant_merge.json()["findings"]}
    assert labels == {first_id: "PERSON_001", second_id: "PERSON_002", alias_id: "PERSON_001"}


def test_review_undo_restores_multiple_edits_without_reusing_labels(intake_site):
    owner, other, _engine, workspace_id, _owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    _login(other, "intake-other@example.invalid")
    source = "😀 Ada met Ada."
    created = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, source=source, categories=[]),
        headers=headers,
    )
    version = created.json()["version"]
    path = f"/api/v1/documents/{version['document_id']}/findings"
    undo_path = f"/api/v1/documents/{version['document_id']}/review/undo"
    first = source.index("Ada")
    added = owner.post(
        path,
        json={
            "expected": version,
            "span": {"start": first, "end": first + 3},
            "category": "person",
        },
        headers=headers,
    ).json()
    version = added["version"]
    first_id = added["findings"][0]["finding_id"]
    labeled = owner.post(
        f"{path}/{first_id}/decision",
        json={
            "expected": version,
            "action": "label",
            "affected_finding_ids": [first_id],
        },
        headers=headers,
    ).json()
    version = labeled["version"]
    assert labeled["findings"][0]["label"] == "PERSON_001"
    second = source.rindex("Ada")
    added_second = owner.post(
        path,
        json={
            "expected": version,
            "span": {"start": second, "end": second + 3},
            "category": "person",
        },
        headers=headers,
    ).json()
    version = added_second["version"]
    second_id = added_second["findings"][1]["finding_id"]
    merged = owner.post(
        f"{path}/{second_id}/merge",
        json={
            "expected": version,
            "target_finding_id": first_id,
        },
        headers=headers,
    ).json()
    version = merged["version"]
    assert {item["label"] for item in merged["findings"]} == {"PERSON_001"}
    redacted = owner.post(
        f"{path}/{first_id}/decision",
        json={
            "expected": version,
            "action": "redact",
            "group_scope": True,
            "affected_finding_ids": [first_id, second_id],
        },
        headers=headers,
    ).json()
    version = redacted["version"]
    assert {item["action"] for item in redacted["findings"]} == {"redact"}
    assert (
        other.post(
            undo_path,
            json={"expected": version},
            headers={
                "Origin": ORIGIN,
                "X-CSRF-Token": other.get("/api/v1/auth/session").json()["csrf_token"],
            },
        ).status_code
        == 404
    )

    restored_decisions = owner.post(undo_path, json={"expected": version}, headers=headers)
    assert restored_decisions.status_code == 200, restored_decisions.text
    version = restored_decisions.json()["version"]
    assert [item["action"] for item in restored_decisions.json()["findings"]] == ["label", None]
    assert (
        owner.post(undo_path, json={"expected": redacted["version"]}, headers=headers).status_code
        == 409
    )
    unmerged = owner.post(undo_path, json={"expected": version}, headers=headers).json()
    version = unmerged["version"]
    assert [item["label"] for item in unmerged["findings"]] == ["PERSON_001", None]
    unadded = owner.post(undo_path, json={"expected": version}, headers=headers).json()
    version = unadded["version"]
    assert len(unadded["findings"]) == 1
    unlabeled = owner.post(undo_path, json={"expected": version}, headers=headers).json()
    version = unlabeled["version"]
    assert unlabeled["findings"][0]["label"] is None
    assert unlabeled["findings"][0]["action"] is None
    empty = owner.post(undo_path, json={"expected": version}, headers=headers).json()
    assert empty["findings"] == []
    activity = owner.get(f"/api/v1/workspaces/{workspace_id}/activity").json()
    codes = [item["event_code"] for item in activity["own_events"]]
    assert codes.count("finding_added") == 2
    assert codes.count("group_merged") == 1
    assert codes.count("review_decision_saved") == 2
    assert codes.count("review_edit_undone") == 5
    assert "Ada" not in str(activity)
    assert (
        owner.post(undo_path, json={"expected": empty["version"]}, headers=headers).json()["code"]
        == "nothing_to_undo"
    )

    new_finding = owner.post(
        path,
        json={
            "expected": empty["version"],
            "span": {"start": first, "end": first + 3},
            "category": "person",
        },
        headers=headers,
    ).json()
    new_id = new_finding["findings"][0]["finding_id"]
    new_label = owner.post(
        f"{path}/{new_id}/decision",
        json={
            "expected": new_finding["version"],
            "action": "label",
            "affected_finding_ids": [new_id],
        },
        headers=headers,
    ).json()
    assert new_label["findings"][0]["label"] == "PERSON_002"


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


def test_preview_recomputes_from_current_decisions_and_stays_owner_scoped(intake_site):
    owner, other, _engine, workspace_id, _owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    _login(other, "intake-other@example.invalid")
    source = "😀 Alice met Alice."
    created = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, source=source, categories=[]),
        headers=headers,
    )
    version = created.json()["version"]
    path = f"/api/v1/documents/{version['document_id']}"
    assert other.get(f"{path}/preview").status_code == 404
    assert owner.get(f"{path}/preview").headers["Cache-Control"] == "no-store"
    first = source.index("Alice")
    added = owner.post(
        f"{path}/findings",
        json={
            "expected": version,
            "span": {"start": first, "end": first + 5},
            "category": "person",
        },
        headers=headers,
    ).json()
    first_id = added["findings"][0]["finding_id"]
    pending = owner.get(f"{path}/preview").json()
    assert pending["status"] == "incomplete"
    assert pending["text"] == source
    assert pending["unresolved_finding_ids"] == [first_id]
    labeled = owner.post(
        f"{path}/findings/{first_id}/decision",
        json={"expected": added["version"], "action": "label", "affected_finding_ids": [first_id]},
        headers=headers,
    ).json()
    first_preview = owner.get(f"{path}/preview").json()
    assert first_preview["status"] == "complete"
    assert first_preview["version"] == labeled["version"]
    assert first_preview["text"] == "😀 PERSON_001 met Alice."
    assert first_preview["mappings"][0]["source_span"] == {"start": first, "end": first + 5}
    assert first_preview["mappings"][0]["preview_span"] == {"start": first, "end": first + 10}

    second = source.rindex("Alice")
    second_added = owner.post(
        f"{path}/findings",
        json={
            "expected": labeled["version"],
            "span": {"start": second, "end": second + 5},
            "category": "person",
        },
        headers=headers,
    ).json()
    second_id = second_added["findings"][1]["finding_id"]
    assert owner.get(f"{path}/preview").json()["unresolved_finding_ids"] == [second_id]
    second_labeled = owner.post(
        f"{path}/findings/{second_id}/decision",
        json={
            "expected": second_added["version"],
            "action": "label",
            "affected_finding_ids": [second_id],
        },
        headers=headers,
    ).json()
    assert owner.get(f"{path}/preview").json()["text"] == "😀 PERSON_001 met PERSON_002."
    merged = owner.post(
        f"{path}/findings/{second_id}/merge",
        json={"expected": second_labeled["version"], "target_finding_id": first_id},
        headers=headers,
    ).json()
    assert owner.get(f"{path}/preview").json()["text"] == "😀 PERSON_001 met PERSON_001."
    split = owner.post(
        f"{path}/findings/{second_id}/split",
        json={"expected": merged["version"]},
        headers=headers,
    ).json()
    assert owner.get(f"{path}/preview").json()["text"] == "😀 PERSON_001 met PERSON_003."
    undone = owner.post(
        f"{path}/review/undo", json={"expected": split["version"]}, headers=headers
    ).json()
    assert owner.get(f"{path}/preview").json()["text"] == "😀 PERSON_001 met PERSON_001."
    assert undone["version"]["decision_version"] == split["version"]["decision_version"] + 1
    revised = owner.put(
        f"{path}/source",
        json={"expected": undone["version"], "source": "😀 New source only."},
        headers=headers,
    )
    assert revised.status_code == 200
    new_preview = owner.get(f"{path}/preview").json()
    assert new_preview["version"] == revised.json()["version"]
    assert new_preview["text"] == "😀 New source only."
    assert new_preview["mappings"] == []


def test_completed_review_copy_txt_summary_and_stale_export_gate(intake_site):
    owner, other, engine, workspace_id, _owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    _login(other, "intake-other@example.invalid")
    source = "😀 Alice emailed a@example.com.\r\nAlice approved."
    created = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, source=source, categories=["email"]),
        headers=headers,
    )
    version = created.json()["version"]
    path = f"/api/v1/documents/{version['document_id']}"
    completion_path = f"{path}/complete"
    assert (
        owner.post(
            completion_path,
            json={
                "expected": version,
                "confirmed_preview": True,
            },
            headers=headers,
        ).json()["code"]
        == "scan_required"
    )
    scanned = owner.post(f"{path}/scan", json={"expected": version}, headers=headers)
    assert scanned.status_code == 200, scanned.text
    version = scanned.json()["version"]
    email_id = scanned.json()["suggestions"][0]["finding_id"]
    assert (
        owner.post(
            completion_path,
            json={
                "expected": version,
                "confirmed_preview": True,
            },
            headers=headers,
        ).json()["code"]
        == "pending_findings"
    )
    first = source.index("Alice")
    second = source.rindex("Alice")
    for position in (first, second):
        added = owner.post(
            f"{path}/findings",
            json={
                "expected": version,
                "span": {"start": position, "end": position + 5},
                "category": "person",
            },
            headers=headers,
        )
        assert added.status_code == 200, added.text
        version = added.json()["version"]
    rows = owner.get(f"{path}/findings").json()["findings"]
    first_id = next(row["finding_id"] for row in rows if row["span"]["start"] == first)
    second_id = next(row["finding_id"] for row in rows if row["span"]["start"] == second)
    redacted = owner.post(
        f"{path}/findings/{email_id}/decision",
        json={
            "expected": version,
            "action": "redact",
            "affected_finding_ids": [email_id],
        },
        headers=headers,
    ).json()
    version = redacted["version"]
    labeled = owner.post(
        f"{path}/findings/{first_id}/decision",
        json={
            "expected": version,
            "action": "label",
            "affected_finding_ids": [first_id],
        },
        headers=headers,
    ).json()
    version = labeled["version"]
    merged = owner.post(
        f"{path}/findings/{second_id}/merge",
        json={
            "expected": version,
            "target_finding_id": first_id,
        },
        headers=headers,
    ).json()
    version = merged["version"]
    grouped = owner.post(
        f"{path}/findings/{first_id}/decision",
        json={
            "expected": version,
            "action": "label",
            "group_scope": True,
            "affected_finding_ids": [first_id, second_id],
        },
        headers=headers,
    )
    assert grouped.status_code == 200, grouped.text
    version = grouped.json()["version"]
    expected_text = "😀 PERSON_001 emailed [REDACTED].\r\nPERSON_001 approved."
    assert owner.get(f"{path}/preview").json()["text"] == expected_text
    assert (
        owner.post(
            completion_path,
            json={
                "expected": version,
                "confirmed_preview": False,
            },
            headers=headers,
        ).json()["code"]
        == "confirmation_required"
    )
    completed = owner.post(
        completion_path,
        json={
            "expected": version,
            "confirmed_preview": True,
        },
        headers=headers,
    )
    assert completed.status_code == 200, completed.text
    completion_id = completed.json()["completion_id"]
    assert (
        owner.post(
            completion_path,
            json={
                "expected": version,
                "confirmed_preview": True,
            },
            headers=headers,
        ).json()["completion_id"]
        == completion_id
    )
    summary = owner.get(f"{path}/summary")
    assert summary.status_code == 200
    assert summary.json()["counts_by_category"] == {"person": 2, "email": 1}
    assert summary.json()["counts_by_action"] == {"label": 2, "redact": 1}
    assert summary.json()["last_output_generated_at"] is None
    decision_events = owner.get(f"/api/v1/workspaces/{workspace_id}/activity").json()["own_events"]
    assert sum(event["event_code"] == "review_decision_saved" for event in decision_events) == 3
    assert "Alice" not in summary.text and "a@example.com" not in summary.text
    assert other.get(f"{path}/summary").status_code == 404

    copy_payload = owner.post(
        f"{path}/exports/copy-payload",
        json={
            "expected": version,
        },
        headers=headers,
    )
    assert copy_payload.status_code == 200, copy_payload.text
    assert copy_payload.json()["text"] == expected_text
    assert copy_payload.headers["Cache-Control"] == "no-store"
    assert (
        other.post(
            f"{path}/exports/copy-payload",
            json={
                "expected": version,
            },
            headers={
                "Origin": ORIGIN,
                "X-CSRF-Token": other.get("/api/v1/auth/session").json()["csrf_token"],
            },
        ).status_code
        == 404
    )
    with Session(engine) as db:
        assert (
            db.scalars(
                select(ExportEvent).where(ExportEvent.document_id == UUID(version["document_id"]))
            ).all()
            == []
        )

    txt_event_id = str(uuid4())
    txt_body = {"expected": version, "event_id": txt_event_id}
    exported = owner.post(f"{path}/exports/txt", json=txt_body, headers=headers)
    assert exported.status_code == 200, exported.text
    assert exported.content == expected_text.encode("utf-8")
    assert exported.headers["Content-Type"].startswith("text/plain")
    assert exported.headers["Cache-Control"] == "no-store"
    assert exported.headers["X-Content-Type-Options"] == "nosniff"
    assert (
        exported.headers["Content-Disposition"]
        == f'attachment; filename="reviewed-{version["document_id"]}.txt"'
    )
    assert (
        owner.post(f"{path}/exports/txt", json=txt_body, headers=headers).content
        == exported.content
    )
    copy_event_id = str(uuid4())
    ack = owner.post(
        f"{path}/exports/copy-success",
        json={
            "expected": version,
            "completion_id": completion_id,
            "event_id": copy_event_id,
        },
        headers=headers,
    )
    assert ack.status_code == 200, ack.text
    assert (
        owner.post(
            f"{path}/exports/copy-success",
            json={
                "expected": version,
                "completion_id": completion_id,
                "event_id": copy_event_id,
            },
            headers=headers,
        ).status_code
        == 200
    )
    with Session(engine) as db:
        events = db.scalars(
            select(ExportEvent).where(ExportEvent.document_id == UUID(version["document_id"]))
        ).all()
        assert len(events) == 2
        assert {event.format for event in events} == {"copy", "txt"}
    assert owner.get(f"{path}/summary").json()["last_output_generated_at"] is not None
    assert owner.get(f"{path}/source").json()["status"] == "exported"

    revised = owner.put(
        f"{path}/source",
        json={
            "expected": version,
            "source": "New synthetic revision.",
        },
        headers=headers,
    )
    assert revised.status_code == 200, revised.text
    assert (
        owner.post(
            f"{path}/exports/copy-payload",
            json={
                "expected": version,
            },
            headers=headers,
        ).status_code
        == 409
    )
    assert (
        owner.post(
            f"{path}/exports/copy-payload",
            json={
                "expected": revised.json()["version"],
            },
            headers=headers,
        ).json()["code"]
        == "review_not_completed"
    )
    assert owner.get(f"{path}/summary").status_code == 409


def test_full_review_journey_persists_and_cleans_up(intake_site):
    owner, other, engine, workspace_id, _owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    _login(other, "intake-other@example.invalid")
    source = "😀 Alice met Alice. Contact ali@example.com."
    created = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, source=source, categories=["email"]),
        headers=headers,
    )
    assert created.status_code == 201, created.text
    version = created.json()["version"]
    path = f"/api/v1/documents/{version['document_id']}"
    scanned = owner.post(f"{path}/scan", json={"expected": version}, headers=headers)
    assert scanned.status_code == 200, scanned.text
    assert scanned.json()["match_count"] == 1
    version = scanned.json()["version"]
    email_id = scanned.json()["suggestions"][0]["finding_id"]

    for position in (source.index("Alice"), source.rindex("Alice")):
        added = owner.post(
            f"{path}/findings",
            json={
                "expected": version,
                "span": {"start": position, "end": position + 5},
                "category": "person",
            },
            headers=headers,
        )
        assert added.status_code == 200, added.text
        version = added.json()["version"]
    people = sorted(
        (
            row
            for row in owner.get(f"{path}/findings").json()["findings"]
            if row["category"] == "person"
        ),
        key=lambda row: row["span"]["start"],
    )
    first_id, second_id = (row["finding_id"] for row in people)
    kept = owner.post(
        f"{path}/findings/{email_id}/decision",
        json={
            "expected": version,
            "action": "keep",
            "keep_reason": "false_match",
            "affected_finding_ids": [email_id],
        },
        headers=headers,
    )
    assert kept.status_code == 200, kept.text
    version = kept.json()["version"]
    labeled = owner.post(
        f"{path}/findings/{first_id}/decision",
        json={"expected": version, "action": "label", "affected_finding_ids": [first_id]},
        headers=headers,
    )
    assert labeled.status_code == 200, labeled.text
    version = labeled.json()["version"]
    merged = owner.post(
        f"{path}/findings/{second_id}/merge",
        json={"expected": version, "target_finding_id": first_id},
        headers=headers,
    )
    assert merged.status_code == 200, merged.text
    version = merged.json()["version"]
    grouped = owner.post(
        f"{path}/findings/{first_id}/decision",
        json={
            "expected": version,
            "action": "label",
            "group_scope": True,
            "affected_finding_ids": [first_id, second_id],
        },
        headers=headers,
    )
    assert grouped.status_code == 200, grouped.text
    version = grouped.json()["version"]

    # Reopen through a fresh app instance before confirmation and export.
    with TestClient(create_app(owner.app.state.settings, engine=engine)) as reopened:
        reopened_headers = _login(reopened, "intake-owner@example.invalid")
        assert reopened.get(f"{path}/source").json()["text"] == source
        findings = reopened.get(f"{path}/findings").json()["findings"]
        assert len(findings) == 3
        assert {row["label"] for row in findings if row["category"] == "person"} == {"PERSON_001"}
        assert (
            next(row for row in findings if row["finding_id"] == email_id)["keep_reason"]
            == "false_match"
        )
        expected_text = "😀 PERSON_001 met PERSON_001. Contact ali@example.com."
        preview = reopened.get(f"{path}/preview")
        assert preview.status_code == 200 and preview.json()["text"] == expected_text
        completed = reopened.post(
            f"{path}/complete",
            json={"expected": version, "confirmed_preview": True},
            headers=reopened_headers,
        )
        assert completed.status_code == 200, completed.text
        summary = reopened.get(f"{path}/summary")
        assert summary.status_code == 200
        assert summary.json()["counts_by_action"] == {"label": 2, "keep": 1}
        assert "Alice" not in summary.text and "ali@example.com" not in summary.text
        exported = reopened.post(
            f"{path}/exports/txt",
            json={"expected": version, "event_id": str(uuid4())},
            headers=reopened_headers,
        )
        assert exported.status_code == 200, exported.text
        assert exported.content == expected_text.encode("utf-8")
        assert other.get(f"{path}/source").status_code == 404
        assert reopened.delete(path, headers=reopened_headers).json() == {"status": "deleted"}
        assert reopened.get(f"{path}/source").status_code == 410

    assert purge_unavailable_content(engine, now=datetime.now(UTC)).documents_purged == 1
    history = owner.get(
        f"/api/v1/workspaces/{workspace_id}/documents/{version['document_id']}/history"
    )
    assert history.status_code == 200
    assert history.json()["status"] == "deleted"
    assert history.json()["revision_total"] == 0
    assert source not in history.text


def test_zero_match_confirmation_and_explicit_keep_export(intake_site):
    owner, _other, _engine, workspace_id, _owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    source = "Training example only."
    created = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, source=source, categories=["email"]),
        headers=headers,
    )
    version = created.json()["version"]
    path = f"/api/v1/documents/{version['document_id']}"
    scanned = owner.post(f"{path}/scan", json={"expected": version}, headers=headers)
    assert scanned.status_code == 200
    assert scanned.json()["match_count"] == 0
    version = scanned.json()["version"]
    confirmed = owner.post(
        f"{path}/complete",
        json={
            "expected": version,
            "confirmed_preview": True,
        },
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    assert owner.get(f"{path}/summary").json()["finding_count"] == 0
    txt = owner.post(
        f"{path}/exports/txt",
        json={
            "expected": version,
            "event_id": str(uuid4()),
        },
        headers=headers,
    )
    assert txt.content == source.encode("utf-8")

    next_source = "Keep this phrase."
    revised = owner.put(
        f"{path}/source",
        json={
            "expected": version,
            "source": next_source,
        },
        headers=headers,
    )
    assert revised.status_code == 200
    version = revised.json()["version"]
    rescanned = owner.post(f"{path}/scan", json={"expected": version}, headers=headers)
    assert rescanned.status_code == 200
    version = rescanned.json()["version"]
    finding = owner.post(
        f"{path}/findings",
        json={
            "expected": version,
            "span": {"start": 0, "end": 4},
            "category": "custom",
        },
        headers=headers,
    ).json()
    finding_id = finding["findings"][0]["finding_id"]
    kept = owner.post(
        f"{path}/findings/{finding_id}/decision",
        json={
            "expected": finding["version"],
            "action": "keep",
            "keep_reason": "intended_disclosure",
            "affected_finding_ids": [finding_id],
        },
        headers=headers,
    )
    assert kept.status_code == 200, kept.text
    version = kept.json()["version"]
    assert owner.get(f"{path}/preview").json()["text"] == next_source
    assert (
        owner.post(
            f"{path}/complete",
            json={
                "expected": version,
                "confirmed_preview": True,
            },
            headers=headers,
        ).status_code
        == 200
    )
    assert owner.get(f"{path}/summary").json()["counts_by_action"] == {"keep": 1}
    assert owner.post(
        f"{path}/exports/txt",
        json={
            "expected": version,
            "event_id": str(uuid4()),
        },
        headers=headers,
    ).content == next_source.encode("utf-8")


def test_workspace_index_and_overview_preserve_member_content_boundary(intake_site):
    owner, other, engine, workspace_id, owner_id = intake_site
    owner_headers = _login(owner, "intake-owner@example.invalid")
    other_headers = _login(other, "intake-other@example.invalid")
    first = owner.post(
        "/api/v1/documents",
        json=_draft_body(
            workspace_id,
            source="Private owner text",
            title="Owner's confidential title",
        ),
        headers=owner_headers,
    )
    second = other.post(
        "/api/v1/documents",
        json=_draft_body(
            workspace_id,
            source="Different private text",
            title="Other's confidential title",
        ),
        headers=other_headers,
    )
    assert first.status_code == 201 and second.status_code == 201
    first_id = first.json()["version"]["document_id"]
    second_id = second.json()["version"]["document_id"]
    index_path = f"/api/v1/workspaces/{workspace_id}/documents"
    overview_path = f"/api/v1/workspaces/{workspace_id}/overview"

    added = owner.post(
        f"/api/v1/documents/{first_id}/findings",
        json={
            "expected": first.json()["version"],
            "span": {"start": 0, "end": 7},
            "category": "person",
        },
        headers=owner_headers,
    )
    assert added.status_code == 200, added.text
    own_index = owner.get(index_path)
    assert own_index.status_code == 200
    assert own_index.headers["Cache-Control"] == "no-store"
    assert len(own_index.json()) == 1
    assert own_index.json()[0]["id"] == first_id
    assert own_index.json()[0]["title"] == "Owner's confidential title"
    assert own_index.json()[0]["finding_count"] == 1
    assert own_index.json()[0]["decided_count"] == 0
    assert "Private owner text" not in own_index.text
    assert "Other's confidential title" not in own_index.text
    assert [item["id"] for item in other.get(index_path).json()] == [second_id]
    assert "Owner's confidential title" not in other.get(index_path).text
    own_overview = owner.get(overview_path).json()
    assert own_overview["own_total"] == 1
    assert own_overview["own_by_status"] == {"needs_review": 1}
    assert own_overview["workspace_total"] is None
    activity_path = f"/api/v1/workspaces/{workspace_id}/activity"
    own_activity = owner.get(activity_path).json()
    assert own_activity["own_total"] == 2
    assert {item["event_code"] for item in own_activity["own_events"]} == {
        "document_created",
        "finding_added",
    }
    assert {item["document_id"] for item in own_activity["own_events"]} == {first_id}
    assert own_activity["workspace_counts"] is None
    assert "Other's confidential title" not in str(own_activity)
    assert other.get(activity_path).json()["own_events"][0]["document_id"] == second_id

    with Session(engine) as session, session.begin():
        session.get(Membership, (workspace_id, owner_id)).role = "administrator"
    admin_index = owner.get(index_path)
    assert [item["id"] for item in admin_index.json()] == [first_id]
    admin_overview = owner.get(overview_path).json()
    assert admin_overview["workspace_total"] == 2
    assert "Other's confidential title" not in str(admin_overview)
    admin_activity = owner.get(activity_path).json()
    assert admin_activity["own_total"] == 2
    assert admin_activity["workspace_counts"] == {"document_created": 2, "finding_added": 1}
    assert second_id not in str(admin_activity)
    assert other.get(f"/api/v1/workspaces/{uuid4()}/documents").status_code == 404


def test_presets_are_member_readable_admin_managed_and_snapshotted_at_intake(intake_site):
    owner, other, engine, workspace_id, owner_id = intake_site
    owner_headers = _login(owner, "intake-owner@example.invalid")
    other_headers = _login(other, "intake-other@example.invalid")
    path = f"/api/v1/workspaces/{workspace_id}/presets"
    first_body = {
        "name": "Email labels",
        "categories": ["email"],
        "phone_region": "GB",
        "preferred_action": "redact",
        "is_default": True,
    }
    assert owner.get(path).json() == []
    assert owner.post(path, json=first_body, headers=owner_headers).status_code == 404
    with Session(engine) as session, session.begin():
        session.get(Membership, (workspace_id, owner_id)).role = "administrator"
    created = owner.post(path, json=first_body, headers=owner_headers)
    assert created.status_code == 201, created.text
    preset_id = created.json()["id"]
    assert created.json()["version"] == 1
    assert other.get(path).json() == [created.json()]
    assert (
        other.put(
            f"{path}/{preset_id}",
            json={**first_body, "expected_version": 1},
            headers=other_headers,
        ).status_code
        == 404
    )

    before = other.post(
        "/api/v1/documents",
        json=_draft_body(
            workspace_id,
            source="Synthetic first preset",
            categories=["phone"],
            phone_region="PH",
            preset_id=preset_id,
        ),
        headers=other_headers,
    )
    assert before.status_code == 201, before.text
    first_document_id = before.json()["version"]["document_id"]
    first_source = other.get(f"/api/v1/documents/{first_document_id}/source").json()
    assert first_source["categories"] == ["email"]
    assert first_source["phone_region"] == "GB"
    assert first_source["preferred_action"] == "redact"
    assert first_source["preset_id"] == preset_id
    assert first_source["preset_version"] == 1

    update_body = {
        **first_body,
        "categories": ["phone"],
        "phone_region": "US",
        "preferred_action": "label",
        "expected_version": 1,
    }
    changed = owner.put(f"{path}/{preset_id}", json=update_body, headers=owner_headers)
    assert changed.status_code == 200, changed.text
    assert changed.json()["version"] == 2
    assert (
        owner.put(f"{path}/{preset_id}", json=update_body, headers=owner_headers).status_code == 409
    )
    assert other.get(f"/api/v1/documents/{first_document_id}/source").json() == first_source

    after = other.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, source="Synthetic second preset", preset_id=preset_id),
        headers=other_headers,
    )
    assert after.status_code == 201, after.text
    second_source = other.get(
        f"/api/v1/documents/{after.json()['version']['document_id']}/source"
    ).json()
    assert second_source["categories"] == ["phone"]
    assert second_source["phone_region"] == "US"
    assert second_source["preferred_action"] == "label"
    assert second_source["preset_version"] == 2
    assert (
        other.post(
            "/api/v1/documents",
            json=_draft_body(workspace_id, preset_id=str(uuid4())),
            headers=other_headers,
        ).status_code
        == 404
    )
    assert other.get(f"/api/v1/workspaces/{workspace_id}/documents").status_code == 200


def test_document_history_is_owner_only_and_content_free_after_cleanup(intake_site):
    owner, other, engine, workspace_id, _owner_id = intake_site
    owner_headers = _login(owner, "intake-owner@example.invalid")
    _login(other, "intake-other@example.invalid")
    created = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, source="Secret synthetic first revision"),
        headers=owner_headers,
    )
    assert created.status_code == 201, created.text
    document_id = created.json()["version"]["document_id"]
    updated = owner.put(
        f"/api/v1/documents/{document_id}/source",
        json={
            "expected": created.json()["version"],
            "source": "Secret synthetic second revision",
        },
        headers=owner_headers,
    )
    assert updated.status_code == 200, updated.text
    path = f"/api/v1/workspaces/{workspace_id}/documents/{document_id}/history"
    history = owner.get(path)
    assert history.status_code == 200, history.text
    assert history.headers["Cache-Control"] == "no-store"
    assert history.json()["revision_total"] == 2
    assert [item["number"] for item in history.json()["revisions"]] == [2, 1]
    assert [item["is_current"] for item in history.json()["revisions"]] == [True, False]
    assert {item["event_code"] for item in history.json()["events"]} == {
        "document_created",
        "source_revised",
    }
    assert "Secret" not in history.text
    assert other.get(path).status_code == 404
    assert (
        owner.get(f"/api/v1/workspaces/{uuid4()}/documents/{document_id}/history").status_code
        == 404
    )

    assert (
        owner.delete(f"/api/v1/documents/{document_id}", headers=owner_headers).status_code == 200
    )
    purge_unavailable_content(engine, now=datetime.now(UTC))
    after = owner.get(path).json()
    assert after["status"] == "deleted"
    assert after["revision_total"] == 0
    assert after["revisions"] == []
    assert {item["event_code"] for item in after["events"]} == {
        "document_created",
        "source_revised",
        "document_deleted",
    }


def test_delete_and_expiry_deny_content_then_purge_protected_rows(intake_site):
    owner, other, engine, workspace_id, _owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    other_headers = _login(other, "intake-other@example.invalid")
    created = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, source="Delete this private source"),
        headers=headers,
    )
    assert created.status_code == 201
    document_id = created.json()["version"]["document_id"]
    path = f"/api/v1/documents/{document_id}"
    added = owner.post(
        f"{path}/findings",
        json={
            "expected": created.json()["version"],
            "span": {"start": 0, "end": 6},
            "category": "custom",
        },
        headers=headers,
    )
    assert added.status_code == 200
    assert other.delete(path, headers=other_headers).status_code == 404
    assert owner.delete(path, headers=headers).json() == {"status": "deleted"}
    assert owner.delete(path, headers=headers).status_code == 200
    assert owner.get(f"{path}/source").status_code == 410
    assert owner.get(f"{path}/preview").status_code == 410
    assert (
        owner.post(
            f"{path}/exports/copy-payload",
            json={"expected": added.json()["version"]},
            headers=headers,
        ).status_code
        == 410
    )
    with Session(engine) as session:
        assert (
            session.scalar(select(SourceRevision).where(SourceRevision.document_id == document_id))
            is not None
        )
    purged = purge_unavailable_content(engine, now=datetime.now(UTC))
    assert purged.documents_purged == 1
    assert purge_unavailable_content(engine, now=datetime.now(UTC)).documents_purged == 0
    with Session(engine) as session:
        document = session.get(Document, UUID(document_id))
        assert document.status == "deleted"
        assert document.current_revision_id is None
        assert document.title_ciphertext is None
        assert (
            session.scalars(
                select(SourceRevision).where(SourceRevision.document_id == document_id)
            ).all()
            == []
        )
        assert (
            session.scalars(select(Finding).where(Finding.document_id == document_id)).all() == []
        )
        events = session.scalars(
            select(AuditEvent).where(AuditEvent.document_id == document_id)
        ).all()
        assert {event.event_code for event in events} == {
            "document_created",
            "finding_added",
            "document_deleted",
        }
    assert owner.get(f"/api/v1/workspaces/{workspace_id}/documents").json() == []

    expired = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, source="Expired private source"),
        headers=headers,
    )
    expired_id = expired.json()["version"]["document_id"]
    with Session(engine) as session, session.begin():
        row = session.get(Document, UUID(expired_id))
        row.created_at = datetime.now(UTC) - timedelta(days=10)
        row.expires_at = datetime.now(UTC) - timedelta(days=1)
    assert owner.get(f"/api/v1/documents/{expired_id}/source").status_code == 410
    assert purge_unavailable_content(engine, now=datetime.now(UTC)).documents_purged == 1
    with Session(engine) as session:
        row = session.get(Document, UUID(expired_id))
        assert row.status == "expired"
        assert row.current_revision_id is None
        assert row.title_ciphertext is None
    index = owner.get(f"/api/v1/workspaces/{workspace_id}/documents").json()
    assert len(index) == 1 and index[0]["status"] == "expired"
    assert index[0]["title"] is None
    old_event_id = uuid4()
    with Session(engine) as session, session.begin():
        session.add(
            AuditEvent(
                id=old_event_id,
                workspace_id=workspace_id,
                actor_id=None,
                document_id=None,
                event_code="source_revised",
                outcome="completed",
                occurred_at=datetime.now(UTC) - timedelta(days=100),
            )
        )
    assert purge_unavailable_content(engine, now=datetime.now(UTC)).activity_removed == 1
    with Session(engine) as session:
        assert session.get(AuditEvent, old_event_id) is None
        assert (
            session.scalar(select(AuditEvent).where(AuditEvent.document_id == expired_id))
            is not None
        )
