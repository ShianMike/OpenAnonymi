"""Real paragraph/table boundaries, exact matches and multiline address detection."""

import io
from uuid import UUID, uuid4

import pytest
from docx import Document as WordDocument
from sqlalchemy.orm import Session

from app.db.crypto import KeyRing
from app.db.models import ExportEvent
from app.db.source_structures import SourceStructure
from tests.docx_fixtures import simple_docx
from tests.docx_support import confirm, mark, output, upload
from tests.intake_support import _login
from tests.styles_support import draft


def test_manual_add_correction_and_exact_mark_crossing_are_atomic(intake_site):
    owner, other, _, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    rh = _login(other, "intake-other@example.invalid")
    base, state, source = upload(
        owner, headers, workspace, simple_docx("😀 Nora", "Caldwell", "Nora", "A\tB")
    )
    crossing = {"start": source["text"].index("Nora"), "end": source["text"].index("Caldwell") + 8}
    body = {"expected": state["version"], "span": crossing, "category": "person"}
    assert other.post(base + "/findings", json=body, headers=rh).status_code == 404
    denied = owner.post(base + "/findings", json=body, headers=headers)
    assert denied.status_code == 422 and denied.json()["code"] == "finding_crosses_block"
    assert owner.get(base + "/findings").json() == state
    state = mark(owner, headers, base, state, source["text"], "Nora", "person")
    finding = state["findings"][0]["finding_id"]
    path = base + "/findings/" + finding
    body["expected"] = state["version"]
    for method, target, payload in [
        ("put", path, body),
        ("post", path + "/exact-matches", {"expected": state["version"], "span": crossing}),
    ]:
        denied = getattr(owner, method)(target, json=payload, headers=headers)
        assert denied.status_code == 422 and denied.json()["code"] == "finding_crosses_block"
        assert owner.get(base + "/findings").json() == state
    offers = owner.get(path + "/exact-matches").json()
    assert offers["spans"] == [
        {"start": source["text"].rindex("Nora"), "end": source["text"].rindex("Nora") + 4}
    ]
    accepted = owner.post(
        path + "/exact-matches",
        json={"expected": state["version"], "span": offers["spans"][0]},
        headers=headers,
    )
    assert accepted.status_code == 200
    state = accepted.json()
    tab = source["text"].index("A\tB")
    denied = owner.post(
        base + "/findings",
        json={
            "expected": state["version"],
            "span": {"start": tab, "end": tab + 3},
            "category": "custom",
        },
        headers=headers,
    )
    assert denied.status_code == 422 and denied.json()["code"] == "finding_crosses_block"


@pytest.mark.parametrize("table", [False, True])
def test_actual_multiline_address_scan_is_dropped_counted_and_legacy_paste_works(
    intake_site, table
):
    owner, _, _, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    if table:
        word = WordDocument()
        cells = word.add_table(rows=1, cols=2).rows[0].cells
        cells[0].text, cells[1].text = "123 Cedar Street", "Denver, CO 80202"
        stream = io.BytesIO()
        word.save(stream)
        content = stream.getvalue()
    else:
        content = simple_docx("123 Cedar Street", "Denver, CO 80202")
    base, state, source = upload(
        owner, headers, workspace, content, categories="address", region="US"
    )
    scan = owner.get(base + "/scan").json()
    assert scan["status"] == "completed" and scan["dropped_suggestions"] == 1
    assert scan["suggestions"] == state["findings"] == []
    assert "123 Cedar" not in str(scan)
    assert (
        owner.post(base + "/scan", json={"expected": state["version"]}, headers=headers).json()[
            "dropped_suggestions"
        ]
        == 1
    )
    confirm(owner, headers, base, state)
    assert output(owner, headers, base, state).status_code == 200
    legacy, legacy_state = draft(
        owner, headers, workspace, source["text"], [(source["text"], "address")]
    )
    assert len(legacy_state["findings"]) == 1
    assert owner.get(legacy + "/scan").json()["dropped_suggestions"] == 0


@pytest.mark.parametrize("damage", ["ciphertext", "missing_key", "malformed_map"])
def test_unreadable_layout_fails_closed_without_export_event_or_content(intake_site, damage):
    owner, _, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    base, state, _ = upload(owner, headers, workspace, simple_docx("Fictional protected source"))
    confirm(owner, headers, base, state)
    keys = KeyRing.from_settings(owner.app.state.settings)
    with Session(engine) as session, session.begin():
        session.info["allow_source_key_rotation"] = True
        from sqlalchemy import text

        session.execute(text("SET LOCAL openanonymi.key_rotation='on'"))
        row = session.get(SourceStructure, UUID(state["version"]["source_revision_id"]))
        if damage == "missing_key":
            row.key_id = "unavailable"
        else:
            row.layout_ciphertext = (
                b"damaged"
                if damage == "ciphertext"
                else keys.encrypt_text('{"v":1,"blocks":[]}').ciphertext
            )
    event = uuid4()
    refused = output(owner, headers, base, state, event=event)
    assert refused.status_code == 503 and refused.json()["code"] == "content_unavailable"
    assert "Fictional" not in refused.text and "blocks" not in refused.text
    with Session(engine) as session:
        assert session.get(ExportEvent, event) is None
    assert (
        owner.post(
            base + "/findings",
            json={
                "expected": state["version"],
                "span": {"start": 0, "end": 9},
                "category": "custom",
            },
            headers=headers,
        ).status_code
        == 503
    )
    assert owner.delete(base, headers=headers).status_code == 200
    with Session(engine) as session:
        assert session.get(SourceStructure, UUID(state["version"]["source_revision_id"])) is None
