"""Working-copy content and deletion stop when access ends during a request."""

from datetime import UTC, datetime, timedelta
from time import sleep
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.models import Document, Membership, Workspace
from app.db.recovery import RecoverySnapshot
from tests.intake_support import _draft_body, _login
from tests.test_autosave_pg import body, path
from tests.test_content_read_access_pg import change_actor

PRIVATE = "Fictional working-copy canary nora@example.test"
CHANGES = ("revoked", "expired", "disabled", "membership")


@pytest.fixture
def working_copy(intake_site):
    owner, _, engine, workspace, actor = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    draft = owner.post(
        "/api/v1/documents", json=_draft_body(workspace), headers=headers
    ).json()
    snapshot, additional = uuid4(), uuid4()
    payload = body(document=draft["version"]["document_id"], base=draft["version"], source=PRIVATE)
    assert owner.put(path(workspace, snapshot), json=payload, headers=headers).status_code == 200
    with Session(engine) as session, session.begin():
        session.add(Workspace(id=additional, name="Other active workspace"))
        session.flush()
        session.add(Membership(workspace_id=additional, user_id=actor, role="member"))
    case = {"client": owner, "engine": engine, "workspace": workspace, "actor": actor,
            "headers": headers, "snapshot": snapshot, "payload": payload,
            "document": UUID(draft["version"]["document_id"])}
    try:
        yield case
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(Membership).where(Membership.workspace_id == additional))
            session.execute(delete(Workspace).where(Workspace.id == additional))


def interrupt(monkeypatch, module, name, case, change):
    original = getattr(module, name)
    fired = []

    def changed(*args, **kwargs):
        value = original(*args, **kwargs)
        if not fired:
            fired.append(True)
            change_actor(case, change)
        return value

    monkeypatch.setattr(module, name, changed)
    return fired


@pytest.mark.parametrize("change", CHANGES)
def test_working_copy_read_rechecks_access_after_decryption(working_copy, monkeypatch, change):
    from app.recovery import api

    case = working_copy
    fired = interrupt(monkeypatch, api, "load_snapshot", case, change)
    response = case["client"].get(path(case["workspace"], case["snapshot"]))
    assert fired
    assert response.status_code == (404 if change == "membership" else 401)
    assert PRIVATE not in response.text and "payload" not in response.json()
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("operation", ["save", "discard"])
@pytest.mark.parametrize("change", CHANGES)
def test_working_copy_changes_roll_back_when_access_ends(working_copy, monkeypatch, operation, change):
    from app.recovery import api

    case = working_copy
    with Session(case["engine"]) as session:
        row = session.get(RecoverySnapshot, case["snapshot"])
        before = row.version, row.payload_ciphertext
    fired = interrupt(
        monkeypatch, api, "save_snapshot" if operation == "save" else "owned_snapshot", case, change
    )
    if operation == "save":
        response = case["client"].put(
            path(case["workspace"], case["snapshot"]), headers=case["headers"],
            json={**case["payload"], "expected_version": 1,
                  "payload": {**case["payload"]["payload"], "source": "Changed after access ended"}},
        )
    else:
        response = case["client"].delete(
            path(case["workspace"], case["snapshot"]) + "?expected_version=1",
            headers=case["headers"],
        )
    assert fired
    assert response.status_code == (404 if change == "membership" else 401)
    with Session(case["engine"]) as session:
        row = session.get(RecoverySnapshot, case["snapshot"])
        assert row is not None and (row.version, row.payload_ciphertext) == before


@pytest.mark.parametrize("change", CHANGES)
def test_document_delete_rechecks_access_after_its_row_lock(working_copy, monkeypatch, change):
    from app.cleanup import service

    case = working_copy
    fired = interrupt(monkeypatch, service, "owned_document_record", case, change)
    response = case["client"].delete(
        f"/api/v1/documents/{case['document']}", headers=case["headers"]
    )
    assert fired
    assert response.status_code == (404 if change == "membership" else 401)
    with Session(case["engine"]) as session:
        document = session.get(Document, case["document"])
        assert document.deleted_at is None and document.current_revision_id is not None
        assert session.get(RecoverySnapshot, case["snapshot"]) is not None


def test_working_copy_expiry_is_checked_after_content_is_serialized(working_copy, monkeypatch):
    from app.recovery.contracts import RecoveryView

    case = working_copy
    original = RecoveryView.model_dump_json
    with Session(case["engine"]) as session, session.begin():
        session.get(RecoverySnapshot, case["snapshot"]).expires_at = (
            datetime.now(UTC) + timedelta(seconds=0.2)
        )

    def expired(view, *args, **kwargs):
        payload = original(view, *args, **kwargs)
        sleep(0.3)
        return payload

    monkeypatch.setattr(RecoveryView, "model_dump_json", expired)
    response = case["client"].get(path(case["workspace"], case["snapshot"]))
    assert response.status_code == 410 and PRIVATE not in response.text


def test_document_expiry_during_decryption_cannot_use_cached_scope(working_copy, monkeypatch):
    from app.recovery import api

    case = working_copy
    original = api.load_snapshot

    def expired(*args, **kwargs):
        view = original(*args, **kwargs)
        with Session(case["engine"]) as session, session.begin():
            session.get(Document, case["document"]).expires_at = datetime.now(UTC)
        return view

    monkeypatch.setattr(api, "load_snapshot", expired)
    response = case["client"].get(path(case["workspace"], case["snapshot"]))
    assert response.status_code == 410 and PRIVATE not in response.text
