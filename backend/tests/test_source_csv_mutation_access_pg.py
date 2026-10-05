"""Actual source and CSV transactions deny late access loss without partial saves."""

import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.column_rules import DocumentColumnRules
from app.db.models import Document, ReviewCompletion, ScanRun, SourceRevision
from app.db.source_structures import SourceStructure
from app.intake.csv_contracts import CsvSettingsView
from tests.docx_support import confirm
from tests.styles_support import decide
from tests.test_content_read_access_pg import change_actor
from tests.test_review_manual_access_pg import fingerprint
from tests.test_review_state_pg import prepare

OPERATIONS = (
    "source-pasted",
    "source-docx",
    "source-csv",
    "syntax",
    "rules",
    "noop-syntax",
    "noop-rules",
)


def storage_fingerprint(engine, document_id):
    with Session(engine) as session:
        document = session.get(Document, document_id)
        revision_ids = select(SourceRevision.id).where(SourceRevision.document_id == document_id)
        tables = (
            (SourceRevision, SourceRevision.document_id == document_id),
            (SourceStructure, SourceStructure.revision_id.in_(revision_ids)),
            (DocumentColumnRules, DocumentColumnRules.document_id == document_id),
            (ScanRun, ScanRun.document_id == document_id),
            (ReviewCompletion, ReviewCompletion.document_id == document_id),
        )
        rows = []
        for model, condition in tables:
            rows.append(
                sorted(
                    (
                        tuple(getattr(row, column.name) for column in model.__table__.columns)
                        for row in session.scalars(select(model).where(condition))
                    ),
                    key=repr,
                )
            )
        return (
            document.current_revision_id,
            document.csv_delimiter,
            document.csv_has_header,
            document.updated_at,
            fingerprint(engine, document_id),
            rows,
        )


def mutation_case(site, operation):
    kind = operation.removeprefix("source-") if operation.startswith("source-") else "csv"
    owner, _, engine, workspace, actor, headers, base, state = prepare(site, kind)
    selected = decide(owner, headers, base, state, state["findings"][0], "label", "stand_in")
    assert selected.status_code == 200
    state = selected.json()
    confirm(owner, headers, base, state)
    body = {"expected_settings_version": state["version"]["settings_version"]}
    if operation.startswith("source-"):
        source = owner.get(base + "/source").json()["text"]
        body = {
            "expected": state["version"],
            "source": source.replace("Fictional", "Fictional changed"),
        }
        suffix = "source"
    elif "syntax" in operation:
        body.update(delimiter=",", has_header=operation == "noop-syntax")
        suffix = "csv-settings"
    else:
        body["rules"] = (
            []
            if operation == "noop-rules"
            else [{"column": 1, "mode": "keep", "keep_reason": "intended_disclosure"}]
        )
        suffix = "column-rules"
    return {
        "client": owner,
        "engine": engine,
        "actor": actor,
        "workspace": workspace,
        "headers": headers,
        "path": base + "/" + suffix,
        "base": base,
        "body": body,
        "document_id": UUID(state["version"]["document_id"]),
    }


def after_mutation(monkeypatch, operation, phase, change):
    from app.db import repository
    from app.intake import csv_service

    source = operation.startswith("source-")
    module = repository if source else csv_service
    hook = "owned_document" if phase == "locked" else "record_event" if source else "csv_info"
    original = getattr(module, hook)
    calls, fired = [], []

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(True)
        target = 1 if source or phase == "locked" or operation.startswith("noop-") else 2
        if len(calls) == target and not fired:
            fired.append(True)
            change()
        return result

    monkeypatch.setattr(module, hook, changed)
    return fired


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("phase", ("locked", "built"))
@pytest.mark.parametrize("change", ("revoked", "expired", "disabled", "membership"))
def test_late_source_or_csv_access_loss_rolls_back_protected_state(
    intake_site, monkeypatch, operation, phase, change
):
    case = mutation_case(intake_site, operation)
    before = storage_fingerprint(case["engine"], case["document_id"])
    fired = after_mutation(monkeypatch, operation, phase, lambda: change_actor(case, change))
    response = case["client"].put(case["path"], headers=case["headers"], json=case["body"])
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert "Fictional" not in response.text and "nora@example.test" not in response.text
    assert fired and storage_fingerprint(case["engine"], case["document_id"]) == before


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("phase", ("locked", "built"))
def test_source_and_csv_wall_clock_expiry_rolls_back_entire_transaction(
    intake_site, monkeypatch, operation, phase
):
    case = mutation_case(intake_site, operation)
    before = storage_fingerprint(case["engine"], case["document_id"])
    with Session(case["engine"]) as session, session.begin():
        session.get(Document, case["document_id"]).expires_at = datetime.now(UTC) + timedelta(
            seconds=0.5
        )
    fired = after_mutation(monkeypatch, operation, phase, lambda: time.sleep(0.55))
    response = case["client"].put(case["path"], headers=case["headers"], json=case["body"])
    assert response.status_code == 410 and "Fictional" not in response.text
    assert fired and storage_fingerprint(case["engine"], case["document_id"]) == before


@pytest.mark.parametrize("operation", OPERATIONS)
def test_authorized_source_csv_changes_and_noops_still_work(intake_site, operation):
    case = mutation_case(intake_site, operation)
    before = storage_fingerprint(case["engine"], case["document_id"])
    response = case["client"].put(case["path"], headers=case["headers"], json=case["body"])
    assert response.status_code == 200
    after = storage_fingerprint(case["engine"], case["document_id"])
    assert (after == before) is operation.startswith("noop-")
    if operation.startswith("source-"):
        assert case["client"].get(case["base"] + "/source").json()["text"] == case["body"]["source"]
    else:
        assert case["client"].get(case["base"] + "/csv-settings").json() == response.json()


@pytest.mark.parametrize("operation", ("syntax", "rules", "noop-syntax", "noop-rules"))
@pytest.mark.parametrize("phase", ("assembled", "serialized"))
@pytest.mark.parametrize("change", ("revoked", "expired"))
def test_csv_response_cannot_release_headers_after_post_commit_session_loss(
    intake_site, monkeypatch, operation, phase, change
):
    case = mutation_case(intake_site, operation)
    fired = []
    if phase == "assembled":
        original = CsvSettingsView.model_validate

        def assembled(cls, *args, **kwargs):
            result = original(*args, **kwargs)
            change_actor(case, change)
            fired.append(True)
            return result

        monkeypatch.setattr(CsvSettingsView, "model_validate", classmethod(assembled))
    else:
        original = CsvSettingsView.model_dump_json

        def serialized(*args, **kwargs):
            result = original(*args, **kwargs)
            change_actor(case, change)
            fired.append(True)
            return result

        monkeypatch.setattr(CsvSettingsView, "model_dump_json", serialized)
    response = case["client"].put(case["path"], headers=case["headers"], json=case["body"])
    assert fired and response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert "Contact" not in response.text and "Fictional" not in response.text
    # This boundary occurs after commit; the already authorized transaction stays saved.
    source = operation.startswith("noop-")
    with Session(case["engine"]) as session:
        settings = session.get(Document, case["document_id"]).settings_version
        assert settings == case["body"]["expected_settings_version"] + int(not source)
