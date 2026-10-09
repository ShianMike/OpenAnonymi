"""Persistent actor-scoped undo through actual API and database transactions."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.cleanup.service import purge_unavailable_content
from app.config import Settings
from app.contracts import VersionRef
from app.db.durable import AttemptEvent, ReviewUndoEntry
from app.db.models import Document, EntityGroup, Finding
from app.factory import create_app
from app.groups.undo_store import remember
from tests.intake_support import _draft_body, _login


def setup_review(intake_site):
    owner, other, engine, workspace, actor = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    created = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace, source="Ada met Ada.", categories=[]),
        headers=headers,
    )
    assert created.status_code == 201
    version = created.json()["version"]
    base = f"/api/v1/documents/{version['document_id']}"
    response = owner.post(
        base + "/findings",
        json={"expected": version, "span": {"start": 0, "end": 3}, "category": "person"},
        headers=headers,
    )
    assert response.status_code == 200
    return owner, other, engine, actor, headers, base, response.json()


def test_reload_and_new_application_can_undo_the_persisted_edit(intake_site):
    owner, other, engine, _, headers, base, added = setup_review(intake_site)
    assert added["undo_available"] == 1
    assert owner.get(base + "/findings").json()["undo_available"] == 1
    _login(other, "intake-other@example.invalid")
    assert other.get(base + "/findings").status_code == 404
    settings = Settings(**owner.app.state.settings.model_dump(), _env_file=None)
    with TestClient(create_app(settings, engine=engine)) as restarted:
        next_headers = _login(restarted, "intake-owner@example.invalid")
        loaded = restarted.get(base + "/findings").json()
        assert loaded["undo_available"] == 1
        undone = restarted.post(
            base + "/review/undo", json={"expected": loaded["version"]}, headers=next_headers
        )
        assert undone.status_code == 200
        assert undone.json()["findings"] == [] and undone.json()["undo_available"] == 0
    assert owner.get(base + "/findings").json()["undo_available"] == 0
    stale = owner.post(base + "/review/undo", json={"expected": added["version"]}, headers=headers)
    assert stale.status_code == 409


def test_source_change_and_settings_change_clear_history(intake_site):
    owner, _, engine, _, headers, base, added = setup_review(intake_site)
    changed = owner.put(
        base + "/source",
        json={"expected": added["version"], "source": "Ada met Ada again."},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(ReviewUndoEntry)
                .where(ReviewUndoEntry.document_id == UUID(added["version"]["document_id"]))
            )
            == 0
        )
    version = changed.json()["version"]
    marked = owner.post(
        base + "/findings",
        json={"expected": version, "span": {"start": 0, "end": 3}, "category": "person"},
        headers=headers,
    ).json()
    changed = owner.put(
        base + "/scan-settings",
        json={"expected": marked["version"], "categories": ["email"], "phone_region": "PH"},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    assert owner.get(base + "/findings").json()["undo_available"] == 0
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(ReviewUndoEntry)
                .where(ReviewUndoEntry.document_id == UUID(version["document_id"]))
            )
            == 0
        )


def test_undo_is_atomic_expires_per_entry_and_oversized_edit_clears_chain(intake_site):
    owner, _, engine, actor, _, base, added = setup_review(intake_site)
    version = VersionRef.model_validate(added["version"])
    with pytest.raises(RuntimeError), Session(engine) as session, session.begin():
        document = session.get(Document, version.document_id)
        document.decision_version += 1
        remember(
            session,
            actor_id=actor,
            before=version,
            after=version.model_copy(update={"decision_version": version.decision_version + 1}),
            payload={"findings": {}, "decisions": {}, "created": []},
            now=datetime.now(UTC),
        )
        raise RuntimeError("Synthetic transaction rollback")
    assert owner.get(base + "/findings").json()["undo_available"] == 1
    with Session(engine) as session, session.begin():
        document = session.get(Document, version.document_id)
        document.decision_version += 1
        remember(
            session,
            actor_id=actor,
            before=version,
            after=version.model_copy(update={"decision_version": version.decision_version + 1}),
            payload={
                "findings": {},
                "decisions": {},
                "created": [],
                "size_canary": "x" * (512 * 1024),
            },
            now=datetime.now(UTC),
        )
    assert owner.get(base + "/findings").json()["undo_available"] == 0
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(ReviewUndoEntry)
                .where(ReviewUndoEntry.document_id == version.document_id)
            )
            == 0
        )


def test_undo_entry_expiration_does_not_extend_on_reload(intake_site):
    owner, _, engine, _, headers, base, added = setup_review(intake_site)
    with Session(engine) as session, session.begin():
        entry = session.scalar(
            select(ReviewUndoEntry).where(
                ReviewUndoEntry.document_id == UUID(added["version"]["document_id"])
            )
        )
        entry.created_at = datetime.now(UTC) - timedelta(hours=1, seconds=1)
    assert owner.get(base + "/findings").json()["undo_available"] == 0
    response = owner.post(
        base + "/review/undo", json={"expected": added["version"]}, headers=headers
    )
    assert response.status_code == 422 and response.json()["code"] == "nothing_to_undo"


def test_large_group_diffs_restore_1000_suggestions_and_200_manual_findings(intake_site):
    owner, _, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    token = "bulk@example.test"
    manual_token = "fixture"
    source = " / ".join([token] * 1000 + [manual_token] * 200)
    version = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace, source=source, categories=["email"]),
        headers=headers,
    ).json()["version"]
    base = f"/api/v1/documents/{version['document_id']}"
    scan = owner.post(base + "/scan", json={"expected": version}, headers=headers)
    assert scan.status_code == 200, scan.text
    assert len(scan.json()["suggestions"]) == 1000
    version = scan.json()["version"]
    document, revision, group = (
        UUID(version["document_id"]),
        UUID(version["source_revision_id"]),
        uuid4(),
    )
    with Session(engine) as session, session.begin():
        session.add(
            EntityGroup(
                id=group,
                document_id=document,
                source_revision_id=revision,
                category="email",
                label="EMAIL_1",
            )
        )
        session.flush()
        for row in session.scalars(select(Finding).where(Finding.document_id == document)):
            row.group_id = group
        session.add_all(
            [
                Finding(
                    id=uuid4(),
                    document_id=document,
                    source_revision_id=revision,
                    group_id=group,
                    category="email",
                    origin="manual",
                    start_offset=1000 * (len(token) + 3) + i * (len(manual_token) + 3),
                    end_offset=1000 * (len(token) + 3)
                    + i * (len(manual_token) + 3)
                    + len(manual_token),
                )
                for i in range(200)
            ]
        )
    before = owner.get(base + "/findings").json()["findings"]
    ids = [row["finding_id"] for row in before]
    assert len(before) == 1200
    decided = owner.post(
        base + f"/findings/{ids[0]}/decision",
        json={
            "expected": version,
            "action": "redact",
            "group_scope": True,
            "affected_finding_ids": ids,
        },
        headers=headers,
    )
    assert decided.status_code == 200, decided.text
    assert all(row["action"] == "redact" for row in decided.json()["findings"])
    split = owner.post(
        base + f"/findings/{ids[0]}/split",
        json={"expected": decided.json()["version"]},
        headers=headers,
    )
    assert split.status_code == 200
    merged = owner.post(
        base + f"/findings/{ids[0]}/merge",
        json={
            "expected": split.json()["version"],
            "target_finding_id": ids[1],
        },
        headers=headers,
    )
    assert merged.status_code == 200 and merged.json()["undo_available"] == 3
    with Session(engine) as session:
        payloads = session.scalars(
            select(ReviewUndoEntry.payload_bytes).where(ReviewUndoEntry.document_id == document)
        ).all()
    assert len(payloads) == 3 and max(payloads) < 512 * 1024
    print(f"Largest 1200-finding undo diff: {max(payloads)} bytes")
    current = merged.json()
    for count in (2, 1, 0):
        result = owner.post(
            base + "/review/undo", json={"expected": current["version"]}, headers=headers
        )
        assert result.status_code == 200 and result.json()["undo_available"] == count
        assert (
            result.json()["version"]["decision_version"]
            == current["version"]["decision_version"] + 1
        )
        current = result.json()
    assert current["findings"] == before


def test_only_latest_twenty_edits_are_replayable(intake_site):
    owner, _, engine, _, headers, base, added = setup_review(intake_site)
    current, finding = added, added["findings"][0]["finding_id"]
    for index in range(25):
        response = owner.post(
            base + f"/findings/{finding}/decision",
            json={
                "expected": current["version"],
                "action": "redact" if index % 2 else "label",
                "group_scope": False,
                "affected_finding_ids": [finding],
            },
            headers=headers,
        )
        assert response.status_code == 200
        current = response.json()
    assert current["undo_available"] == 20
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(ReviewUndoEntry)
                .where(ReviewUndoEntry.document_id == UUID(current["version"]["document_id"]))
            )
            == 20
        )
    for count in range(19, -1, -1):
        response = owner.post(
            base + "/review/undo", json={"expected": current["version"]}, headers=headers
        )
        assert response.status_code == 200 and response.json()["undo_available"] == count
        current = response.json()
    assert current["findings"][0]["action"] == "label"
    assert (
        owner.post(
            base + "/review/undo", json={"expected": current["version"]}, headers=headers
        ).status_code
        == 422
    )


def test_another_reviewers_edit_cannot_be_undone_by_the_owner(intake_site):
    owner, reviewer, engine, actor, headers, base, added = setup_review(intake_site)
    rh = _login(reviewer, "intake-other@example.invalid")
    reviewer_id = reviewer.get("/api/v1/auth/session").json()["user_id"]
    granted = owner.put(
        base + "/handoff",
        headers=headers,
        json={
            "expected": added["version"],
            "reviewer_id": reviewer_id,
            "require_approval": False,
        },
    )
    assert granted.status_code == 200
    finding = added["findings"][0]["finding_id"]
    current = granted.json()["version"]
    for client, request_headers, action in ((owner, headers, "redact"), (reviewer, rh, "label")):
        response = client.post(
            base + f"/findings/{finding}/decision",
            headers=request_headers,
            json={
                "expected": current,
                "action": action,
                "group_scope": False,
                "affected_finding_ids": [finding],
            },
        )
        assert response.status_code == 200
        current = response.json()["version"]
    assert owner.get(base + "/findings").json()["undo_available"] == 0
    assert reviewer.get(base + "/findings").json()["undo_available"] == 1
    blocked = owner.post(base + "/review/undo", json={"expected": current}, headers=headers)
    assert blocked.status_code == 422 and blocked.json()["code"] == "undo_unavailable"
    response = owner.post(
        base + f"/findings/{finding}/decision",
        headers=headers,
        json={
            "expected": current,
            "action": "redact",
            "group_scope": False,
            "affected_finding_ids": [finding],
        },
    )
    assert response.status_code == 200 and response.json()["undo_available"] == 1
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(ReviewUndoEntry)
                .where(
                    ReviewUndoEntry.document_id == UUID(current["document_id"]),
                    ReviewUndoEntry.actor_id == actor,
                )
            )
            == 1
        )
    undone = owner.post(
        base + "/review/undo", headers=headers, json={"expected": response.json()["version"]}
    )
    assert undone.status_code == 200 and undone.json()["findings"][0]["action"] == "label"


def test_cleanup_prunes_expired_budgets_and_deleted_document_history(intake_site):
    owner, _, engine, _, headers, base, added = setup_review(intake_site)
    now = datetime.now(UTC)
    old, fresh = uuid4(), uuid4()
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                AttemptEvent(
                    id=old,
                    scope="cleanup-test",
                    subject_hmac=b"o" * 32,
                    attempted_at=now - timedelta(days=1, seconds=1),
                ),
                AttemptEvent(
                    id=fresh, scope="cleanup-test", subject_hmac=b"f" * 32, attempted_at=now
                ),
            ]
        )
    assert owner.delete(base, headers=headers).status_code == 200
    assert owner.get(base + "/findings").status_code == 410
    assert purge_unavailable_content(engine, now=now).documents_purged == 0
    with Session(engine) as session, session.begin():
        assert session.get(AttemptEvent, old) is None
        assert session.get(AttemptEvent, fresh) is not None
        assert (
            session.scalar(
                select(func.count())
                .select_from(ReviewUndoEntry)
                .where(ReviewUndoEntry.document_id == UUID(added["version"]["document_id"]))
            )
            == 0
        )
        session.delete(session.get(AttemptEvent, fresh))
