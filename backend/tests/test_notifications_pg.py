"""Real notification triggers, access rechecks and lifecycle on PostgreSQL."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.accounts.memberships import restore_member, revoke_member
from app.cleanup.service import purge_unavailable_content
from app.db.crypto import KeyRing
from app.db.models import Document, Membership, User, Workspace
from app.db.notifications import EVENT_CODES, Notification
from app.notifications.service import list_notifications, notify, unread_count
from tests.intake_support import _draft_body, _login
from tests.test_team_review_pg import _decision

TITLE = "NOTIFICATION_PRIVATE_TITLE_b65b9"
SOURCE = "NOTIFICATION_PRIVATE_SOURCE_b65b9 nora@example.com"
COMMENT = "NOTIFICATION_PRIVATE_COMMENT_b65b9"
WORKSPACE = "NOTIFICATION_PRIVATE_WORKSPACE_b65b9"


def start_review(site):
    owner, reviewer, engine, workspace, owner_id = site
    headers = _login(owner, "intake-owner@example.invalid")
    rh = _login(reviewer, "intake-other@example.invalid")
    reviewer_id = UUID(reviewer.get("/api/v1/auth/session").json()["user_id"])
    with Session(engine) as session, session.begin():
        session.get(Workspace, workspace).name = WORKSPACE
        for user in (owner_id, reviewer_id):
            session.get(Membership, (workspace, user)).role = "administrator"
    draft = owner.post(
        "/api/v1/documents",
        headers=headers,
        json=_draft_body(workspace, source=SOURCE, title=TITLE, categories=["email"]),
    )
    assert draft.status_code == 201
    version = draft.json()["version"]
    base = f"/api/v1/documents/{version['document_id']}"
    scan = owner.post(base + "/scan", json={"expected": version}, headers=headers)
    assert scan.status_code == 200
    return {
        "owner": owner,
        "reviewer": reviewer,
        "engine": engine,
        "workspace": workspace,
        "owner_id": owner_id,
        "reviewer_id": reviewer_id,
        "headers": headers,
        "rh": rh,
        "base": base,
        "version": scan.json()["version"],
        "finding": scan.json()["suggestions"][0]["finding_id"],
    }


def assign(case, reviewer_id="current"):
    selected = case["reviewer_id"] if reviewer_id == "current" else reviewer_id
    result = case["owner"].put(
        case["base"] + "/handoff",
        headers=case["headers"],
        json={
            "expected": case["version"],
            "reviewer_id": str(selected) if selected else None,
            "require_approval": True,
        },
    )
    assert result.status_code == 200
    case["version"] = result.json()["version"]
    return result


def confirmed_review(case, *, approved=False):
    assign(case)
    case["version"] = _decision(
        case["owner"], case["base"], case["finding"], case["version"], case["headers"]
    )
    result = case["owner"].post(
        case["base"] + "/complete",
        headers=case["headers"],
        json={"expected": case["version"], "confirmed_preview": True},
    )
    assert result.status_code == 200
    if approved:
        result = case["reviewer"].post(
            case["base"] + "/approval",
            headers=case["rh"],
            json={"expected": case["version"], "confirmed_preview": True},
        )
        assert result.status_code == 200


def stored(case):
    with Session(case["engine"]) as session:
        return session.scalars(
            select(Notification).where(
                Notification.document_id == UUID(case["version"]["document_id"])
            )
        ).all()


def inbox(client, **params):
    result = client.get("/api/v1/notifications", params=params)
    assert result.status_code == 200
    return result.json()


def test_all_six_real_events_are_content_free_and_repeated_actions_are_idempotent(intake_site):
    case = start_review(intake_site)
    confirmed_review(case, approved=True)
    assign(case)  # current handoff: no new assignment or invalidation
    body = {"expected": case["version"], "confirmed_preview": True}
    assert (
        case["owner"]
        .post(case["base"] + "/complete", headers=case["headers"], json=body)
        .status_code
        == 200
    )
    assert (
        case["reviewer"].post(case["base"] + "/approval", headers=case["rh"], json=body).status_code
        == 200
    )
    case["version"] = _decision(
        case["owner"],
        case["base"],
        case["finding"],
        case["version"],
        case["headers"],
        action="keep",
    )
    comment = {"id": str(uuid4()), "expected": case["version"], "text": COMMENT}
    path = case["base"] + f"/findings/{case['finding']}/comments"
    for _ in range(2):
        assert case["reviewer"].post(path, json=comment, headers=case["rh"]).status_code == 201
    assign(case, None)
    rows = stored(case)
    assert sorted(row.event_code for row in rows) == sorted(EVENT_CODES)
    assert {column.name for column in Notification.__table__.columns} == {
        "id",
        "workspace_id",
        "recipient_id",
        "document_id",
        "actor_id",
        "event_code",
        "created_at",
        "read_at",
        "email_status",
        "email_attempted_at",
        "email_requested",
    }
    serialized = repr(
        [
            {column.name: getattr(row, column.name) for column in Notification.__table__.columns}
            for row in rows
        ]
    )
    assert all(sentinel not in serialized for sentinel in (TITLE, SOURCE, COMMENT, WORKSPACE))
    assert all(not row.email_requested and row.email_status == "not_requested" for row in rows)
    reviewer_codes = {item["event_code"] for item in inbox(case["reviewer"])["items"]}
    assert reviewer_codes == {
        "review_assigned",
        "approval_requested",
        "approval_invalidated",
        "review_unassigned",
    }
    assert {item["event_code"] for item in inbox(case["owner"])["items"]} == {
        "review_approved",
        "comment_added",
    }


@pytest.mark.parametrize("approved", [False, True], ids=["requested", "approved"])
@pytest.mark.parametrize("mutation", ["decision", "settings", "source", "undo"])
def test_each_version_change_invalidates_an_exact_request_or_approval_once(
    intake_site, approved, mutation
):
    case = start_review(intake_site)
    confirmed_review(case, approved=approved)
    owner, base, version, headers = (case[key] for key in ("owner", "base", "version", "headers"))
    if mutation == "decision":
        case["version"] = _decision(owner, base, case["finding"], version, headers, action="keep")
        result = None
    elif mutation == "settings":
        result = owner.put(
            base + "/scan-settings",
            json={"expected": version, "categories": ["email"], "phone_region": "US"},
            headers=headers,
        )
    elif mutation == "source":
        result = owner.put(
            base + "/source",
            json={"expected": version, "source": SOURCE + " revised"},
            headers=headers,
        )
    else:
        result = owner.post(base + "/review/undo", json={"expected": version}, headers=headers)
    if result is not None:
        assert result.status_code == 200
        case["version"] = result.json().get("version", result.json())
    assert [row.event_code for row in stored(case)].count("approval_invalidated") == 1
    assert (
        owner.post(
            base + "/exports/txt",
            json={"expected": case["version"], "event_id": str(uuid4())},
            headers=headers,
        ).status_code
        == 409
    )
    # A later edit of a version nobody has been asked to approve is not another invalidation.
    later = owner.put(
        base + "/source",
        json={"expected": case["version"], "source": SOURCE + " another revision"},
        headers=headers,
    )
    assert later.status_code == 200
    assert [row.event_code for row in stored(case)].count("approval_invalidated") == 1


def test_title_requires_current_grant_even_for_administrator_and_open_rechecks(intake_site):
    case = start_review(intake_site)
    reviewer = case["reviewer"]
    assert inbox(reviewer)["items"] == []
    assert reviewer.get(case["base"] + "/source").status_code == 404
    assign(case)
    item = inbox(reviewer)["items"][0]
    assert item["document_available"] and item["title"] == TITLE
    assign(case, None)
    assert all(
        not row["document_available"] and row["title"] is None for row in inbox(reviewer)["items"]
    )
    assert reviewer.get(case["base"] + "/source").status_code == 404
    # Opaque notification history may still be acknowledged after document access ends.
    assert (
        reviewer.post(f"/api/v1/notifications/{item['id']}/read", headers=case["rh"]).status_code
        == 204
    )


def test_keyset_pages_unread_counts_and_read_mutations_are_recipient_and_csrf_bound(intake_site):
    case = start_review(intake_site)
    assign(case)
    assign(case, None)
    owner, reviewer = case["owner"], case["reviewer"]
    first = inbox(reviewer, limit=1)
    assert first["next_cursor"] and len(first["items"]) == 1
    second = inbox(reviewer, limit=1, cursor=first["next_cursor"])
    assert second["next_cursor"] is None and len(second["items"]) == 1
    assert first["items"][0]["id"] != second["items"][0]["id"]
    identifier = second["items"][0]["id"]
    assert owner.get("/api/v1/notifications", params={"cursor": identifier}).status_code == 404
    assert (
        owner.post(f"/api/v1/notifications/{identifier}/read", headers=case["headers"]).status_code
        == 404
    )
    assert reviewer.get("/api/v1/notifications", params={"limit": 51}).status_code == 422
    assert reviewer.get("/api/v1/notifications/unread-count").json()["count"] == 2
    for headers in (
        {},
        {"Origin": "https://example.invalid", "X-CSRF-Token": case["rh"]["X-CSRF-Token"]},
    ):
        assert (
            reviewer.post(f"/api/v1/notifications/{identifier}/read", headers=headers).status_code
            == 403
        )
        assert reviewer.post("/api/v1/notifications/read-all", headers=headers).status_code == 403
    for _ in range(2):
        assert (
            reviewer.post(
                f"/api/v1/notifications/{identifier}/read", headers=case["rh"]
            ).status_code
            == 204
        )
    assert reviewer.get("/api/v1/notifications/unread-count").json()["count"] == 1
    assert (
        owner.post("/api/v1/notifications/read-all", headers=case["headers"]).json()["changed"] == 0
    )
    assert (
        reviewer.post("/api/v1/notifications/read-all", headers=case["rh"]).json()["changed"] == 1
    )
    assert (
        reviewer.post("/api/v1/notifications/read-all", headers=case["rh"]).json()["changed"] == 0
    )
    assert reviewer.get("/api/v1/notifications/unread-count").json()["count"] == 0


def test_membership_revocation_hides_history_and_restoration_does_not_restore_title_access(
    intake_site,
):
    case = start_review(intake_site)
    assign(case)
    with Session(case["engine"]) as session:
        revoke_member(
            session,
            workspace_id=case["workspace"],
            actor_id=case["owner_id"],
            user_id=case["reviewer_id"],
            now=datetime.now(UTC),
        )
    keys = KeyRing.from_settings(case["owner"].app.state.settings)
    assert (
        list_notifications(case["engine"], case["reviewer_id"], keys, datetime.now(UTC)).items == []
    )
    assert unread_count(case["engine"], case["reviewer_id"], datetime.now(UTC)) == 0
    assert [row.event_code for row in stored(case)].count("review_unassigned") == 1
    with Session(case["engine"]) as session:
        restore_member(
            session,
            workspace_id=case["workspace"],
            actor_id=case["owner_id"],
            user_id=case["reviewer_id"],
        )
    page = list_notifications(case["engine"], case["reviewer_id"], keys, datetime.now(UTC))
    assert len(page.items) == 2 and all(
        not item.document_available and item.title is None for item in page.items
    )


@pytest.mark.parametrize("unavailable", ["expired", "deleted", "owner_disabled"])
def test_unavailable_document_titles_are_withheld_and_content_purge_removes_events(
    intake_site, unavailable
):
    case = start_review(intake_site)
    assign(case)
    now = datetime.now(UTC)
    with Session(case["engine"]) as session, session.begin():
        document = session.get(Document, UUID(case["version"]["document_id"]))
        if unavailable == "expired":
            document.created_at = now - timedelta(days=5)
            document.expires_at = now - timedelta(days=1)
        elif unavailable == "deleted":
            document.deleted_at = now
        else:
            session.get(User, case["owner_id"]).disabled_at = now
    item = inbox(case["reviewer"])["items"][0]
    assert not item["document_available"] and item["title"] is None
    if unavailable != "owner_disabled":
        purge_unavailable_content(case["engine"], now=now)
        assert stored(case) == []


def test_thirty_day_retention_denies_old_rows_before_cleanup_and_deletes_only_expired(intake_site):
    case = start_review(intake_site)
    assign(case)
    assign(case, None)
    rows = stored(case)
    old_id = rows[0].id
    now = datetime.now(UTC)
    with Session(case["engine"]) as session, session.begin():
        session.get(Notification, old_id).created_at = now - timedelta(days=30, seconds=1)
    assert len(inbox(case["reviewer"])["items"]) == 1
    assert (
        case["reviewer"]
        .post(f"/api/v1/notifications/{old_id}/read", headers=case["rh"])
        .status_code
        == 404
    )
    purge_unavailable_content(case["engine"], now=now)
    assert len(stored(case)) == 1 and stored(case)[0].id != old_id


def test_database_rejection_rolls_back_document_change_and_notification_together(intake_site):
    case = start_review(intake_site)
    document_id = UUID(case["version"]["document_id"])
    with pytest.raises(IntegrityError), Session(case["engine"]) as session, session.begin():
        document = session.get(Document, document_id)
        document.decision_version += 1
        notify(
            session,
            document,
            case["reviewer_id"],
            case["owner_id"],
            "review_assigned",
            datetime.now(UTC),
        )
        session.add(
            Notification(
                id=uuid4(),
                workspace_id=case["workspace"],
                recipient_id=case["reviewer_id"],
                document_id=document_id,
                event_code="not_allowed",
                created_at=datetime.now(UTC),
            )
        )
    with Session(case["engine"]) as session:
        assert (
            session.get(Document, document_id).decision_version
            == case["version"]["decision_version"]
        )
        assert (
            session.scalar(
                select(func.count(Notification.id)).where(Notification.document_id == document_id)
            )
            == 0
        )
