import io
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
from zipfile import ZipFile

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cleanup.service import purge_unavailable_content
from app.db.models import Document, ExportEvent, Membership
from app.db.source_structures import SourceStructure
from app.exports.docx import MEDIA_TYPE, PARTS_ALLOWLIST
from tests.docx_fixtures import SENTINEL, read_word, simple_docx, structured_docx
from tests.docx_support import confirm, mark, output, upload
from tests.intake_support import _login
from tests.styles_support import decide


@pytest.mark.parametrize(
    "value,category",
    [
        ("Nora Caldwell", "person"),
        ("Example Company", "organization"),
        ("Example Town", "location"),
        ("12 Example Street", "address"),
        ("nora@example.test", "email"),
        ("https://example.test/path", "url"),
        ("+44 7400 123456", "phone"),
    ],
)
def test_each_fictional_category_through_real_word_layout_matches_canonical_output(
    intake_site, value, category
):
    owner, _, _, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    base, state, source = upload(
        owner, headers, workspace, simple_docx("😀 " + value, "Later block")
    )
    state = mark(owner, headers, base, state, source["text"], value, category)
    saved = decide(owner, headers, base, state, state["findings"][0], "label", "stand_in")
    assert saved.status_code == 200, saved.text
    state = saved.json()
    confirm(owner, headers, base, state)
    word, txt = output(owner, headers, base, state), output(owner, headers, base, state, "txt")
    assert word.status_code == txt.status_code == 200
    assert (
        read_word(word.content)[0]
        == txt.content.decode()
        == owner.get(base + "/preview").json()["text"]
    )
    assert value not in read_word(word.content)[0]


def test_structured_word_has_style_parity_fresh_parts_no_hidden_original_and_idempotent_event(
    intake_site,
):
    owner, other, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    _login(other, "intake-other@example.invalid")
    base, state, source = upload(owner, headers, workspace, structured_docx())
    assert output(owner, headers, base, state).status_code == 409
    assert (
        output(other, _login(other, "intake-other@example.invalid"), base, state).status_code == 404
    )
    text = source["text"]
    for value, category, action, style, option in [
        ("Nora Caldwell", "person", "label", "stand_in", None),
        ("nora@example.test", "email", "redact", "partial_mask", "email_domain"),
        ("+44 7400 123456", "phone", "label", "stand_in", None),
        ("2000-01-01", "date", "redact", "generalize", "age_band"),
        ("2026-10-03", "date", "label", "date_shift", None),
        ("ghp_Fictional7654", "secret", "redact", "partial_mask", "secret_prefix"),
    ]:
        state = mark(owner, headers, base, state, text, value, category)
        finding = next(
            item for item in state["findings"] if item["span"]["start"] == text.index(value)
        )
        saved = decide(owner, headers, base, state, finding, action, style, option)
        assert saved.status_code == 200, saved.text
        state = saved.json()
    for finding in state["findings"]:
        if finding["action"] is None:
            saved = decide(owner, headers, base, state, finding, "redact")
            assert saved.status_code == 200
            state = saved.json()
    confirm(owner, headers, base, state)
    event = uuid4()
    word = output(owner, headers, base, state, event=event)
    assert word.status_code == 200, word.text if word.status_code != 200 else ""
    assert word.headers["content-type"] == MEDIA_TYPE
    assert word.headers["cache-control"] == "no-store"
    assert word.headers["x-content-type-options"] == "nosniff"
    assert (
        word.headers["content-disposition"]
        == f'attachment; filename="reviewed-{state["version"]["document_id"]}.docx"'
    )
    canonical = owner.get(base + "/preview").json()["text"]
    assert (
        read_word(word.content)[0]
        == output(owner, headers, base, state, "txt").content.decode()
        == canonical
    )
    with ZipFile(io.BytesIO(word.content)) as archive:
        assert set(archive.namelist()) == PARTS_ALLOWLIST
        assert all(SENTINEL.encode() not in archive.read(name) for name in archive.namelist())
        assert all(
            b"Nora Caldwell" not in archive.read(name)
            for name in archive.namelist()
            if name != "word/document.xml"
        )
    assert output(owner, headers, base, state, event=event).status_code == 200
    assert output(owner, headers, base, state, "txt", event=event).status_code == 409
    with Session(engine) as session:
        rows = session.scalars(select(ExportEvent).where(ExportEvent.id == event)).all()
        assert len(rows) == 1 and rows[0].format == "docx"
    assert owner.get(base + "/source").json()["text"] == text


def test_same_gate_requires_exact_completion_owner_and_active_second_approval(intake_site):
    owner, reviewer, engine, workspace, _actor = intake_site
    headers, rh = (
        _login(owner, "intake-owner@example.invalid"),
        _login(reviewer, "intake-other@example.invalid"),
    )
    reviewer_id = reviewer.get("/api/v1/auth/session").json()["user_id"]
    base, state, _ = upload(owner, headers, workspace, simple_docx("Fictional review"))
    handoff = owner.put(
        base + "/handoff",
        json={"expected": state["version"], "reviewer_id": reviewer_id, "require_approval": True},
        headers=headers,
    )
    assert handoff.status_code == 200
    state = owner.get(base + "/findings").json()
    confirm(owner, headers, base, state)
    assert output(owner, headers, base, state).status_code == 409
    assert output(reviewer, rh, base, state).status_code == 404
    assert (
        reviewer.post(
            base + "/approval",
            json={"expected": state["version"], "confirmed_preview": True},
            headers=rh,
        ).status_code
        == 200
    )
    assert output(owner, headers, base, state).status_code == 200
    assert (
        owner.post(
            base + "/exports/docx",
            json={"expected": state["version"], "event_id": str(uuid4())},
            headers={"Origin": "http://localhost:5173"},
        ).status_code
        == 403
    )
    with Session(engine) as session, session.begin():
        session.get(Membership, (workspace, UUID(reviewer_id))).revoked_at = datetime.now(UTC)
    assert output(owner, headers, base, state).status_code == 409
    with Session(engine) as session, session.begin():
        document = session.get(Document, UUID(state["version"]["document_id"]))
        document.created_at = datetime.now(UTC) - timedelta(days=2)
        document.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert output(owner, headers, base, state).status_code == 410
    assert (
        purge_unavailable_content(engine, now=datetime.now(UTC), batch_size=100).documents_purged
        >= 1
    )
    with Session(engine) as session:
        assert session.get(SourceStructure, UUID(state["version"]["source_revision_id"])) is None


def test_source_edit_blocks_old_or_unconfirmed_word_and_pasted_docx_keeps_crlf(intake_site):
    from tests.styles_support import draft

    owner, _, _, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    base, state = draft(owner, headers, workspace, "😀 First\r\n\r\n東京 last\n", [])
    confirm(owner, headers, base, state)
    assert (
        read_word(output(owner, headers, base, state).content)[0] == "😀 First\r\n\r\n東京 last\n"
    )
    changed = owner.put(
        base + "/source",
        json={"expected": state["version"], "source": "New source"},
        headers=headers,
    )
    assert changed.status_code == 200 and changed.json()["structure"] == "none"
    assert output(owner, headers, base, state).status_code == 409
    assert output(owner, headers, base, {"version": changed.json()["version"]}).status_code == 409
