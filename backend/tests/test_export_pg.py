"""Paste, file, and revision workflow on an explicit local PostgreSQL database."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cleanup.service import purge_unavailable_content
from app.db.models import (
    ExportEvent,
)
from app.factory import create_app
from tests.intake_support import ORIGIN, _draft_body, _login


def test_preview_recomputes_from_current_decisions_and_stays_owner_scoped(intake_site):
    owner, other, _engine, workspace_id, _owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    _login(other, "intake-other@example.invalid")
    source = "😀 Alice met Alice."
    created = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, source=source, categories=[]),
        headers=headers,
    )
    version = created.json()["version"]
    path = f"/api/v1/documents/{version['document_id']}"
    assert other.get(f"{path}/preview").status_code == 404
    assert owner.get(f"{path}/preview").headers["Cache-Control"] == "no-store"
    first = source.index("Alice")
    added = owner.post(
        f"{path}/findings",
        json={
            "expected": version,
            "span": {"start": first, "end": first + 5},
            "category": "person",
        },
        headers=headers,
    ).json()
    first_id = added["findings"][0]["finding_id"]
    pending = owner.get(f"{path}/preview").json()
    assert pending["status"] == "incomplete"
    assert pending["text"] == source
    assert pending["unresolved_finding_ids"] == [first_id]
    labeled = owner.post(
        f"{path}/findings/{first_id}/decision",
        json={"expected": added["version"], "action": "label", "affected_finding_ids": [first_id]},
        headers=headers,
    ).json()
    first_preview = owner.get(f"{path}/preview").json()
    assert first_preview["status"] == "complete"
    assert first_preview["version"] == labeled["version"]
    assert first_preview["text"] == "😀 PERSON_001 met Alice."
    assert first_preview["mappings"][0]["source_span"] == {"start": first, "end": first + 5}
    assert first_preview["mappings"][0]["preview_span"] == {"start": first, "end": first + 10}

    second = source.rindex("Alice")
    second_added = owner.post(
        f"{path}/findings",
        json={
            "expected": labeled["version"],
            "span": {"start": second, "end": second + 5},
            "category": "person",
        },
        headers=headers,
    ).json()
    second_id = second_added["findings"][1]["finding_id"]
    assert owner.get(f"{path}/preview").json()["unresolved_finding_ids"] == [second_id]
    second_labeled = owner.post(
        f"{path}/findings/{second_id}/decision",
        json={
            "expected": second_added["version"],
            "action": "label",
            "affected_finding_ids": [second_id],
        },
        headers=headers,
    ).json()
    assert owner.get(f"{path}/preview").json()["text"] == "😀 PERSON_001 met PERSON_002."
    merged = owner.post(
        f"{path}/findings/{second_id}/merge",
        json={"expected": second_labeled["version"], "target_finding_id": first_id},
        headers=headers,
    ).json()
    assert owner.get(f"{path}/preview").json()["text"] == "😀 PERSON_001 met PERSON_001."
    split = owner.post(
        f"{path}/findings/{second_id}/split",
        json={"expected": merged["version"]},
        headers=headers,
    ).json()
    assert owner.get(f"{path}/preview").json()["text"] == "😀 PERSON_001 met PERSON_003."
    undone = owner.post(
        f"{path}/review/undo", json={"expected": split["version"]}, headers=headers
    ).json()
    assert owner.get(f"{path}/preview").json()["text"] == "😀 PERSON_001 met PERSON_001."
    assert undone["version"]["decision_version"] == split["version"]["decision_version"] + 1
    revised = owner.put(
        f"{path}/source",
        json={"expected": undone["version"], "source": "😀 New source only."},
        headers=headers,
    )
    assert revised.status_code == 200
    new_preview = owner.get(f"{path}/preview").json()
    assert new_preview["version"] == revised.json()["version"]
    assert new_preview["text"] == "😀 New source only."
    assert new_preview["mappings"] == []


def test_completed_review_copy_txt_summary_and_stale_export_gate(intake_site):
    owner, other, engine, workspace_id, _owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    _login(other, "intake-other@example.invalid")
    source = "😀 Alice emailed a@example.com.\r\nAlice approved."
    created = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, source=source, categories=["email"]),
        headers=headers,
    )
    version = created.json()["version"]
    path = f"/api/v1/documents/{version['document_id']}"
    completion_path = f"{path}/complete"
    assert (
        owner.post(
            completion_path,
            json={
                "expected": version,
                "confirmed_preview": True,
            },
            headers=headers,
        ).json()["code"]
        == "scan_required"
    )
    scanned = owner.post(f"{path}/scan", json={"expected": version}, headers=headers)
    assert scanned.status_code == 200, scanned.text
    version = scanned.json()["version"]
    email_id = scanned.json()["suggestions"][0]["finding_id"]
    assert (
        owner.post(
            completion_path,
            json={
                "expected": version,
                "confirmed_preview": True,
            },
            headers=headers,
        ).json()["code"]
        == "pending_findings"
    )
    first = source.index("Alice")
    second = source.rindex("Alice")
    for position in (first, second):
        added = owner.post(
            f"{path}/findings",
            json={
                "expected": version,
                "span": {"start": position, "end": position + 5},
                "category": "person",
            },
            headers=headers,
        )
        assert added.status_code == 200, added.text
        version = added.json()["version"]
    rows = owner.get(f"{path}/findings").json()["findings"]
    first_id = next(row["finding_id"] for row in rows if row["span"]["start"] == first)
    second_id = next(row["finding_id"] for row in rows if row["span"]["start"] == second)
    redacted = owner.post(
        f"{path}/findings/{email_id}/decision",
        json={
            "expected": version,
            "action": "redact",
            "affected_finding_ids": [email_id],
        },
        headers=headers,
    ).json()
    version = redacted["version"]
    labeled = owner.post(
        f"{path}/findings/{first_id}/decision",
        json={
            "expected": version,
            "action": "label",
            "affected_finding_ids": [first_id],
        },
        headers=headers,
    ).json()
    version = labeled["version"]
    merged = owner.post(
        f"{path}/findings/{second_id}/merge",
        json={
            "expected": version,
            "target_finding_id": first_id,
        },
        headers=headers,
    ).json()
    version = merged["version"]
    grouped = owner.post(
        f"{path}/findings/{first_id}/decision",
        json={
            "expected": version,
            "action": "label",
            "group_scope": True,
            "affected_finding_ids": [first_id, second_id],
        },
        headers=headers,
    )
    assert grouped.status_code == 200, grouped.text
    version = grouped.json()["version"]
    expected_text = "😀 PERSON_001 emailed [REDACTED].\r\nPERSON_001 approved."
    assert owner.get(f"{path}/preview").json()["text"] == expected_text
    assert (
        owner.post(
            completion_path,
            json={
                "expected": version,
                "confirmed_preview": False,
            },
            headers=headers,
        ).json()["code"]
        == "confirmation_required"
    )
    completed = owner.post(
        completion_path,
        json={
            "expected": version,
            "confirmed_preview": True,
        },
        headers=headers,
    )
    assert completed.status_code == 200, completed.text
    completion_id = completed.json()["completion_id"]
    assert (
        owner.post(
            completion_path,
            json={
                "expected": version,
                "confirmed_preview": True,
            },
            headers=headers,
        ).json()["completion_id"]
        == completion_id
    )
    summary = owner.get(f"{path}/summary")
    assert summary.status_code == 200
    assert summary.json()["counts_by_category"] == {"person": 2, "email": 1}
    assert summary.json()["counts_by_action"] == {"label": 2, "redact": 1}
    assert summary.json()["last_output_generated_at"] is None
    decision_events = owner.get(f"/api/v1/workspaces/{workspace_id}/activity").json()["own_events"]
    assert sum(event["event_code"] == "review_decision_saved" for event in decision_events) == 3
    assert "Alice" not in summary.text and "a@example.com" not in summary.text
    assert other.get(f"{path}/summary").status_code == 404

    copy_payload = owner.post(
        f"{path}/exports/copy-payload",
        json={
            "expected": version,
        },
        headers=headers,
    )
    assert copy_payload.status_code == 200, copy_payload.text
    assert copy_payload.json()["text"] == expected_text
    assert copy_payload.headers["Cache-Control"] == "no-store"
    assert (
        other.post(
            f"{path}/exports/copy-payload",
            json={
                "expected": version,
            },
            headers={
                "Origin": ORIGIN,
                "X-CSRF-Token": other.get("/api/v1/auth/session").json()["csrf_token"],
            },
        ).status_code
        == 404
    )
    with Session(engine) as db:
        assert (
            db.scalars(
                select(ExportEvent).where(ExportEvent.document_id == UUID(version["document_id"]))
            ).all()
            == []
        )

    txt_event_id = str(uuid4())
    txt_body = {"expected": version, "event_id": txt_event_id}
    exported = owner.post(f"{path}/exports/txt", json=txt_body, headers=headers)
    assert exported.status_code == 200, exported.text
    assert exported.content == expected_text.encode("utf-8")
    assert exported.headers["Content-Type"].startswith("text/plain")
    assert exported.headers["Cache-Control"] == "no-store"
    assert exported.headers["X-Content-Type-Options"] == "nosniff"
    assert (
        exported.headers["Content-Disposition"]
        == f'attachment; filename="reviewed-{version["document_id"]}.txt"'
    )
    assert (
        owner.post(f"{path}/exports/txt", json=txt_body, headers=headers).content
        == exported.content
    )
    copy_event_id = str(uuid4())
    ack = owner.post(
        f"{path}/exports/copy-success",
        json={
            "expected": version,
            "completion_id": completion_id,
            "event_id": copy_event_id,
        },
        headers=headers,
    )
    assert ack.status_code == 200, ack.text
    assert (
        owner.post(
            f"{path}/exports/copy-success",
            json={
                "expected": version,
                "completion_id": completion_id,
                "event_id": copy_event_id,
            },
            headers=headers,
        ).status_code
        == 200
    )
    with Session(engine) as db:
        events = db.scalars(
            select(ExportEvent).where(ExportEvent.document_id == UUID(version["document_id"]))
        ).all()
        assert len(events) == 2
        assert {event.format for event in events} == {"copy", "txt"}
    assert owner.get(f"{path}/summary").json()["last_output_generated_at"] is not None
    assert owner.get(f"{path}/source").json()["status"] == "exported"

    revised = owner.put(
        f"{path}/source",
        json={
            "expected": version,
            "source": "New synthetic revision.",
        },
        headers=headers,
    )
    assert revised.status_code == 200, revised.text
    assert (
        owner.post(
            f"{path}/exports/copy-payload",
            json={
                "expected": version,
            },
            headers=headers,
        ).status_code
        == 409
    )
    assert (
        owner.post(
            f"{path}/exports/copy-payload",
            json={
                "expected": revised.json()["version"],
            },
            headers=headers,
        ).json()["code"]
        == "review_not_completed"
    )
    assert owner.get(f"{path}/summary").status_code == 409


def test_full_review_journey_persists_and_cleans_up(intake_site):
    owner, other, engine, workspace_id, _owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    _login(other, "intake-other@example.invalid")
    source = "😀 Alice met Alice. Contact ali@example.com."
    created = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, source=source, categories=["email"]),
        headers=headers,
    )
    assert created.status_code == 201, created.text
    version = created.json()["version"]
    path = f"/api/v1/documents/{version['document_id']}"
    scanned = owner.post(f"{path}/scan", json={"expected": version}, headers=headers)
    assert scanned.status_code == 200, scanned.text
    assert scanned.json()["match_count"] == 1
    version = scanned.json()["version"]
    email_id = scanned.json()["suggestions"][0]["finding_id"]

    for position in (source.index("Alice"), source.rindex("Alice")):
        added = owner.post(
            f"{path}/findings",
            json={
                "expected": version,
                "span": {"start": position, "end": position + 5},
                "category": "person",
            },
            headers=headers,
        )
        assert added.status_code == 200, added.text
        version = added.json()["version"]
    people = sorted(
        (
            row
            for row in owner.get(f"{path}/findings").json()["findings"]
            if row["category"] == "person"
        ),
        key=lambda row: row["span"]["start"],
    )
    first_id, second_id = (row["finding_id"] for row in people)
    kept = owner.post(
        f"{path}/findings/{email_id}/decision",
        json={
            "expected": version,
            "action": "keep",
            "keep_reason": "false_match",
            "affected_finding_ids": [email_id],
        },
        headers=headers,
    )
    assert kept.status_code == 200, kept.text
    version = kept.json()["version"]
    labeled = owner.post(
        f"{path}/findings/{first_id}/decision",
        json={"expected": version, "action": "label", "affected_finding_ids": [first_id]},
        headers=headers,
    )
    assert labeled.status_code == 200, labeled.text
    version = labeled.json()["version"]
    merged = owner.post(
        f"{path}/findings/{second_id}/merge",
        json={"expected": version, "target_finding_id": first_id},
        headers=headers,
    )
    assert merged.status_code == 200, merged.text
    version = merged.json()["version"]
    grouped = owner.post(
        f"{path}/findings/{first_id}/decision",
        json={
            "expected": version,
            "action": "label",
            "group_scope": True,
            "affected_finding_ids": [first_id, second_id],
        },
        headers=headers,
    )
    assert grouped.status_code == 200, grouped.text
    version = grouped.json()["version"]

    # Reopen through a fresh app instance before confirmation and export.
    with TestClient(create_app(owner.app.state.settings, engine=engine)) as reopened:
        reopened_headers = _login(reopened, "intake-owner@example.invalid")
        assert reopened.get(f"{path}/source").json()["text"] == source
        findings = reopened.get(f"{path}/findings").json()["findings"]
        assert len(findings) == 3
        assert {row["label"] for row in findings if row["category"] == "person"} == {"PERSON_001"}
        assert (
            next(row for row in findings if row["finding_id"] == email_id)["keep_reason"]
            == "false_match"
        )
        expected_text = "😀 PERSON_001 met PERSON_001. Contact ali@example.com."
        preview = reopened.get(f"{path}/preview")
        assert preview.status_code == 200 and preview.json()["text"] == expected_text
        completed = reopened.post(
            f"{path}/complete",
            json={"expected": version, "confirmed_preview": True},
            headers=reopened_headers,
        )
        assert completed.status_code == 200, completed.text
        summary = reopened.get(f"{path}/summary")
        assert summary.status_code == 200
        assert summary.json()["counts_by_action"] == {"label": 2, "keep": 1}
        assert "Alice" not in summary.text and "ali@example.com" not in summary.text
        exported = reopened.post(
            f"{path}/exports/txt",
            json={"expected": version, "event_id": str(uuid4())},
            headers=reopened_headers,
        )
        assert exported.status_code == 200, exported.text
        assert exported.content == expected_text.encode("utf-8")
        assert other.get(f"{path}/source").status_code == 404
        assert reopened.delete(path, headers=reopened_headers).json() == {"status": "deleted"}
        assert reopened.get(f"{path}/source").status_code == 410

    assert purge_unavailable_content(engine, now=datetime.now(UTC)).documents_purged == 1
    history = owner.get(
        f"/api/v1/workspaces/{workspace_id}/documents/{version['document_id']}/history"
    )
    assert history.status_code == 200
    assert history.json()["status"] == "deleted"
    assert history.json()["revision_total"] == 0
    assert source not in history.text


def test_zero_match_confirmation_and_explicit_keep_export(intake_site):
    owner, _other, _engine, workspace_id, _owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    source = "Training example only."
    created = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, source=source, categories=["email"]),
        headers=headers,
    )
    version = created.json()["version"]
    path = f"/api/v1/documents/{version['document_id']}"
    scanned = owner.post(f"{path}/scan", json={"expected": version}, headers=headers)
    assert scanned.status_code == 200
    assert scanned.json()["match_count"] == 0
    version = scanned.json()["version"]
    confirmed = owner.post(
        f"{path}/complete",
        json={
            "expected": version,
            "confirmed_preview": True,
        },
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    assert owner.get(f"{path}/summary").json()["finding_count"] == 0
    txt = owner.post(
        f"{path}/exports/txt",
        json={
            "expected": version,
            "event_id": str(uuid4()),
        },
        headers=headers,
    )
    assert txt.content == source.encode("utf-8")

    next_source = "Keep this phrase."
    revised = owner.put(
        f"{path}/source",
        json={
            "expected": version,
            "source": next_source,
        },
        headers=headers,
    )
    assert revised.status_code == 200
    version = revised.json()["version"]
    rescanned = owner.post(f"{path}/scan", json={"expected": version}, headers=headers)
    assert rescanned.status_code == 200
    version = rescanned.json()["version"]
    finding = owner.post(
        f"{path}/findings",
        json={
            "expected": version,
            "span": {"start": 0, "end": 4},
            "category": "custom",
        },
        headers=headers,
    ).json()
    finding_id = finding["findings"][0]["finding_id"]
    kept = owner.post(
        f"{path}/findings/{finding_id}/decision",
        json={
            "expected": finding["version"],
            "action": "keep",
            "keep_reason": "intended_disclosure",
            "affected_finding_ids": [finding_id],
        },
        headers=headers,
    )
    assert kept.status_code == 200, kept.text
    version = kept.json()["version"]
    assert owner.get(f"{path}/preview").json()["text"] == next_source
    assert (
        owner.post(
            f"{path}/complete",
            json={
                "expected": version,
                "confirmed_preview": True,
            },
            headers=headers,
        ).status_code
        == 200
    )
    assert owner.get(f"{path}/summary").json()["counts_by_action"] == {"keep": 1}
    assert owner.post(
        f"{path}/exports/txt",
        json={
            "expected": version,
            "event_id": str(uuid4()),
        },
        headers=headers,
    ).content == next_source.encode("utf-8")
