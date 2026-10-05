"""Actual manual/column transactions recheck access and roll back every side effect."""

import hashlib
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Decision, Document, Finding, LabelCounter, Membership, User
from app.db.models import Session as StoredSession
from app.db.replacement_secrets import DocumentReplacementSecret
from app.db.team_review import ReviewHandoff
from tests.csv_support import upload_csv
from tests.docx_support import mark
from tests.intake_support import _draft_body, _login
from tests.test_review_mutation_access_pg import fingerprint as decision_fingerprint

SOURCE = "😀 First: nora@example.test. Second: nora@example.test. Unmarked: Other."
EMAIL = "nora@example.test"
MANUAL = ("add", "revise", "remove", "exact", "split", "merge", "noop_revise", "noop_merge")
OPERATIONS = (*MANUAL, "column")


def fingerprint(engine, document_id):
    """Include spans, label allocation, styles and encrypted replacement-seed state."""
    with Session(engine) as session:
        secret = session.get(DocumentReplacementSecret, document_id)
        return (
            decision_fingerprint(engine, document_id),
            [
                tuple(
                    getattr(row, name)
                    for name in (
                        "id",
                        "source_revision_id",
                        "group_id",
                        "category",
                        "origin",
                        "rule_id",
                        "rule_version",
                        "date_format",
                        "reason",
                        "scan_run_id",
                        "start_offset",
                        "end_offset",
                        "created_at",
                        "removed_at",
                    )
                )
                for row in session.scalars(
                    select(Finding).where(Finding.document_id == document_id).order_by(Finding.id)
                )
            ],
            [
                (row.category, row.next_number)
                for row in session.scalars(
                    select(LabelCounter)
                    .where(LabelCounter.document_id == document_id)
                    .order_by(LabelCounter.category)
                )
            ],
            [
                (row.finding_id, row.style_option)
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
            None
            if secret is None
            else (
                hashlib.sha256(secret.secret_ciphertext).hexdigest(),
                secret.key_id,
                secret.created_at,
            ),
        )


def prepare(site, operation):
    owner, other, engine, workspace, actor = site
    headers = _login(owner, "intake-owner@example.invalid")
    other_headers = _login(other, "intake-other@example.invalid")
    if operation == "column":
        base, state, _ = upload_csv(
            owner,
            headers,
            workspace,
            "Contact,Note\nnora@example.test,Fictional\nother@example.test,Later\n",
            "email",
        )
        assert len(state["findings"]) == 2
    else:
        result = owner.post(
            "/api/v1/documents",
            headers=headers,
            json=_draft_body(workspace, source=SOURCE, categories=[]),
        )
        assert result.status_code == 201
        state = result.json()
        base = "/api/v1/documents/" + state["version"]["document_id"]
        assert (
            owner.post(
                base + "/scan", headers=headers, json={"expected": state["version"]}
            ).status_code
            == 200
        )
        state = mark(
            owner, headers, base, owner.get(base + "/findings").json(), SOURCE, EMAIL, "email"
        )
        if operation in ("split", "merge", "noop_merge"):
            state = mark(owner, headers, base, state, SOURCE, EMAIL, "email", SOURCE.rindex(EMAIL))
        if operation in ("split", "noop_merge"):
            result = mutate(owner, headers, base, state, "merge")
            assert result.status_code == 200
            state = result.json()
    return owner, other, engine, workspace, actor, headers, other_headers, base, state


def mutate(client, headers, base, state, operation):
    findings = sorted(state["findings"], key=lambda item: item["span"]["start"])
    first = findings[0]
    route = base + "/findings/" + first["finding_id"]
    body = {"expected": state["version"]}
    method = client.post
    if operation == "column":
        route = base + "/columns/0/decision"
        body.update(
            action="label",
            style="stand_in",
            same_text_same_entity=False,
            affected_finding_ids=[item["finding_id"] for item in findings],
        )
    elif operation == "add":
        route = base + "/findings"
        start = SOURCE.index("Other")
        body.update(span={"start": start, "end": start + len("Other")}, category="custom")
    elif operation in ("revise", "noop_revise"):
        method = client.put
        span = dict(first["span"])
        category = first["category"]
        if operation == "revise":
            span["end"] -= 1
            category = "custom"
        body.update(span=span, category=category)
    elif operation == "remove":
        route += "/remove"
    elif operation == "exact":
        route += "/exact-matches"
        start = SOURCE.rindex(EMAIL)
        body["span"] = {"start": start, "end": start + len(EMAIL)}
    elif operation == "split":
        route += "/split"
    else:
        route += "/merge"
        body["target_finding_id"] = findings[1]["finding_id"]
    return method(route, headers=headers, json=body)


def hook_operation(monkeypatch, operation, phase, after):
    from app.groups import columns, service

    module = columns if operation == "column" else service
    hook = (
        "_snapshot"
        if phase == "after_snapshot"
        else ("owned_document" if operation == "column" else "_current_locked")
    )
    original = getattr(module, hook)

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        after()
        return result

    monkeypatch.setattr(module, hook, changed)


def revoke(engine, workspace, actor, change):
    with Session(engine) as session, session.begin():
        now = datetime.now(UTC)
        if change == "session":
            for row in session.scalars(select(StoredSession).where(StoredSession.user_id == actor)):
                row.revoked_at = now
        elif change == "membership":
            session.get(Membership, (workspace, actor)).revoked_at = now
        else:
            session.get(User, actor).disabled_at = now


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("phase", ["after_lock", "after_snapshot"])
@pytest.mark.parametrize("change", ["session", "membership", "disabled"])
def test_late_manual_access_loss_rolls_back_all_state(
    intake_site, monkeypatch, operation, phase, change
):
    owner, _, engine, workspace, actor, headers, _, base, state = prepare(intake_site, operation)
    document_id = UUID(state["version"]["document_id"])
    before = fingerprint(engine, document_id)
    hook_operation(monkeypatch, operation, phase, lambda: revoke(engine, workspace, actor, change))
    response = mutate(owner, headers, base, state, operation)
    assert response.status_code in (401, 404)
    assert EMAIL not in response.text and "EMAIL_001" not in response.text
    assert fingerprint(engine, document_id) == before


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("phase", ["after_lock", "after_snapshot"])
def test_manual_wall_clock_expiry_rolls_back_all_state(intake_site, monkeypatch, operation, phase):
    owner, _, engine, _, _, headers, _, base, state = prepare(intake_site, operation)
    document_id = UUID(state["version"]["document_id"])
    before = fingerprint(engine, document_id)
    with Session(engine) as session, session.begin():
        session.get(Document, document_id).expires_at = datetime.now(UTC) + timedelta(seconds=0.3)
    hook_operation(monkeypatch, operation, phase, lambda: time.sleep(0.35))
    response = mutate(owner, headers, base, state, operation)
    assert response.status_code == 410 and EMAIL not in response.text
    assert fingerprint(engine, document_id) == before


@pytest.mark.parametrize("operation", MANUAL)
@pytest.mark.parametrize("phase", ["after_lock", "after_snapshot"])
def test_manual_reviewer_grant_removal_rolls_back(intake_site, monkeypatch, operation, phase):
    owner, reviewer, engine, _, _, headers, rh, base, state = prepare(intake_site, operation)
    reviewer_id = reviewer.get("/api/v1/auth/session").json()["user_id"]
    granted = owner.put(
        base + "/handoff",
        headers=headers,
        json={
            "expected": state["version"],
            "reviewer_id": reviewer_id,
            "require_approval": False,
        },
    )
    assert granted.status_code == 200
    state = reviewer.get(base + "/findings").json()
    document_id = UUID(state["version"]["document_id"])
    before = fingerprint(engine, document_id)

    def remove_grant():
        with Session(engine) as session, session.begin():
            session.get(ReviewHandoff, document_id).reviewer_id = None

    hook_operation(monkeypatch, operation, phase, remove_grant)
    response = mutate(reviewer, rh, base, state, operation)
    assert response.status_code == 404 and EMAIL not in response.text
    assert fingerprint(engine, document_id) == before


@pytest.mark.parametrize("operation", OPERATIONS)
def test_current_owner_mutations_commit_and_noops_preserve_state(intake_site, operation):
    owner, _, engine, _, _, headers, _, base, state = prepare(intake_site, operation)
    document_id = UUID(state["version"]["document_id"])
    before = fingerprint(engine, document_id)
    response = mutate(owner, headers, base, state, operation)
    assert response.status_code == 200
    after = fingerprint(engine, document_id)
    assert (after == before) == operation.startswith("noop_")
    assert owner.get(base + "/findings").json() == response.json()


@pytest.mark.parametrize("operation", MANUAL)
def test_current_assigned_reviewer_can_still_edit_findings(intake_site, operation):
    owner, reviewer, _, _, _, headers, rh, base, state = prepare(intake_site, operation)
    reviewer_id = reviewer.get("/api/v1/auth/session").json()["user_id"]
    assert (
        owner.put(
            base + "/handoff",
            headers=headers,
            json={
                "expected": state["version"],
                "reviewer_id": reviewer_id,
                "require_approval": False,
            },
        ).status_code
        == 200
    )
    state = reviewer.get(base + "/findings").json()
    response = mutate(reviewer, rh, base, state, operation)
    assert response.status_code == 200
    assert reviewer.get(base + "/findings").json() == response.json()
    assert (
        reviewer.post(
            base + "/columns/0/decision",
            headers=rh,
            json={
                "expected": response.json()["version"],
                "action": "label",
                "affected_finding_ids": [],
                "same_text_same_entity": False,
            },
        ).status_code
        == 404
    )
