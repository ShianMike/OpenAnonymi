"""Independently committed access loss denies real workspace writes and private JSON."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.custom_rules.contracts import RuleSnapshotView, RuleTestView, RuleView
from app.db.models import Document, Membership, Workspace
from app.workspace.api import DocumentIndexView
from app.workspace.organize import DocumentSearchView
from app.workspace.presets_api import PresetView
from tests.intake_support import _draft_body
from tests.test_content_read_access_pg import change_actor
from tests.test_intake_batch_lifecycle_access_pg import assert_denied
from tests.workspace_access_support import (
    OPERATIONS,
    PRIVATE_PRESET,
    PRIVATE_RULE,
    after_actual_work,
    fingerprint,
    perform,
    workspace_case,
)

CHANGED_WRITES = (
    "rule-create",
    "rule-update",
    "snapshot-refresh",
    "preset-create",
    "preset-update",
)
WRITES = (*CHANGED_WRITES, "snapshot-unchanged")


def after_json(monkeypatch, case, change):
    operation = case["operation"]
    if operation.startswith("snapshot"):
        model = RuleSnapshotView
    elif operation.startswith("preset"):
        model = PresetView
    elif operation == "document-index":
        model = DocumentIndexView
    elif operation == "document-search":
        model = DocumentSearchView
    else:
        model = RuleTestView if operation == "rule-test" else RuleView
    original, fired = model.model_dump_json, []

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        if not fired:
            fired.append(True)
            change()
        return result

    monkeypatch.setattr(model, "model_dump_json", changed)
    return fired


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("change", ("revoked", "expired", "disabled", "membership"))
def test_prepared_workspace_operations_recheck_the_actual_session(
    intake_site,
    monkeypatch,
    operation,
    change,
):
    case = workspace_case(intake_site, operation)
    before = fingerprint(case)
    fired = after_actual_work(monkeypatch, case, lambda: change_actor(case, change))
    assert_denied(perform(case), 401)
    assert fired and fingerprint(case) == before


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("change", ("revoked", "expired", "disabled", "membership"))
def test_serialized_workspace_json_withholds_private_values_after_session_loss(
    intake_site,
    monkeypatch,
    operation,
    change,
):
    case = workspace_case(intake_site, operation)
    before = fingerprint(case)
    fired = after_json(monkeypatch, case, lambda: change_actor(case, change))
    assert_denied(perform(case), 401)
    assert fired
    assert (fingerprint(case) != before) == (operation in CHANGED_WRITES)


@pytest.mark.parametrize("operation", WRITES)
def test_workspace_mutations_recheck_after_the_actual_lock(intake_site, monkeypatch, operation):
    from app.custom_rules import service
    from app.workspace import presets

    case = workspace_case(intake_site, operation)
    before = fingerprint(case)
    module = presets if operation.startswith("preset") else service
    name = "owned_document" if operation.startswith("snapshot") else "require_administrator"
    original, fired = getattr(module, name), []

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        if kwargs.get("lock") and not fired:
            fired.append(True)
            change_actor(case, "revoked")
        return result

    monkeypatch.setattr(module, name, changed)
    assert_denied(perform(case), 401)
    assert fired and fingerprint(case) == before


@pytest.mark.parametrize(
    "operation", ("rule-create", "rule-update", "preset-create", "preset-update")
)
def test_late_administrator_role_loss_rolls_back_the_real_workspace_change(
    intake_site,
    monkeypatch,
    operation,
):
    case = workspace_case(intake_site, operation)
    before = fingerprint(case)

    def role_loss():
        with Session(case["engine"]) as session, session.begin():
            session.get(Membership, (case["workspace"], case["actor"])).role = "member"

    fired = after_actual_work(monkeypatch, case, role_loss)
    assert_denied(perform(case), 404)
    assert fired and fingerprint(case) == before
    assert case["client"].get("/api/v1/auth/session").status_code == 200


@pytest.mark.parametrize("operation", OPERATIONS)
def test_current_session_in_another_workspace_does_not_authorize_private_target_json(
    intake_site,
    monkeypatch,
    operation,
):
    case = workspace_case(intake_site, operation)
    extra = uuid4()
    with Session(case["engine"]) as session, session.begin():
        session.add(Workspace(id=extra, name="Another synthetic active workspace"))
        session.flush()
        session.add(Membership(workspace_id=extra, user_id=case["actor"], role="member"))
    try:
        fired = after_json(monkeypatch, case, lambda: change_actor(case, "membership"))
        assert_denied(perform(case), 404)
        assert fired and case["client"].get("/api/v1/auth/session").status_code == 200
    finally:
        with Session(case["engine"]) as session, session.begin():
            session.delete(session.get(Membership, (extra, case["actor"])))
            session.delete(session.get(Workspace, extra))


@pytest.mark.parametrize(
    "operation",
    ("rules-read", "rule-create", "rule-update", "presets-read", "preset-create", "preset-update"),
)
def test_actual_new_rule_or_preset_version_denies_the_previous_serialized_body(
    intake_site,
    monkeypatch,
    operation,
):
    case = workspace_case(intake_site, operation)

    def version_change():
        prefix = f"/api/v1/workspaces/{case['workspace']}"
        route = prefix + ("/presets" if operation.startswith("preset") else "/rules")
        current = case["client"].get(route).json()
        record = next(
            item
            for item in current
            if item["id"]
            == str(case["preset_id"] if operation.startswith("preset") else case["rule_id"])
        )
        # For a newly created single response, change that newly created row.
        if operation.endswith("create"):
            record = next(item for item in current if "second" in item["name"])
        body = PRIVATE_PRESET if operation.startswith("preset") else PRIVATE_RULE
        result = case["client"].put(
            route + "/" + record["id"],
            headers=case["headers"],
            json={**body, "name": record["name"], "expected_version": record["version"]},
        )
        assert result.status_code == 200

    fired = after_json(monkeypatch, case, version_change)
    assert_denied(perform(case), 409)
    assert fired and case["client"].get("/api/v1/auth/session").status_code == 200


@pytest.mark.parametrize(
    "operation",
    (
        "snapshot-read",
        "snapshot-refresh",
        "snapshot-unchanged",
        "document-index",
        "document-search",
    ),
)
@pytest.mark.parametrize("change", ("expired", "deleted"))
def test_expired_or_deleted_document_cannot_release_serialized_rules_or_title(
    intake_site,
    monkeypatch,
    operation,
    change,
):
    case = workspace_case(intake_site, operation)

    def document_change():
        with Session(case["engine"]) as session, session.begin():
            document = session.get(Document, case["document_id"])
            if change == "expired":
                document.expires_at = document.created_at + timedelta(microseconds=1)
            else:
                document.deleted_at = datetime.now(UTC)
                document.status = "deleted"

    fired = after_json(monkeypatch, case, document_change)
    status = 404 if change == "deleted" and operation.startswith("document") else 410
    assert_denied(perform(case), status)
    assert fired and case["client"].get("/api/v1/auth/session").status_code == 200


@pytest.mark.parametrize("operation", ("document-index", "document-search"))
def test_titles_recheck_grants_after_their_actual_validation_decryption(
    intake_site,
    monkeypatch,
    operation,
):
    from app.db.crypto import KeyRing

    case = workspace_case(intake_site, operation)
    original, fired, serialized = KeyRing.decrypt_text, [], []
    after_json(monkeypatch, case, lambda: serialized.append(True))

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        if serialized and not fired:
            fired.append(True)
            change_actor(case, "membership")
        return result

    monkeypatch.setattr(KeyRing, "decrypt_text", changed)
    # The resource check notices grant loss; the last session lookup also
    # runs when resource checks succeed. No title is returned in either case.
    assert_denied(perform(case), 404)
    assert fired


def test_search_cursor_cannot_expose_a_deleted_candidate(intake_site, monkeypatch):
    case = workspace_case(intake_site, "document-search")
    case["body"]["limit"] = 1
    second = case["client"].post(
        "/api/v1/documents",
        headers=case["headers"],
        json=_draft_body(case["workspace"], title="Fictional newer search result"),
    )
    assert second.status_code == 201
    ready = perform(case)
    assert ready.status_code == 200 and ready.json()["next_cursor"] is not None
    cursor_id = UUID(ready.json()["next_cursor"]["id"])

    def remove_candidate():
        with Session(case["engine"]) as session, session.begin():
            document = session.get(Document, cursor_id)
            document.deleted_at, document.status = datetime.now(UTC), "deleted"

    fired = after_json(monkeypatch, case, remove_candidate)
    assert_denied(perform(case), 404)
    assert fired


@pytest.mark.parametrize("operation", OPERATIONS)
def test_session_ending_after_real_final_resource_checks_is_checked_again(
    intake_site,
    monkeypatch,
    operation,
):
    from app.custom_rules import api
    from app.workspace import api as index_api
    from app.workspace import organize_api, presets_api

    case = workspace_case(intake_site, operation)
    serialized = []
    after_json(monkeypatch, case, lambda: serialized.append(True))
    if operation.startswith("snapshot"):
        module, name = api, "validate_snapshot_view"
    elif operation.startswith("preset"):
        module, name = presets_api, "validate_preset_view"
    elif operation == "document-index":
        module, name = index_api, "validate_title_view"
    elif operation == "document-search":
        module, name = organize_api, "validate_title_view"
    else:
        module, name = api, "active_workspace" if operation == "rule-test" else "validate_rule_view"
    original, fired = getattr(module, name), []

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        if serialized and not fired:
            fired.append(True)
            change_actor(case, "revoked")
        return result

    monkeypatch.setattr(module, name, changed)
    assert_denied(perform(case), 401)
    assert fired


@pytest.mark.parametrize("operation", ("rules-read", "presets-read", "snapshot-read"))
def test_membership_ending_during_actual_response_metadata_queries_is_denied(
    intake_site,
    monkeypatch,
    operation,
):
    case = workspace_case(intake_site, operation)
    extra = uuid4()
    with Session(case["engine"]) as session, session.begin():
        session.add(Workspace(id=extra, name="Another active synthetic workspace"))
        session.flush()
        session.add(Membership(workspace_id=extra, user_id=case["actor"], role="member"))
    serialized, fired = [], []
    after_json(monkeypatch, case, lambda: serialized.append(True))
    original = Session.execute

    def changed(self, statement, *args, **kwargs):
        result = original(self, statement, *args, **kwargs)
        sql = str(statement)
        metadata = sql.startswith(
            (
                "SELECT workspace_rules.id, workspace_rules.version",
                "SELECT presets.id, presets.version",
            )
        )
        if serialized and metadata and not fired:
            fired.append(True)
            change_actor(case, "membership")
        return result

    monkeypatch.setattr(Session, "execute", changed)
    try:
        assert_denied(perform(case), 404)
        assert fired and case["client"].get("/api/v1/auth/session").status_code == 200
    finally:
        with Session(case["engine"]) as session, session.begin():
            session.delete(session.get(Membership, (extra, case["actor"])))
            session.delete(session.get(Workspace, extra))


@pytest.mark.parametrize("operation", OPERATIONS)
def test_authorized_workspace_operations_preserve_the_http_contract(intake_site, operation):
    response = perform(workspace_case(intake_site, operation))
    assert response.status_code == (201 if operation in ("rule-create", "preset-create") else 200)
    assert response.headers["cache-control"] == "no-store"
    assert "Fictional" in response.text
