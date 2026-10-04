"""Aggregate parity, single source decryption and current locked permissions."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.db.crypto import KeyRing
from app.db.models import Document, Membership, ScanRun, SourceRevision
from tests.csv_support import upload_csv
from tests.docx_fixtures import simple_docx
from tests.docx_support import confirm, mark, upload
from tests.intake_support import _draft_body, _login
from tests.styles_support import decide


def prepare(site, kind="pasted"):
    owner, other, engine, workspace, actor = site
    headers = _login(owner, "intake-owner@example.invalid")
    _login(other, "intake-other@example.invalid")
    if kind == "csv":
        base, findings, source = upload_csv(
            owner, headers, workspace, "Contact,Note\nnora@example.test,Fictional 😀\n"
        )
    elif kind == "docx":
        base, findings, source = upload(
            owner, headers, workspace, simple_docx("Fictional 😀 nora@example.test", "Later block")
        )
    else:
        created = owner.post(
            "/api/v1/documents",
            json=_draft_body(workspace, source="Fictional 😀 nora@example.test", categories=[]),
            headers=headers,
        )
        assert created.status_code == 201
        base = "/api/v1/documents/" + created.json()["version"]["document_id"]
        assert (
            owner.post(
                base + "/scan", json={"expected": created.json()["version"]}, headers=headers
            ).status_code
            == 200
        )
        findings, source = owner.get(base + "/findings").json(), owner.get(base + "/source").json()
    findings = mark(owner, headers, base, findings, source["text"], "nora@example.test", "email")
    return owner, other, engine, workspace, actor, headers, base, findings


@pytest.mark.parametrize("kind", ["pasted", "docx", "csv"])
def test_aggregate_matches_individual_views_and_decrypts_source_once(
    intake_site, monkeypatch, kind
):
    owner, _, engine, _, _, headers, base, findings = prepare(intake_site, kind)
    saved = decide(owner, headers, base, findings, findings["findings"][0], "label", "stand_in")
    assert saved.status_code == 200
    findings = saved.json()
    confirm(owner, headers, base, findings)
    expected = {
        name: owner.get(base + "/" + endpoint).json()
        for name, endpoint in (
            ("source", "source"),
            ("scan", "scan"),
            ("findings", "findings"),
            ("preview", "preview"),
            ("summary", "summary"),
            ("handoff", "handoff"),
        )
    }
    with Session(engine) as session:
        ciphertext = session.get(
            SourceRevision, UUID(findings["version"]["source_revision_id"])
        ).source_ciphertext
    decryptions = []
    original = KeyRing.decrypt_text

    def observed(keys, protected):
        if protected.ciphertext == ciphertext:
            decryptions.append(1)
        return original(keys, protected)

    monkeypatch.setattr(KeyRing, "decrypt_text", observed)
    response = owner.get(base + "/review-state")
    assert response.status_code == 200
    assert response.json() == expected
    assert len(decryptions) == 1
    assert "no-store" in response.headers["cache-control"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "content-encoding" not in response.headers


def test_aggregate_grant_is_required_for_admin_and_rechecked_after_revocation(intake_site):
    owner, other, engine, workspace, _, headers, base, findings = prepare(intake_site)
    reviewer = other.get("/api/v1/auth/session").json()["user_id"]
    with Session(engine) as session, session.begin():
        session.get(Membership, (workspace, UUID(reviewer))).role = "administrator"
    assert other.get(base + "/review-state").status_code == 404
    granted = owner.put(
        base + "/handoff",
        json={"expected": findings["version"], "reviewer_id": reviewer, "require_approval": False},
        headers=headers,
    )
    assert granted.status_code == 200
    response = other.get(base + "/review-state")
    assert response.status_code == 200 and response.json()["source"]["can_edit"] is False
    assert response.json()["summary"] is None
    revoked = owner.put(
        base + "/handoff",
        json={
            "expected": granted.json()["version"],
            "reviewer_id": None,
            "require_approval": False,
        },
        headers=headers,
    )
    assert revoked.status_code == 200
    denied = other.get(base + "/review-state")
    assert denied.status_code == 404 and "nora@example.test" not in denied.text


@pytest.mark.parametrize("unavailable", ["expired", "deleted", "owner_disabled", "owner_revoked"])
def test_aggregate_denies_unavailable_content(intake_site, unavailable):
    owner, _, engine, workspace, actor, _, base, findings = prepare(intake_site)
    from app.db.models import User

    with Session(engine) as session, session.begin():
        document = session.get(Document, UUID(findings["version"]["document_id"]))
        if unavailable == "expired":
            document.created_at = datetime.now(UTC) - timedelta(days=1)
            document.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        elif unavailable == "deleted":
            document.deleted_at = datetime.now(UTC)
            document.status = "deleted"
        elif unavailable == "owner_disabled":
            session.get(User, actor).disabled_at = datetime.now(UTC)
        else:
            session.get(Membership, (workspace, actor)).revoked_at = datetime.now(UTC)
    response = owner.get(base + "/review-state")
    assert response.status_code in (401, 404, 410)
    assert "nora@example.test" not in response.text


def test_aggregate_recovers_a_stale_scan_before_returning_all_current_metadata(intake_site):
    owner, _, engine, _, _, _, base, findings = prepare(intake_site)
    with Session(engine) as session, session.begin():
        document = session.get(Document, UUID(findings["version"]["document_id"]))
        document.status = "scanning"
        scan = session.query(ScanRun).filter(ScanRun.document_id == document.id).one()
        scan.status = "scanning"
        scan.started_at = datetime.now(UTC) - timedelta(minutes=3)
    response = owner.get(base + "/review-state")
    assert response.status_code == 200
    result = response.json()
    assert result["source"]["status"] == "failed"
    assert (
        result["scan"]["status"] == "failed"
        and result["scan"]["failure_code"] == "scan_interrupted"
    )
    assert all(
        result[name]["version"] == result["source"]["version"]
        for name in ("scan", "findings", "preview", "handoff")
    )
