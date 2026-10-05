"""Actual title isolation, persisted flags, partial outcomes and access races."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.crypto import KeyRing
from app.db.document_preferences import DocumentPreference
from app.db.models import Document, Membership, SourceRevision, User, Workspace
from app.db.models import Session as StoredSession
from app.db.team_review import ReviewHandoff
from tests.intake_support import _draft_body, _login


def draft(client, headers, workspace_id, title):
    response = client.post(
        "/api/v1/documents", json=_draft_body(workspace_id, title=title), headers=headers
    )
    assert response.status_code == 201
    return response.json()["version"]["document_id"]


@pytest.mark.parametrize("endpoint", ["index", "search"])
@pytest.mark.parametrize("change", ["membership", "disabled_user", "expiry", "handoff", "session"])
def test_document_index_does_not_return_titles_after_late_access_change(
    intake_site, monkeypatch, change, endpoint
):
    owner, other, engine, workspace_id, owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    document_id = draft(owner, headers, workspace_id, "PRIVATE TITLE CANARY")
    reader = owner
    if change == "handoff":
        headers = _login(other, "intake-other@example.invalid")
        with Session(engine) as session, session.begin():
            other_id = session.scalar(
                select(User.id).where(User.email == "intake-other@example.invalid")
            )
            session.add(
                ReviewHandoff(document_id=UUID(document_id), reviewer_id=other_id, generation=1)
            )
        reader = other
    decrypt = KeyRing.decrypt_text
    changed = False

    def decrypt_then_change(self, value):
        nonlocal changed
        text = decrypt(self, value)
        if not changed:
            changed = True
            with Session(engine) as session, session.begin():
                if change == "membership":
                    session.get(Membership, (workspace_id, owner_id)).revoked_at = datetime.now(UTC)
                elif change == "disabled_user":
                    session.get(User, owner_id).disabled_at = datetime.now(UTC)
                elif change == "expiry":
                    document = session.get(Document, UUID(document_id))
                    document.created_at = datetime.now(UTC) - timedelta(days=2)
                    document.expires_at = datetime.now(UTC) - timedelta(days=1)
                elif change == "session":
                    for stored in session.scalars(
                        select(StoredSession).where(StoredSession.user_id == owner_id)
                    ):
                        stored.revoked_at = datetime.now(UTC)
                else:
                    session.execute(
                        delete(ReviewHandoff).where(ReviewHandoff.document_id == UUID(document_id))
                    )
        return text

    monkeypatch.setattr(KeyRing, "decrypt_text", decrypt_then_change)
    result = (
        reader.get(f"/api/v1/workspaces/{workspace_id}/documents")
        if endpoint == "index"
        else reader.post("/api/v1/search/documents", json={"query": "PRIVATE"}, headers=headers)
    )
    assert changed
    assert "PRIVATE TITLE CANARY" not in result.text
    if change == "expiry" and endpoint == "index":
        # The final serialized-response check detects the independently changed
        # creation/expiry metadata, rather than releasing the earlier index body.
        assert result.status_code == 409
        assert result.json()["code"] == "documents_changed"
    else:
        assert result.status_code in (200, 401, 404)
    assert result.headers["cache-control"] == "no-store"


def test_global_search_scopes_titles_and_personal_flags_to_real_grants(intake_site):
    owner, other, engine, workspace_id, owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    other_headers = _login(other, "intake-other@example.invalid")
    own_id = draft(owner, headers, workspace_id, "Fictional café 😀 Owner")
    other_id = draft(other, other_headers, workspace_id, "Fictional Other private")
    with Session(engine) as session, session.begin():
        session.get(Membership, (workspace_id, owner_id)).role = "administrator"
    search = lambda client, auth, **body: client.post(
        "/api/v1/search/documents", json=body, headers=auth
    )
    result = search(owner, headers, query="FICTIONAL")
    assert result.status_code == 200
    assert result.headers["Cache-Control"] == "no-store"
    assert [item["id"] for item in result.json()["items"]] == [own_id]
    assert "Other private" not in result.text and "Synthetic owner" not in result.text
    assert search(owner, headers, query="café 😀").json()["items"][0]["id"] == own_id
    assert search(owner, headers, query="cafe").json()["items"] == []
    assert search(owner, headers, workspace_id=str(uuid4())).status_code == 404
    assert (
        owner.patch(
            f"/api/v1/documents/{other_id}/preferences", json={"favorite": True}, headers=headers
        ).status_code
        == 404
    )
    assert owner.patch(
        f"/api/v1/documents/{own_id}/preferences", json={"favorite": True}, headers=headers
    ).json()["favorite"]
    assert search(owner, headers, favorites_only=True).json()["items"][0]["id"] == own_id
    assert search(other, other_headers, favorites_only=True).json()["items"] == []
    assert owner.patch(
        f"/api/v1/documents/{own_id}/preferences", json={"pinned": True}, headers=headers
    ).json() == {
        "document_id": own_id,
        "favorite": True,
        "pinned": True,
    }
    # Sign in anew; preferences live in Postgres and do not depend on this tab/session.
    headers = _login(owner, "intake-owner@example.invalid")
    index = owner.get(f"/api/v1/workspaces/{workspace_id}/documents").json()
    assert index[0]["favorite"] and index[0]["pinned"]
    with Session(engine) as session, session.begin():
        session.add(
            ReviewHandoff(
                document_id=UUID(own_id),
                reviewer_id=session.scalar(
                    select(User.id).where(User.email == "intake-other@example.invalid")
                ),
                generation=1,
            )
        )
    assigned = search(other, other_headers, query="Owner").json()["items"]
    assert len(assigned) == 1 and not assigned[0]["is_owner"] and not assigned[0]["favorite"]
    assert (
        other.patch(
            f"/api/v1/documents/{own_id}/preferences",
            json={"favorite": True},
            headers=other_headers,
        ).status_code
        == 200
    )
    assert (
        other.post(
            f"/api/v1/workspaces/{workspace_id}/documents/bulk",
            json={"action": "delete", "document_ids": [own_id]},
            headers=other_headers,
        ).json()["outcomes"][0]["outcome"]
        == "not_found"
    )
    with Session(engine) as session, session.begin():
        session.execute(delete(ReviewHandoff).where(ReviewHandoff.document_id == UUID(own_id)))
    assert search(other, other_headers, favorites_only=True).json()["items"] == []
    assert owner.get(f"/api/v1/documents/{own_id}/source").status_code == 200


def test_search_bounded_keyset_pages_cover_large_encrypted_index(intake_site):
    owner, _other, engine, workspace_id, owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    keys = KeyRing.from_settings(owner.app.state.settings)
    now = datetime.now(UTC)
    wanted_id = uuid4()
    with Session(engine) as session, session.begin():
        for index in range(501):
            value = keys.encrypt_text(
                "Oldest matching title" if index == 500 else "Ordinary encrypted title"
            )
            session.add(
                Document(
                    id=wanted_id if index == 500 else uuid4(),
                    workspace_id=workspace_id,
                    owner_id=owner_id,
                    title_ciphertext=value.ciphertext,
                    title_key_id=value.key_id,
                    created_at=now - timedelta(seconds=index),
                    expires_at=now + timedelta(days=1),
                )
            )
    path, body = "/api/v1/search/documents", {"query": "matching"}
    first = owner.post(path, json=body, headers=headers).json()
    assert first["items"] == [] and first["scanned_count"] == 500 and first["next_cursor"]
    second = owner.post(path, json={**body, "cursor": first["next_cursor"]}, headers=headers).json()
    assert [row["id"] for row in second["items"]] == [str(wanted_id)]
    assert second["scanned_count"] == 1 and second["next_cursor"] is None
    all_ids, cursor = [], None
    for _ in range(11):
        value = owner.post(path, json={"limit": 50, "cursor": cursor}, headers=headers).json()
        all_ids.extend(item["id"] for item in value["items"])
        cursor = value["next_cursor"]
        if cursor is None:
            break
    assert len(set(all_ids)) == len(all_ids) == 501


def test_bulk_independent_outcomes_and_actual_content_removal(intake_site):
    owner, other, engine, workspace_id, owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    other_headers = _login(other, "intake-other@example.invalid")
    own_id = draft(owner, headers, workspace_id, "Bulk owner")
    other_id = draft(other, other_headers, workspace_id, "Bulk foreign")
    expired_id = draft(owner, headers, workspace_id, "Bulk expired")
    missing_id = str(uuid4())
    with Session(engine) as session, session.begin():
        row = session.get(Document, UUID(expired_id))
        row.created_at, row.expires_at = (
            datetime.now(UTC) - timedelta(days=2),
            datetime.now(UTC) - timedelta(days=1),
        )
    path = f"/api/v1/workspaces/{workspace_id}/documents/bulk"
    ids = [own_id, other_id, missing_id, expired_id]
    response = owner.post(path, json={"document_ids": ids, "action": "favorite"}, headers=headers)
    assert response.status_code == 200
    assert [item["outcome"] for item in response.json()["outcomes"]] == [
        "updated",
        "not_found",
        "not_found",
        "unavailable",
    ]
    assert [item["document_id"] for item in response.json()["outcomes"]] == ids
    for action, favorite, pinned in [
        ("pin", True, True),
        ("unfavorite", False, True),
        ("unpin", False, False),
    ]:
        row = owner.post(
            path, json={"document_ids": [own_id], "action": action}, headers=headers
        ).json()["outcomes"][0]
        assert (
            row["outcome"] == "updated" and row["favorite"] == favorite and row["pinned"] == pinned
        )
    with Session(engine) as session:
        assert session.get(DocumentPreference, (owner_id, UUID(own_id))) is None
    removed = owner.post(
        path, json={"document_ids": ids, "action": "delete"}, headers=headers
    ).json()
    assert [item["outcome"] for item in removed["outcomes"]] == [
        "deleted",
        "not_found",
        "not_found",
        "deleted",
    ]
    assert owner.get(f"/api/v1/documents/{own_id}/source").status_code == 410
    assert other.get(f"/api/v1/documents/{other_id}/source").status_code == 200
    with Session(engine) as session:
        assert (
            session.scalar(
                select(SourceRevision).where(
                    SourceRevision.document_id.in_([UUID(own_id), UUID(expired_id)])
                )
            )
            is None
        )


@pytest.mark.parametrize(
    "path,body",
    [
        ("/search/documents", {"query": "Title"}),
        ("/documents/{id}/preferences", {"favorite": True}),
        (
            "/workspaces/{workspace}/documents/bulk",
            {"action": "favorite", "document_ids": ["{id}"]},
        ),
    ],
)
def test_organization_requires_session_csrf_and_exact_origin(intake_site, path, body):
    owner, other, _engine, workspace_id, _owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    doc_id = draft(owner, headers, workspace_id, "CSRF title")
    path = "/api/v1" + path.format(id=doc_id, workspace=workspace_id)
    body = {key: ([doc_id] if isinstance(value, list) else value) for key, value in body.items()}
    method = "patch" if "preferences" in path else "post"
    assert getattr(other, method)(path, json=body, headers=headers).status_code == 401
    assert (
        getattr(owner, method)(path, json=body, headers={"Origin": headers["Origin"]}).status_code
        == 403
    )
    assert (
        getattr(owner, method)(
            path, json=body, headers={**headers, "Origin": "https://evil.example"}
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "body",
    [
        {"query": "PRIVATE" * 20},
        {"limit": 51},
        {"limit": 0},
        {"favorites_only": "true"},
        {"cursor": {"created_at": "2026-01-01T00:00:00", "id": str(uuid4())}},
        {"source": "PRIVATE"},
    ],
)
def test_search_input_is_bounded_and_errors_do_not_echo_terms(intake_site, body):
    owner, _other, _engine, _workspace, _owner = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    response = owner.post("/api/v1/search/documents", json=body, headers=headers)
    assert response.status_code == 422 and "PRIVATE" not in response.text


def test_bulk_rejects_duplicates_oversize_and_action_bypass(intake_site):
    owner, _other, _engine, workspace, _owner = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    doc_id = draft(owner, headers, workspace, "Validation review")
    path = f"/api/v1/workspaces/{workspace}/documents/bulk"
    for body in (
        {"document_ids": [doc_id, doc_id], "action": "delete"},
        {"document_ids": [str(uuid4()) for _ in range(51)], "action": "favorite"},
        {"document_ids": [doc_id], "action": "confirm"},
        {"document_ids": [doc_id], "action": "export"},
    ):
        assert owner.post(path, json=body, headers=headers).status_code == 422
    for body in ({}, {"favorite": "false"}, {"favorite": True, "actor_id": str(uuid4())}):
        assert (
            owner.patch(
                f"/api/v1/documents/{doc_id}/preferences", json=body, headers=headers
            ).status_code
            == 422
        )
    assert owner.get(f"/api/v1/documents/{doc_id}/source").status_code == 200


def test_bulk_stops_when_session_is_revoked_between_items(intake_site, monkeypatch):
    from app.workspace import organize_api

    owner, _other, engine, workspace, owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    ids = [draft(owner, headers, workspace, "Session review") for _ in range(3)]
    original = organize_api.update_preference

    def update_then_revoke(*args, **kwargs):
        result = original(*args, **kwargs)
        with Session(engine) as session, session.begin():
            for stored in session.scalars(
                select(StoredSession).where(StoredSession.user_id == owner_id)
            ):
                stored.revoked_at = datetime.now(UTC)
        return result

    monkeypatch.setattr(organize_api, "update_preference", update_then_revoke)
    response = owner.post(
        f"/api/v1/workspaces/{workspace}/documents/bulk",
        json={"document_ids": ids, "action": "favorite"},
        headers=headers,
    )
    assert [item["outcome"] for item in response.json()["outcomes"]] == [
        "updated",
        "session_ended",
        "session_ended",
    ]
    with Session(engine) as session:
        assert [
            str(row.document_id)
            for row in session.scalars(
                select(DocumentPreference).where(DocumentPreference.actor_id == owner_id)
            )
        ] == ids[:1]


def test_bulk_cannot_act_on_owned_document_in_a_different_workspace(intake_site):
    owner, _other, engine, workspace, owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    alternate = uuid4()
    try:
        with Session(engine) as session, session.begin():
            session.add(Workspace(id=alternate, name="Different scope"))
            session.flush()
            session.add(Membership(workspace_id=alternate, user_id=owner_id, role="member"))
        document_id = draft(owner, headers, alternate, "Other workspace title")
        for action in ("favorite", "delete"):
            response = owner.post(
                f"/api/v1/workspaces/{workspace}/documents/bulk",
                json={"action": action, "document_ids": [document_id]},
                headers=headers,
            )
            assert response.json()["outcomes"][0]["outcome"] == "not_found"
        assert owner.get(f"/api/v1/documents/{document_id}/source").status_code == 200
        with Session(engine) as session:
            assert session.get(DocumentPreference, (owner_id, UUID(document_id))) is None
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(Document).where(Document.workspace_id == alternate))
            session.execute(delete(Membership).where(Membership.workspace_id == alternate))
            session.execute(delete(Workspace).where(Workspace.id == alternate))


@pytest.mark.parametrize("change", ["membership", "session", "disabled"])
def test_preference_rechecks_access_before_commit_and_rolls_back(intake_site, monkeypatch, change):
    from app.workspace import organize_api

    owner, _other, engine, workspace, owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    document_id = draft(owner, headers, workspace, "Race review")
    original = organize_api.update_preference

    def alter_before_commit(*args, **kwargs):
        authorize = kwargs["authorize"]

        def change_then_authorize():
            with Session(engine) as session, session.begin():
                if change == "membership":
                    session.get(Membership, (workspace, owner_id)).revoked_at = datetime.now(UTC)
                elif change == "disabled":
                    session.get(User, owner_id).disabled_at = datetime.now(UTC)
                else:
                    for stored in session.scalars(
                        select(StoredSession).where(StoredSession.user_id == owner_id)
                    ):
                        stored.revoked_at = datetime.now(UTC)
            authorize()

        return original(*args, **{**kwargs, "authorize": change_then_authorize})

    monkeypatch.setattr(organize_api, "update_preference", alter_before_commit)
    response = owner.patch(
        f"/api/v1/documents/{document_id}/preferences", json={"favorite": True}, headers=headers
    )
    assert response.status_code == 401
    with Session(engine) as session:
        assert session.get(DocumentPreference, (owner_id, UUID(document_id))) is None


def test_search_limit_survives_independent_application_and_never_stores_terms(intake_site, caplog):
    import logging

    from fastapi.testclient import TestClient

    from app.accounts.limits import AttemptLimiter
    from app.db.durable import AttemptEvent
    from app.factory import create_app

    owner, _other, engine, _workspace, owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    settings = owner.app.state.settings
    limiter = AttemptLimiter(
        engine,
        settings,
        scope="document_search",
        maximum=60,
        window_seconds=60,
        network_scope=False,
    )
    with caplog.at_level(logging.INFO):
        response = owner.post(
            "/api/v1/search/documents", json={"query": "SECRET QUERY CANARY"}, headers=headers
        )
        assert response.status_code == 200
    assert "SECRET QUERY CANARY" not in caplog.text
    for _ in range(59):
        assert limiter.take(str(owner_id))
    with TestClient(create_app(settings, engine=engine)) as restarted:
        restarted.cookies.update(owner.cookies)
        assert (
            restarted.post("/api/v1/search/documents", json={}, headers=headers).status_code == 429
        )
    with Session(engine) as session:
        stored = session.scalars(
            select(AttemptEvent).where(AttemptEvent.scope == "document_search")
        ).all()
        assert stored and all(len(row.subject_hmac) == 32 for row in stored)
