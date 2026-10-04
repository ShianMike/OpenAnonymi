"""Actual route enumeration and output gates before/after workspace policy changes."""

import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event
from uuid import UUID, uuid4
from zipfile import ZipFile

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.db.models import Document, ExportEvent, Membership, User, Workspace
from app.db.team_review import ReviewHandoff
from app.reviews.service import CompletionRejected
from app.team_review.service import require_second_approval
from tests.batch_support import batch_client, review_and_confirm, upload
from tests.intake_support import _login

ROUTES = {
    "/api/v1/documents/{document_id}/exports/copy-payload",
    "/api/v1/documents/{document_id}/exports/copy-success",
    "/api/v1/documents/{document_id}/exports/txt",
    "/api/v1/documents/{document_id}/exports/docx",
    "/api/v1/documents/{document_id}/exports/csv",
    "/api/v1/documents/{document_id}/exports/pdf",
    "/api/v1/documents/{document_id}/exports/report",
    "/api/v1/batches/{batch_id}/outputs",
}
CASES = (
    "copy-payload",
    "copy-success",
    "txt",
    "docx",
    "pdf",
    "report",
    "csv_safe",
    "csv_unmodified",
    "zip_original",
    "zip_txt",
)


def ready_batch(site):
    owner, reviewer, engine, workspace, actor = site
    with Session(engine) as session, session.begin():
        session.get(Membership, (workspace, actor)).role = "administrator"
    owner, headers, batch = batch_client(site, categories=[])
    reviewer_headers = _login(reviewer, "intake-other@example.invalid")
    reviewer_id = reviewer.get("/api/v1/auth/session").json()["user_id"]
    version = upload(
        owner, headers, batch, b"Note,Value\nFictional safe text,Example\n", "fictional.csv"
    )
    base, findings, canonical = review_and_confirm(owner, headers, version)
    copied = owner.post(
        base + "/exports/copy-payload", json={"expected": findings["version"]}, headers=headers
    )
    assert copied.status_code == 200
    return (
        owner,
        reviewer,
        headers,
        reviewer_headers,
        reviewer_id,
        batch,
        base,
        findings["version"],
        copied.json()["completion_id"],
        canonical,
    )


def set_policy(owner, headers, workspace, policy):
    path = f"/api/v1/workspaces/{workspace}/settings"
    old = owner.get(path).json()
    result = owner.put(
        path,
        json={
            "expected_version": old["settings_version"],
            "content_retention_days": old["content_retention_days"],
            "activity_retention_days": old["activity_retention_days"],
            "approval_policy": policy,
        },
        headers=headers,
    )
    assert result.status_code == 200
    assert result.json()["approval_policy"] == policy
    return result.json()


def output(owner, headers, case, batch, base, version, completion):
    if case.startswith("zip_"):
        return owner.post(
            batch + "/outputs", json={"request_id": str(uuid4()), "mode": case[4:]}, headers=headers
        )
    body = {"expected": version, "event_id": str(uuid4())}
    suffix = case
    if case.startswith("csv_"):
        suffix = "csv"
        body["variant"] = "spreadsheet_safe" if case == "csv_safe" else "unmodified"
    elif case == "copy-success":
        body["completion_id"] = completion
    elif case == "copy-payload":
        body = {"expected": version}
    return owner.post(base + "/exports/" + suffix, json=body, headers=headers)


def test_every_registered_copy_export_and_zip_route_has_an_enforcement_case(intake_site):
    owner = intake_site[0]
    actual = {
        path
        for path, operations in owner.app.openapi()["paths"].items()
        if "post" in operations
        and ("exports" in operations["post"].get("tags", []) or path.endswith("/outputs"))
    }
    assert actual == ROUTES, "A new output route requires an explicit policy enforcement case."


