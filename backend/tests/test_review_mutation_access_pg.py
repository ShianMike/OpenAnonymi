"""Real transactions must roll back decision/Undo state after late access loss."""

import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.durable import ReviewUndoEntry
from app.db.models import AuditEvent, Decision, Document, EntityGroup, Finding, Membership, User
from app.db.models import Session as StoredSession
from tests.test_review_state_pg import prepare


def fingerprint(engine, document_id):
    with Session(engine) as session:
        item = session.get(Document, document_id)
        return (
            item.decision_version,
            item.settings_version,
            item.status,
            [
                (row.finding_id, row.action, row.style, row.keep_reason, row.decision_version)
                for row in session.scalars(
                    select(Decision)
                    .where(
                        Decision.finding_id.in_(
                            select(Finding.id).where(Finding.document_id == document_id)
                        )
                    )
                    .order_by(Decision.finding_id)
                )
            ],
            [
                (row.id, row.payload, row.sequence, row.after_version)
                for row in session.scalars(
                    select(ReviewUndoEntry)
                    .where(ReviewUndoEntry.document_id == document_id)
                    .order_by(ReviewUndoEntry.id)
                )
            ],
            [
                row.id
                for row in session.scalars(
                    select(AuditEvent)
                    .where(AuditEvent.document_id == document_id)
                    .order_by(AuditEvent.id)
                )
            ],
            [
                (row.id, row.label)
                for row in session.scalars(
                    select(EntityGroup)
                    .where(EntityGroup.document_id == document_id)
                    .order_by(EntityGroup.id)
                )
            ],
        )


def decision(owner, headers, base, findings):
    item = findings["findings"][0]["finding_id"]
    return owner.post(
        base + "/findings/" + item + "/decision",
        headers=headers,
        json={
            "expected": findings["version"],
            "action": "label",
            "keep_reason": None,
            "affected_finding_ids": [item],
            "group_scope": False,
        },
    )


@pytest.mark.parametrize("operation", ["decision", "undo"])
@pytest.mark.parametrize("phase", ["after_lock", "after_snapshot"])
@pytest.mark.parametrize("change", ["session", "membership", "disabled"])
def test_late_access_loss_rolls_back_all_changes(
    intake_site, monkeypatch, operation, phase, change
):
    owner, _, engine, workspace, actor, headers, base, findings = prepare(intake_site)
    if operation == "undo":
        response = decision(owner, headers, base, findings)
        assert response.status_code == 200
        findings = response.json()
    document_id = UUID(findings["version"]["document_id"])
    before = fingerprint(engine, document_id)
    from app.groups import decisions, service

    module = decisions if operation == "decision" else service
    hook = "_current_locked" if phase == "after_lock" else "_snapshot"
    original = getattr(module, hook)

    def revoke(*args, **kwargs):
        result = original(*args, **kwargs)
        with Session(engine) as session, session.begin():
            now = datetime.now(UTC)
            if change == "session":
                for row in session.scalars(
                    select(StoredSession).where(StoredSession.user_id == actor)
                ):
                    row.revoked_at = now
            elif change == "membership":
                session.get(Membership, (workspace, actor)).revoked_at = now
            else:
                session.get(User, actor).disabled_at = now
        return result

    monkeypatch.setattr(module, hook, revoke)
    response = (
        decision(owner, headers, base, findings)
        if operation == "decision"
        else owner.post(
            base + "/review/undo", headers=headers, json={"expected": findings["version"]}
        )
    )
    assert response.status_code in (401, 404)
    assert "nora@example.test" not in response.text
    assert fingerprint(engine, document_id) == before


@pytest.mark.parametrize("operation", ["decision", "undo"])
@pytest.mark.parametrize("phase", ["after_lock", "after_snapshot"])
def test_real_wall_clock_expiry_rolls_back_decision_and_undo(
    intake_site, monkeypatch, operation, phase
):
    owner, _, engine, _, _, headers, base, findings = prepare(intake_site)
    if operation == "undo":
        result = decision(owner, headers, base, findings)
        assert result.status_code == 200
        findings = result.json()
    document_id = UUID(findings["version"]["document_id"])
    before = fingerprint(engine, document_id)
    from app.groups import decisions, service

    module = decisions if operation == "decision" else service
    hook = "_current_locked" if phase == "after_lock" else "_snapshot"
    original = getattr(module, hook)
    with Session(engine) as session, session.begin():
        session.get(Document, document_id).expires_at = datetime.now(UTC) + timedelta(seconds=0.2)

    def delay(*args, **kwargs):
        result = original(*args, **kwargs)
        time.sleep(0.25)
        return result

    monkeypatch.setattr(module, hook, delay)
    response = (
        decision(owner, headers, base, findings)
        if operation == "decision"
        else owner.post(
            base + "/review/undo", headers=headers, json={"expected": findings["version"]}
        )
    )
    assert response.status_code == 410 and "nora@example.test" not in response.text
    assert fingerprint(engine, document_id) == before
