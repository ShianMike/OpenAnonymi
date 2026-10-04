"""Actual SQL/API measurements on 60/500 findings and group decisions."""

import json
import os
import time
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.db.models import Finding
from tests.intake_support import _draft_body, _login

MILESTONE = os.environ.get("OPENANONYMI_PERF_MILESTONE", "E11")
assert MILESTONE in {"E11", "G06", "E12"}
OUTPUT = (
    Path(__file__).resolve().parents[2]
    / "docs/privacy-review-build/evidence/expansion-2"
    / MILESTONE
)


def source_text(count):
    line_size = 100 if count == 60 else 200
    return "".join(
        f"Fictional note {index:05d}: contact-{index:05d}@example.test. ".ljust(line_size - 1, ".")
        + "\n"
        for index in range(count)
    )


@pytest.mark.parametrize("count", [60, 500])
def test_real_review_request_query_counts_and_group_action(intake_site, count):
    owner, _other, engine, workspace_id, _actor = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    created = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, source=source_text(count), categories=["email"]),
        headers=headers,
    )
    assert created.status_code == 201
    version = created.json()["version"]
    base = f"/api/v1/documents/{version['document_id']}"
    scanned = owner.post(base + "/scan", json={"expected": version}, headers=headers)
    assert scanned.status_code == 200 and scanned.json()["match_count"] == count
    findings = owner.get(base + "/findings").json()
    assert len(findings["findings"]) == count
    measurements, queries = {}, []

    def counted(_connection, _cursor, _statement, _params, _context, _many):
        queries.append(1)

    def measure(name, call):
        queries.clear()
        started = time.perf_counter()
        response = call()
        measurements[name] = {
            "queries": len(queries),
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        assert response.status_code == 200
        return response

    event.listen(engine, "before_cursor_execute", counted)
    try:
        for endpoint in ("source", "scan", "findings", "preview", "handoff"):
            measure(endpoint, lambda endpoint=endpoint: owner.get(base + "/" + endpoint))
        if any(path.endswith("/review-state") for path in owner.app.openapi()["paths"]):
            measure("review-state", lambda: owner.get(base + "/review-state"))
        # Seed only the grouping metadata after a real API merge; all subsequent
        # decision admission, row reads, encrypted Undo and preview remain real.
        merged = owner.post(
            base + f"/findings/{findings['findings'][0]['finding_id']}/merge",
            json={
                "expected": findings["version"],
                "target_finding_id": findings["findings"][1]["finding_id"],
            },
            headers=headers,
        )
        assert merged.status_code == 200
        merged = merged.json()
        group_id = UUID(merged["findings"][0]["group_id"])
        with Session(engine) as session, session.begin():
            for row in session.scalars(
                select(Finding).where(Finding.document_id == UUID(version["document_id"]))
            ):
                row.group_id = group_id
        result = measure(
            "group-redact",
            lambda: owner.post(
                base + f"/findings/{findings['findings'][0]['finding_id']}/decision",
                json={
                    "expected": merged["version"],
                    "action": "redact",
                    "keep_reason": None,
                    "group_scope": True,
                    "affected_finding_ids": [row["finding_id"] for row in merged["findings"]],
                },
                headers=headers,
            ),
        )
        assert all(row["action"] == "redact" for row in result.json()["findings"])
        measure("decided-preview", lambda: owner.get(base + "/preview"))
    finally:
        event.remove(engine, "before_cursor_execute", counted)
    phase = os.environ.get("OPENANONYMI_PERF_PHASE", "after")
    assert phase in {"before", "after"}
    if phase == "after":
        assert measurements["review-state"]["queries"] <= 24
        assert measurements["group-redact"]["queries"] <= 30
        assert all(
            measurements[name]["queries"] <= limit
            for name, limit in (
                ("source", 6),
                ("scan", 6),
                ("findings", 9),
                # D047: measured four fixed queries for post-render session/grant
                # checks;13 queries for both60 and500 findings, no per-row reads.
                ("preview", 13),
                ("handoff", 6),
            )
        )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / f"{phase}-sql-perf-{count}.json").write_text(
        json.dumps(
            {
                "phase": phase,
                "fixture": f"perf-{count}",
                "findings": count,
                "synthetic_fixture_only": True,
                "measurements": measurements,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
