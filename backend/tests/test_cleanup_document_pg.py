"""Immediate and batch purge share the same complete protected-content lifecycle."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.cleanup.background import purge_deleted_document
from app.cleanup.service import mark_document_deleted, purge_document, purge_unavailable_content
from app.db.custom_rules import DocumentRuleSnapshot, RuleVersion, WorkspaceRule
from app.db.durable import ReviewUndoEntry
from app.db.models import (
    Decision,
    Document,
    EntityGroup,
    Finding,
    LabelCounter,
    ReviewCompletion,
    ScanRun,
    SourceRevision,
)
from app.db.recovery import RecoverySnapshot
from app.db.team_review import FindingComment, ReviewApproval, ReviewHandoff
from tests.intake_support import _draft_body, _login
from tests.test_autosave_pg import body, path
from tests.test_custom_rules_pg import RULE, admin_headers
from tests.test_team_review_pg import _decision

CHILDREN = (
    SourceRevision,
    EntityGroup,
    Finding,
    Decision,
    ReviewCompletion,
    ScanRun,
    LabelCounter,
    ReviewUndoEntry,
    RecoverySnapshot,
    ReviewHandoff,
    FindingComment,
    ReviewApproval,
    DocumentRuleSnapshot,
)


def prepared(site, headers, reviewer_id):
    owner, reviewer, _, workspace, _ = site
    saved = owner.post(
        "/api/v1/documents",
        json=_draft_body(
            workspace, source="CASE-123456 email nora@example.com", categories=["email"]
        ),
        headers=headers,
    ).json()
    base = f"/api/v1/documents/{saved['version']['document_id']}"
    scan = owner.post(base + "/scan", json={"expected": saved["version"]}, headers=headers).json()
    version = scan["version"]
    for item in scan["suggestions"]:
        version = _decision(owner, base, item["finding_id"], version, headers, action="label")
    handoff = owner.put(
        base + "/handoff",
        json={"expected": version, "reviewer_id": str(reviewer_id), "require_approval": True},
        headers=headers,
    )
    assert handoff.status_code == 200
    version = handoff.json()["version"]
    comment = owner.post(
        base + f"/findings/{scan['suggestions'][0]['finding_id']}/comments",
        json={"id": str(uuid4()), "expected": version, "text": "Synthetic confidential comment"},
        headers=headers,
    )
    assert comment.status_code == 201
    assert (
        owner.post(
            base + "/complete",
            json={"expected": version, "confirmed_preview": True},
            headers=headers,
        ).status_code
        == 200
    )
    rh = _login(reviewer, "intake-other@example.invalid")
    assert (
        reviewer.post(
            base + "/approval", json={"expected": version, "confirmed_preview": True}, headers=rh
        ).status_code
        == 200
    )
    assert (
        owner.put(
            path(workspace, uuid4()),
            json=body(document=version["document_id"], base=version),
            headers=headers,
        ).status_code
        == 200
    )
    return UUID(version["document_id"])


def test_shared_purge_removes_every_existing_child_and_preserves_audit(intake_site):
    owner, reviewer, engine, workspace, actor = intake_site
    headers = admin_headers(intake_site)
    assert (
        owner.post(f"/api/v1/workspaces/{workspace}/rules", json=RULE, headers=headers).status_code
        == 201
    )
    _login(reviewer, "intake-other@example.invalid")
    reviewer_id = UUID(reviewer.get("/api/v1/auth/session").json()["user_id"])
    ids = [prepared(intake_site, headers, reviewer_id) for _ in range(2)]
    now = datetime.now(UTC)
    finding_ids = {}

    def child_count(session, model, doc):
        predicate = (
            Decision.finding_id.in_(finding_ids[doc])
            if model is Decision
            else model.document_id == doc
        )
        return session.scalar(select(func.count()).select_from(model).where(predicate))

    with Session(engine) as session, session.begin():
        for doc in ids:
            finding_ids[doc] = session.scalars(
                select(Finding.id).where(Finding.document_id == doc)
            ).all()
            for model in CHILDREN:
                assert child_count(session, model, doc) > 0, model.__tablename__
        expired = session.get(Document, ids[0])
        expired.created_at = now - timedelta(days=2)
        expired.expires_at = now - timedelta(days=1)
    assert purge_unavailable_content(engine, now=now).documents_purged == 1
    mark_document_deleted(engine, document_id=ids[1], actor_id=actor, now=now)
    with Session(engine) as session, session.begin():
        assert purge_document(session, session.get(Document, ids[1]), now)
    with Session(engine) as session:
        for doc in ids:
            for model in CHILDREN:
                assert child_count(session, model, doc) == 0, model.__tablename__
            row = session.get(Document, doc)
            assert (
                row.current_revision_id is None
                and row.title_ciphertext is None
                and row.title_key_id is None
            )
            assert (
                owner.get(f"/api/v1/workspaces/{workspace}/documents/{doc}/history").json()[
                    "event_total"
                ]
                > 0
            )
        # Workspace rule definitions belong to the workspace, not either document.
        assert (
            session.scalar(
                select(func.count())
                .select_from(WorkspaceRule)
                .where(WorkspaceRule.workspace_id == workspace)
            )
            == 1
        )
        assert session.scalar(select(func.count()).select_from(RuleVersion)) > 0


def test_purge_refuses_active_document(intake_site):
    owner, _, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    draft = owner.post("/api/v1/documents", json=_draft_body(workspace), headers=headers).json()
    doc = UUID(draft["version"]["document_id"])
    with Session(engine) as session, session.begin():
        assert not purge_document(session, session.get(Document, doc), datetime.now(UTC))
    assert owner.get(f"/api/v1/documents/{doc}/source").status_code == 200


def test_background_failure_never_reverts_deletion_and_batch_retries(
    intake_site, monkeypatch, caplog
):
    from app.cleanup import background

    owner, _, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    doc = UUID(
        owner.post("/api/v1/documents", json=_draft_body(workspace), headers=headers).json()[
            "version"
        ]["document_id"]
    )

    def fail(*_args):
        raise RuntimeError("PRIVATE_BACKGROUND_SENTINEL")

    monkeypatch.setattr(background, "purge_document", fail)
    assert owner.delete(f"/api/v1/documents/{doc}", headers=headers).status_code == 200
    assert owner.get(f"/api/v1/documents/{doc}/source").status_code == 410
    assert "PRIVATE_BACKGROUND_SENTINEL" not in caplog.text and str(doc) not in caplog.text
    assert purge_unavailable_content(engine, now=datetime.now(UTC)).documents_purged == 1
    purge_deleted_document(engine, doc)  # already purged, harmless
