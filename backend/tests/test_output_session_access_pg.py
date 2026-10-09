"""Real downloads and copy responses must stop after a session ends mid-operation."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ExportEvent
from app.db.models import Session as StoredSession
from tests.docx_support import confirm
from tests.test_review_manual_access_pg import fingerprint
from tests.test_review_mutation_access_pg import decision
from tests.test_review_state_pg import prepare

FORMATS = ("txt", "docx", "csv", "pdf", "report")
CASES = [(format, phase) for format in FORMATS for phase in ("rendered", "recorded")]
CASES += [("copy-payload", "rendered"), ("copy-success", "recorded")]


def end_session(engine, actor, change):
    with Session(engine) as session, session.begin():
        now = datetime.now(UTC)
        for row in session.scalars(select(StoredSession).where(StoredSession.user_id == actor)):
            if change == "revoked":
                row.revoked_at = now
            else:
                row.created_at = now - timedelta(days=1)
                row.expires_at = now - timedelta(seconds=1)


def output_fingerprint(engine, document_id):
    with Session(engine) as session:
        return fingerprint(engine, document_id), list(
            session.scalars(
                select(ExportEvent.id)
                .where(ExportEvent.document_id == document_id)
                .order_by(ExportEvent.id)
            )
        )


@pytest.mark.parametrize("format,phase", CASES)
@pytest.mark.parametrize("change", ("revoked", "expired"))
def test_late_output_session_loss_denies_bytes_and_rolls_back_events(
    intake_site, monkeypatch, format, phase, change
):
    from app.exports import csv_export, docx, pdf, report, service

    owner, _, engine, _, actor, headers, base, state = prepare(
        intake_site, "csv" if format == "csv" else "pasted"
    )
    saved = decision(owner, headers, base, state)
    assert saved.status_code == 200
    state = saved.json()
    confirm(owner, headers, base, state)
    body = {"expected": state["version"], "event_id": str(uuid4())}
    if format == "copy-success":
        copied = owner.post(
            base + "/exports/copy-payload", headers=headers, json={"expected": state["version"]}
        )
        assert copied.status_code == 200
        body["completion_id"] = copied.json()["completion_id"]
    if format == "copy-payload":
        body = {"expected": state["version"]}
    document_id = UUID(state["version"]["document_id"])
    before = output_fingerprint(engine, document_id)
    module, hook = (
        (service, "_record_event")
        if phase == "recorded"
        else {
            "pdf": (pdf, "generate_pdf"),
            "report": (report, "generate_report"),
            "docx": (docx, "generate_word"),
            "csv": (csv_export, "generate_csv"),
            "txt": (service, "_current_output"),
            "copy-payload": (service, "_current_output"),
        }[format]
    )
    original = getattr(module, hook)

    def ended(*args, **kwargs):
        result = original(*args, **kwargs)
        end_session(engine, actor, change)
        return result

    monkeypatch.setattr(module, hook, ended)
    response = owner.post(base + "/exports/" + format, headers=headers, json=body)
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/json")
    assert b"Fictional" not in response.content and b"EMAIL_001" not in response.content
    assert response.headers["cache-control"] == "no-store"
    assert output_fingerprint(engine, document_id) == before
