"""Real protected reads recheck access after assembly and JSON serialization."""

import time
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.batches.contracts import BatchList, BatchView
from app.db.batches import Batch
from app.db.models import Document, Membership, User, Workspace
from app.db.team_review import ReviewHandoff
from app.intake.api import SourceView
from app.intake.csv_contracts import CsvSettingsView
from app.intake.import_api import ImportPreview
from app.notifications.contracts import NotificationPage
from tests.batch_support import batch_client, upload
from tests.intake_support import _login
from tests.test_notifications_pg import TITLE, assign, start_review
from tests.test_output_session_access_pg import end_session
from tests.test_review_state_pg import prepare

READS = ("source", "revision", "csv", "rules", "batch", "batches", "notifications")
PRIVATE = ("Fictional", "nora@example.test", "Synthetic optional title", TITLE, "Contact")


def read_case(site, route):
    owner, other, engine, workspace, actor = site
    case = {"engine": engine, "workspace": workspace, "actor": actor, "client": owner}
    if route in ("batch", "batches"):
        owner, headers, base = batch_client(site)
        case.update(batch_id=UUID(base.rsplit("/", 1)[1]), headers=headers)
        if route == "batch":
            version = upload(owner, headers, base)
            case.update(document_id=UUID(version["document_id"]), path=base, model=BatchView)
        else:
            case.update(path=f"/api/v1/batches?workspace_id={workspace}", model=BatchList)
    elif route == "notifications":
        review = start_review(site)
        assign(review)
        case.update(
            client=other,
            actor=review["reviewer_id"],
            owner=owner,
            document_id=UUID(review["version"]["document_id"]),
            path="/api/v1/notifications",
            model=NotificationPage,
        )
    else:
        owner, other, engine, workspace, actor, headers, base, state = prepare(
            site, "csv" if route in ("csv", "rules") else "pasted"
        )
        suffix = {
            "source": "/source",
            "revision": f"/revisions/{state['version']['source_revision_id']}/source",
            "csv": "/csv-settings",
            "rules": "/column-rules",
        }[route]
        case.update(
            headers=headers,
            other=other,
            base=base,
            state=state,
            document_id=UUID(state["version"]["document_id"]),
            path=base + suffix,
            model=CsvSettingsView if route in ("csv", "rules") else SourceView,
        )
    assert case["client"].get(case["path"]).status_code == 200
    return case


def after_read(monkeypatch, route, case, phase, change):
    from app.batches import api as batch_api
    from app.intake import api as intake_api
    from app.notifications import api as notification_api

    if phase == "serialized":
        module, hook = case["model"], "model_dump_json"
    elif phase == "authorized":
        module, hook = {
            "batch": (batch_api, "validate_batch_view"),
            "batches": (batch_api, "validate_batch_list"),
            "notifications": (notification_api, "validate_notification_page"),
        }.get(route, (intake_api, "review_document"))
    else:
        module, hook = {
            "batch": (batch_api, "load_batch"),
            "batches": (batch_api, "list_batches"),
            "notifications": (notification_api, "list_notifications"),
        }.get(route, (intake_api, "_load_owned_source"))
    original = getattr(module, hook)
    fired = []

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        if not fired:
            fired.append(True)
            change()
        return result

    monkeypatch.setattr(module, hook, changed)
    return fired


def change_actor(case, change):
    if change in ("revoked", "expired"):
        end_session(case["engine"], case["actor"], change)
        return
    with Session(case["engine"]) as session, session.begin():
        if change == "disabled":
            session.get(User, case["actor"]).disabled_at = datetime.now(UTC)
        else:
            session.get(Membership, (case["workspace"], case["actor"])).revoked_at = datetime.now(
                UTC
            )


def assert_neutral(response, status):
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["cache-control"] == "no-store"
    assert all(value not in response.text for value in PRIVATE)


@pytest.mark.parametrize("route", READS)
@pytest.mark.parametrize("phase", ("assembled", "serialized"))
@pytest.mark.parametrize("change", ("revoked", "expired", "disabled"))
def test_ended_session_cannot_release_assembled_private_json(
    intake_site, monkeypatch, route, phase, change
):
    case = read_case(intake_site, route)
    fired = after_read(monkeypatch, route, case, phase, lambda: change_actor(case, change))
    assert_neutral(case["client"].get(case["path"]), 401)
    assert fired


@pytest.mark.parametrize("route", ("source", "batch", "batches", "notifications"))
def test_session_ending_during_final_resource_queries_is_rechecked(intake_site, monkeypatch, route):
    case = read_case(intake_site, route)
    fired = after_read(
        monkeypatch,
        route,
        case,
        "authorized",
        lambda: end_session(case["engine"], case["actor"], "revoked"),
    )
    assert_neutral(case["client"].get(case["path"]), 401)
    assert fired


@pytest.mark.parametrize("route", READS)
def test_revoked_resource_membership_is_denied_even_with_another_active_workspace(
    intake_site, monkeypatch, route
):
    case = read_case(intake_site, route)
    additional = uuid4()
    with Session(case["engine"]) as session, session.begin():
        session.add(Workspace(id=additional, name="Another active synthetic workspace"))
        session.flush()
        session.add(Membership(workspace_id=additional, user_id=case["actor"], role="member"))
    try:
        fired = after_read(
            monkeypatch, route, case, "serialized", lambda: change_actor(case, "membership")
        )
        assert_neutral(case["client"].get(case["path"]), 404)
        assert fired and case["client"].get("/api/v1/auth/session").status_code == 200
    finally:
        with Session(case["engine"]) as session, session.begin():
            session.delete(session.get(Membership, (additional, case["actor"])))
            session.delete(session.get(Workspace, additional))


