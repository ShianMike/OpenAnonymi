"""Versioned defaults preselect choices without deciding or expanding access."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Decision, Membership, ScanRun
from tests.intake_support import _draft_body, _login
from tests.styles_support import decide, draft


def preset(owner, headers, engine, workspace, actor, defaults):
    with Session(engine) as session, session.begin():
        session.get(Membership, (workspace, actor)).role = "administrator"
    path = f"/api/v1/workspaces/{workspace}/presets"
    body = {
        "name": "Style defaults",
        "categories": [],
        "phone_region": "GB",
        "preferred_action": "label",
        "is_default": False,
        "category_defaults": defaults,
    }
    created = owner.post(path, json=body, headers=headers)
    assert created.status_code == 201, created.text
    return path, body, created.json()


def test_snapshot_refresh_permissions_and_confirmation_invalidation(intake_site):
    owner, other, engine, workspace, actor = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    other_headers = _login(other, "intake-other@example.invalid")
    first = {"person": {"action": "label", "style": "stand_in", "style_option": None}}
    path, body, saved = preset(owner, headers, engine, workspace, actor, first)
    assert other.get(path).json() == [saved]
    assert (
        other.put(
            path + "/" + saved["id"], json={**body, "expected_version": 1}, headers=other_headers
        ).status_code
        == 404
    )
    base, state = draft(
        owner,
        headers,
        workspace,
        "Nora Caldwell",
        [("Nora Caldwell", "person")],
        preset_id=saved["id"],
    )
    original_source = owner.get(base + "/source").json()
    assert original_source["category_defaults"] == first
    assert state["findings"][0]["action"] is None
    assert state["findings"][0]["style"] == "token"
    assert owner.get(base + "/preview").json()["text"] == "Nora Caldwell"
    state = decide(owner, headers, base, state, state["findings"][0], "label").json()
    assert (
        owner.post(
            base + "/complete",
            json={"expected": state["version"], "confirmed_preview": True},
            headers=headers,
        ).status_code
        == 200
    )
    assert owner.get(base + "/summary").status_code == 200
    second = {"person": {"action": "redact", "style": "partial_mask", "style_option": "full"}}
    changed = owner.put(
        path + "/" + saved["id"],
        json={**body, "expected_version": 1, "category_defaults": second},
        headers=headers,
    )
    assert changed.status_code == 200 and changed.json()["version"] == 2
    assert (
        owner.put(
            path + "/" + saved["id"], json={**body, "expected_version": 1}, headers=headers
        ).status_code
        == 409
    )
    assert owner.get(base + "/source").json()["category_defaults"] == first
    next_doc = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace, source="Another synthetic review", preset_id=saved["id"]),
        headers=headers,
    )
    assert next_doc.status_code == 201
    next_source = owner.get(
        "/api/v1/documents/" + next_doc.json()["version"]["document_id"] + "/source"
    ).json()
    assert next_source["category_defaults"] == second and next_source["preset_version"] == 2
    with Session(engine) as session, session.begin():
        other_id = UUID(other.get("/api/v1/auth/session").json()["user_id"])
        session.get(Membership, (workspace, other_id)).role = "administrator"
        scans_before = list(
            session.scalars(
                select(ScanRun.id).where(
                    ScanRun.document_id == UUID(state["version"]["document_id"])
                )
            )
        )
    refresh_path = base + "/category-defaults/refresh"
    refresh_body = {"expected_decision_version": state["version"]["decision_version"]}
    assert other.post(refresh_path, json=refresh_body, headers=other_headers).status_code == 404
    assert (
        owner.post(refresh_path, json={"expected_decision_version": 0}, headers=headers).status_code
        == 409
    )
    refreshed = owner.post(refresh_path, json=refresh_body, headers=headers)
    assert refreshed.status_code == 200
    result = refreshed.json()
    assert result["version"]["decision_version"] == state["version"]["decision_version"] + 1
    assert result["findings"] == state["findings"]
    assert result["undo_available"] == 0
    source = owner.get(base + "/source").json()
    assert source["category_defaults"] == second and source["status"] == "needs_review"
    assert source["categories"] == original_source["categories"]
    assert source["phone_region"] == original_source["phone_region"]
    assert owner.get(base + "/summary").status_code == 409
    assert (
        owner.post(
            base + "/exports/txt",
            json={"expected": result["version"], "event_id": str(uuid4())},
            headers=headers,
        ).status_code
        == 409
    )
    with Session(engine) as session:
        assert (
            list(
                session.scalars(
                    select(ScanRun.id).where(
                        ScanRun.document_id == UUID(state["version"]["document_id"])
                    )
                )
            )
            == scans_before
        )
    history = owner.get(
        f"/api/v1/workspaces/{workspace}/documents/{state['version']['document_id']}/history"
    )
    assert history.status_code == 200 and "preset_defaults_applied" in history.text
    assert "Nora Caldwell" not in history.text


@pytest.mark.parametrize(
    "defaults",
    [
        {"person": {"action": "keep", "style": "stand_in"}},
        {"national_id": {"action": "label", "style": "stand_in"}},
        {"email": {"action": "redact", "style": "partial_mask", "style_option": "last4"}},
        {"date": {"action": "redact", "style": "generalize"}},
        {"person": {"action": "label", "style": "token", "source": "private value"}},
        {"unknown": {"action": "label", "style": "token"}},
    ],
)
def test_invalid_defaults_are_rejected_without_preset_change(intake_site, defaults):
    owner, _, engine, workspace, actor = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    path, body, saved = preset(owner, headers, engine, workspace, actor, {})
    denied = owner.put(
        path + "/" + saved["id"],
        json={**body, "expected_version": 1, "category_defaults": defaults},
        headers=headers,
    )
    assert denied.status_code == 422
    assert owner.get(path).json() == [saved]


def test_legacy_preset_update_preserves_defaults_and_no_preset_refresh_is_atomic(intake_site):
    owner, _, engine, workspace, actor = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    defaults = {
        "email": {"action": "redact", "style": "partial_mask", "style_option": "email_domain"}
    }
    path, body, saved = preset(owner, headers, engine, workspace, actor, defaults)
    body.pop("category_defaults")
    changed = owner.put(
        path + "/" + saved["id"], json={**body, "expected_version": 1}, headers=headers
    )
    assert changed.status_code == 200 and changed.json()["category_defaults"] == defaults
    base, state = draft(owner, headers, workspace, "No preset.", [])
    denied = owner.post(
        base + "/category-defaults/refresh",
        json={"expected_decision_version": state["version"]["decision_version"]},
        headers=headers,
    )
    assert denied.status_code == 422 and denied.json()["code"] == "preset_unavailable"
    assert owner.get(base + "/findings").json() == state


@pytest.mark.parametrize(
    "style,option,action",
    [
        ("partial_mask", None, "redact"),
        ("generalize", None, "redact"),
        ("stand_in", "full", "label"),
        ("stand_in", None, "keep"),
    ],
)
def test_database_style_constraints_reject_incomplete_or_incompatible_rows(
    intake_site, style, option, action
):
    owner, _, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    base, state = draft(owner, headers, workspace, "Nora Caldwell", [("Nora Caldwell", "person")])
    saved = decide(owner, headers, base, state, state["findings"][0], "label")
    assert saved.status_code == 200
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE decisions SET action=:action, style=:style, style_option=:option WHERE finding_id=:id"
            ),
            {
                "action": action,
                "style": style,
                "option": option,
                "id": state["findings"][0]["finding_id"],
            },
        )
    with Session(engine) as session:
        decision = session.get(Decision, UUID(state["findings"][0]["finding_id"]))
        assert decision.style == "token"
