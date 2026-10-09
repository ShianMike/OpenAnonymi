"""Paste, file, and revision workflow on an explicit local PostgreSQL database."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cleanup.service import purge_unavailable_content
from app.db.models import (
    AuditEvent,
    Document,
    Finding,
    Membership,
    SourceRevision,
)
from tests.intake_support import _draft_body, _login


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
            is None
        )
    purged = purge_unavailable_content(engine, now=datetime.now(UTC))
    assert purged.documents_purged == 0
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