@pytest.mark.parametrize("route", ("source", "revision", "csv", "rules", "notifications"))
def test_reviewer_grant_removed_after_serialization_denies_content(intake_site, monkeypatch, route):
    case = read_case(intake_site, route)
    if route != "notifications":
        reviewer = UUID(case["other"].get("/api/v1/auth/session").json()["user_id"])
        response = case["client"].put(
            case["base"] + "/handoff",
            headers=case["headers"],
            json={
                "expected": case["state"]["version"],
                "reviewer_id": str(reviewer),
                "require_approval": False,
            },
        )
        assert response.status_code == 200
        case.update(client=case["other"], actor=reviewer)
        allowed = case["client"].get(case["path"])
        assert allowed.status_code == 200
        if route in ("source", "revision"):
            assert allowed.json()["can_edit"] is False

    def remove_grant():
        with Session(case["engine"]) as session, session.begin():
            session.delete(session.get(ReviewHandoff, case["document_id"]))

    fired = after_read(monkeypatch, route, case, "serialized", remove_grant)
    assert_neutral(case["client"].get(case["path"]), 409 if route == "notifications" else 404)
    assert fired
    monkeypatch.undo()
    if route == "notifications":
        fresh = case["client"].get(case["path"])
        assert fresh.status_code == 200
        assert fresh.json()["items"]
        assert all(
            item["title"] is None and not item["document_available"]
            for item in fresh.json()["items"]
        )


@pytest.mark.parametrize(
    "route,change",
    [
        (route, change)
        for route in ("source", "revision", "csv", "rules", "batch", "notifications")
        for change in ("expired", "version", "deleted")
        if (route, change) != ("notifications", "version")
    ],
)
def test_document_change_after_serialization_never_returns_stale_content(
    intake_site, monkeypatch, route, change
):
    case = read_case(intake_site, route)

    def change_document():
        with Session(case["engine"]) as session, session.begin():
            document = session.get(Document, case["document_id"])
            if change == "expired":
                document.expires_at = document.created_at + timedelta(microseconds=1)
            elif change == "deleted":
                document.deleted_at = datetime.now(UTC)
            else:
                document.decision_version += 1

    fired = after_read(monkeypatch, route, case, "serialized", change_document)
    expected = (
        410 if change in ("expired", "deleted") and route not in ("batch", "notifications") else 409
    )
    assert_neutral(case["client"].get(case["path"]), expected)
    assert fired


@pytest.mark.parametrize("route", ("source", "batch", "notifications"))
def test_real_time_expiry_during_serialization_denies_private_body(intake_site, monkeypatch, route):
    case = read_case(intake_site, route)
    expires_at = datetime.now(UTC) + timedelta(seconds=3)
    with Session(case["engine"]) as session, session.begin():
        session.get(Document, case["document_id"]).expires_at = expires_at

    def expire():
        assert datetime.now(UTC) < expires_at, "Content must still be live at serialization"
        time.sleep(max(0, (expires_at - datetime.now(UTC)).total_seconds()) + 0.05)

    fired = after_read(monkeypatch, route, case, "serialized", expire)
    assert_neutral(case["client"].get(case["path"]), 410 if route == "source" else 409)
    assert fired


@pytest.mark.parametrize("route", ("batch", "batches"))
def test_deleted_batch_cannot_release_previously_decrypted_name(intake_site, monkeypatch, route):
    case = read_case(intake_site, route)

    def remove_batch():
        with Session(case["engine"]) as session, session.begin():
            session.get(Batch, case["batch_id"]).deleted_at = datetime.now(UTC)

    fired = after_read(monkeypatch, route, case, "serialized", remove_batch)
    assert_neutral(case["client"].get(case["path"]), 404)
    assert fired


def test_administrator_role_loss_cannot_release_workspace_batch_totals(intake_site, monkeypatch):
    case = read_case(intake_site, "batches")
    with Session(case["engine"]) as session, session.begin():
        session.get(Membership, (case["workspace"], case["actor"])).role = "administrator"
    assert case["client"].get(case["path"]).json()["workspace_total"] == 1

    def demote():
        with Session(case["engine"]) as session, session.begin():
            session.get(Membership, (case["workspace"], case["actor"])).role = "member"

    fired = after_read(monkeypatch, "batches", case, "serialized", demote)
    assert_neutral(case["client"].get(case["path"]), 404)
    assert fired
    monkeypatch.undo()
    assert case["client"].get(case["path"]).json()["workspace_total"] is None


@pytest.mark.parametrize("format", ("txt", "csv"))
@pytest.mark.parametrize("phase", ("assembled", "serialized"))
@pytest.mark.parametrize("change", ("revoked", "expired"))
def test_import_preview_rechecks_after_private_text_and_headers_are_assembled(
    intake_site, monkeypatch, format, phase, change
):
    owner, _, engine, workspace, actor = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    hook = "__init__" if phase == "assembled" else "model_dump_json"
    original = getattr(ImportPreview, hook)
    fired = []

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        end_session(engine, actor, change)
        fired.append(True)
        return result

    monkeypatch.setattr(ImportPreview, hook, changed)
    content = b"Contact,Note\nnora@example.test,Fictional\n"
    response = owner.post(
        "/api/v1/documents/import-preview",
        headers=headers,
        data={"workspace_id": str(workspace)},
        files={"file": ("fictional." + format, content)},
    )
    assert_neutral(response, 401)
    assert fired
