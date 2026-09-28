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
from app.config import Settings
from app.contracts import VersionRef
from app.db.crypto import KeyRing
from app.db.models import (
    Decision,
    Document,
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