@pytest.mark.parametrize("case", CASES)
def test_policy_on_blocks_each_real_output_until_exact_independent_approval(intake_site, case):
    owner, reviewer, headers, rh, reviewer_id, batch, base, version, completion, canonical = (
        ready_batch(intake_site)
    )
    _, _, engine, workspace, _ = intake_site
    document_id = UUID(version["document_id"])
    with Session(engine) as session:
        document = session.get(Document, document_id)
        before = (
            document.status,
            document.current_revision_id,
            document.decision_version,
            document.settings_version,
        )
    settings = set_policy(owner, headers, workspace, "always")
    assert settings["active_member_count"] == 2
    with Session(engine) as session:
        document = session.get(Document, document_id)
        assert (
            document.status,
            document.current_revision_id,
            document.decision_version,
            document.settings_version,
        ) == before
        assert session.get(ReviewHandoff, document_id) is None
    blocked = output(owner, headers, case, batch, base, version, completion)
    assert blocked.status_code == 409
    assert blocked.json()["code"] == (
        "no_reviewed_outputs" if case.startswith("zip_") else "approval_required_by_policy"
    )
    eligibility = owner.get(batch + "/outputs/eligibility").json()
    assert (
        eligibility["included_count"] == 0
        and eligibility["excluded"][0]["reason"] == "approval_required"
    )
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count(ExportEvent.id)).where(ExportEvent.document_id == document_id)
            )
            == 0
        )
    opted_out = owner.put(
        base + "/handoff",
        json={"expected": version, "reviewer_id": reviewer_id, "require_approval": False},
        headers=headers,
    )
    assert (
        opted_out.status_code == 422 and opted_out.json()["code"] == "approval_required_by_policy"
    )
    handoff = owner.put(
        base + "/handoff",
        json={"expected": version, "reviewer_id": reviewer_id, "require_approval": True},
        headers=headers,
    )
    assert handoff.status_code == 200
    version = handoff.json()["version"]
    confirmed = owner.post(
        base + "/complete", json={"expected": version, "confirmed_preview": True}, headers=headers
    )
    assert confirmed.status_code == 200
    completion = confirmed.json()["completion_id"]
    assert output(owner, headers, case, batch, base, version, completion).status_code == 409
    approved = reviewer.post(
        base + "/approval", json={"expected": version, "confirmed_preview": True}, headers=rh
    )
    assert approved.status_code == 200 and approved.json()["approved_at"]
    successful = output(owner, headers, case, batch, base, version, completion)
    assert successful.status_code == 200
    if case.startswith("zip_"):
        with ZipFile(io.BytesIO(successful.content)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            assert len(manifest["included"]) == 1 and manifest["excluded"] == []
    elif case == "copy-payload":
        assert successful.json()["text"] == canonical
    elif case == "txt":
        assert successful.content.decode() == canonical
    with Session(engine) as session, session.begin():
        session.get(Membership, (workspace, UUID(reviewer_id))).revoked_at = datetime.now(UTC)
    assert output(owner, headers, case, batch, base, version, completion).status_code == 409


def test_existing_optional_handoff_and_policy_toggle_do_not_rewrite_the_review(intake_site):
    owner, _, headers, _, reviewer_id, batch, base, version, _, _ = ready_batch(intake_site)
    _, _, engine, workspace, _ = intake_site
    assigned = owner.put(
        base + "/handoff",
        json={"expected": version, "reviewer_id": reviewer_id, "require_approval": False},
        headers=headers,
    )
    assert assigned.status_code == 200
    version = assigned.json()["version"]
    confirmed = owner.post(
        base + "/complete", json={"expected": version, "confirmed_preview": True}, headers=headers
    )
    assert confirmed.status_code == 200
    completion = confirmed.json()["completion_id"]
    set_policy(owner, headers, workspace, "always")
    handoff = owner.get(base + "/handoff").json()
    assert (
        handoff["require_approval"]
        and handoff["approval_policy"] == "always"
        and handoff["version"] == version
    )
    with Session(engine) as session:
        assert session.get(ReviewHandoff, UUID(version["document_id"])).require_approval is False
    assert output(owner, headers, "txt", batch, base, version, completion).status_code == 409
    set_policy(owner, headers, workspace, "owner_choice")
    assert owner.get(base + "/handoff").json()["version"] == version
    assert output(owner, headers, "txt", batch, base, version, completion).status_code == 200


def test_gate_reads_current_policy_even_with_an_old_workspace_in_the_identity_map(intake_site):
    owner, _, headers, _, _, _, _, version, _, _ = ready_batch(intake_site)
    _, _, engine, workspace, _ = intake_site
    with Session(engine) as session:
        cached = session.get(Workspace, workspace)
        document = session.get(Document, UUID(version["document_id"]))
        assert cached.approval_policy == "owner_choice"
        set_policy(owner, headers, workspace, "always")
        assert cached.approval_policy == "owner_choice"
        with pytest.raises(CompletionRejected, match="requires a reviewer"):
            require_second_approval(session, document)


@pytest.mark.parametrize("unavailable", ["revoked", "disabled"])
def test_approval_gate_reads_current_reviewer_access_with_cached_rows(intake_site, unavailable):
    owner, reviewer, headers, rh, reviewer_id, _, base, version, _, _ = ready_batch(intake_site)
    _, _, engine, workspace, _ = intake_site
    assigned = owner.put(
        base + "/handoff",
        json={"expected": version, "reviewer_id": reviewer_id, "require_approval": True},
        headers=headers,
    )
    assert assigned.status_code == 200
    version = assigned.json()["version"]
    assert (
        owner.post(
            base + "/complete",
            json={"expected": version, "confirmed_preview": True},
            headers=headers,
        ).status_code
        == 200
    )
    assert (
        reviewer.post(
            base + "/approval", json={"expected": version, "confirmed_preview": True}, headers=rh
        ).status_code
        == 200
    )
    reviewer_id = UUID(reviewer_id)
    with Session(engine) as session:
        document = session.get(Document, UUID(version["document_id"]))
        cached_member = session.get(Membership, (workspace, reviewer_id))
        cached_user = session.get(User, reviewer_id)
        require_second_approval(session, document)
        with Session(engine) as other_session, other_session.begin():
            if unavailable == "revoked":
                other_session.get(Membership, (workspace, reviewer_id)).revoked_at = datetime.now(
                    UTC
                )
            else:
                other_session.get(User, reviewer_id).disabled_at = datetime.now(UTC)
        assert cached_member.revoked_at is None and cached_user.disabled_at is None
        with pytest.raises(CompletionRejected, match="must approve"):
            require_second_approval(session, document)


def test_policy_enabled_while_output_waits_for_document_lock_is_enforced(intake_site):
    owner, _, headers, _, _, batch, base, version, completion, _ = ready_batch(intake_site)
    _, _, engine, workspace, _ = intake_site
    reached = Event()
    blocker = Session(engine)
    blocker.scalar(
        select(Document).where(Document.id == UUID(version["document_id"])).with_for_update()
    )

    def observe(_connection, _cursor, statement, _parameters, _context, _many):
        if "from documents" in statement.lower() and "for update" in statement.lower():
            reached.set()

    pool = ThreadPoolExecutor(max_workers=1)
    event.listen(engine, "before_cursor_execute", observe)
    try:
        pending = pool.submit(output, owner, headers, "txt", batch, base, version, completion)
        assert reached.wait(5)
        set_policy(owner, headers, workspace, "always")
        blocker.commit()
        result = pending.result(timeout=10)
        assert result.status_code == 409 and result.json()["code"] == "approval_required_by_policy"
    finally:
        blocker.rollback()
        blocker.close()
        event.remove(engine, "before_cursor_execute", observe)
        pool.shutdown(wait=True)
