"""PDF/report format parity, report privacy and ordinary output isolation gates."""

import json
from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import UUID, uuid4

import pytest
from pypdf import PdfReader
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Document, ExportEvent, Membership, User, Workspace
from app.exports import service
from tests.csv_support import upload_csv
from tests.docx_fixtures import read_word, simple_docx
from tests.docx_support import confirm, mark, output, upload
from tests.intake_support import _draft_body, _login
from tests.styles_support import decide

TEXT = "Fictional 😀 東京\nnora@example.test\nSecret ghp_Fictional7654\n2026-10-03\nKept fictional note"


def prepared(site, kind="pasted"):
    owner, other, engine, workspace, actor = site
    headers = _login(owner, "intake-owner@example.invalid")
    if kind == "docx":
        base, findings, source = upload(owner, headers, workspace, simple_docx(TEXT))
    elif kind == "csv":
        base, findings, source = upload_csv(
            owner, headers, workspace, "Value\n" + TEXT + "\n", delimiter=","
        )
    else:
        created = owner.post(
            "/api/v1/documents",
            json=_draft_body(workspace, source=TEXT, categories=[]),
            headers=headers,
        )
        assert created.status_code == 201
        base = "/api/v1/documents/" + created.json()["version"]["document_id"]
        assert (
            owner.post(
                base + "/scan", json={"expected": created.json()["version"]}, headers=headers
            ).status_code
            == 200
        )
        findings, source = owner.get(base + "/findings").json(), owner.get(base + "/source").json()
    for value, category, action, style, option in [
        ("nora@example.test", "email", "label", "stand_in", None),
        ("ghp_Fictional7654", "secret", "redact", "token", None),
        ("2026-10-03", "date", "label", "date_shift", None),
    ]:
        findings = mark(owner, headers, base, findings, source["text"], value, category)
        finding = next(
            item
            for item in findings["findings"]
            if item["span"]["start"] == source["text"].index(value)
        )
        saved = decide(owner, headers, base, findings, finding, action, style, option)
        assert saved.status_code == 200
        findings = saved.json()
    findings = mark(owner, headers, base, findings, source["text"], "Kept fictional note", "custom")
    finding = next(item for item in findings["findings"] if item["category"] == "custom")
    kept = owner.post(
        base + "/findings/" + finding["finding_id"] + "/decision",
        json={
            "expected": findings["version"],
            "action": "keep",
            "keep_reason": "intended_disclosure",
            "affected_finding_ids": [finding["finding_id"]],
        },
        headers=headers,
    )
    assert kept.status_code == 200
    findings = kept.json()
    confirm(owner, headers, base, findings)
    return owner, other, engine, workspace, actor, headers, base, findings, source


@pytest.mark.parametrize("kind", ["pasted", "docx", "csv"])
def test_actual_formats_match_canonical_review_and_report_omits_freeform_content(intake_site, kind):
    owner, _, engine, _, _, headers, base, findings, source = prepared(intake_site, kind)
    canonical = owner.get(base + "/preview").json()
    pdf, report, txt, word = [
        output(owner, headers, base, findings, format)
        for format in ("pdf", "report", "txt", "docx")
    ]
    assert pdf.status_code == report.status_code == txt.status_code == word.status_code == 200
    extracted = "\n".join(page.extract_text() for page in PdfReader(BytesIO(pdf.content)).pages)
    assert extracted.split() == canonical["text"].split()
    assert txt.content.decode() == canonical["text"] == read_word(word.content)[0]
    assert "ghp_Fictional7654" not in extracted
    assert pdf.headers["content-type"] == "application/pdf"
    for response in (pdf, report):
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["content-disposition"].startswith('attachment; filename="')
    data = json.loads(report.content)
    assert data["review_version"] == findings["version"]
    assert data["finding_count"] == 4
    assert data["counts_by_action"] == {"label": 2, "redact": 1, "keep": 1}
    assert data["counts_by_style"] == {"stand_in": 1, "token": 2, "date_shift": 1}
    assert set(data) == {
        "schema_version",
        "review_version",
        "confirmed_at",
        "generated_at",
        "finding_count",
        "counts_by_category",
        "counts_by_action",
        "counts_by_style",
        "findings",
    }
    raw = report.content.decode()
    assert all(
        canary not in raw
        for canary in (
            "intended_disclosure",
            "Fictional",
            "nora@example.test",
            "ghp_Fictional7654",
            "東京",
        )
    )
    mappings = {item["finding_id"]: item for item in canonical["mappings"]}
    for row in data["findings"]:
        assert set(row) == {
            "finding_id",
            "category",
            "action",
            "style",
            "style_option",
            "source_span",
            "reviewed_span",
        }
        assert row["reviewed_span"] == mappings[row["finding_id"]]["preview_span"]
    assert owner.get(base + "/source").json()["text"] == source["text"]
    with Session(engine) as session:
        assert set(
            session.scalars(
                select(ExportEvent.format).where(
                    ExportEvent.document_id == UUID(findings["version"]["document_id"])
                )
            )
        ) == {"txt", "docx", "pdf", "report"}


@pytest.mark.parametrize("format", ["pdf", "report"])
def test_no_other_member_admin_or_reviewer_can_export_and_csrf_is_required(intake_site, format):
    owner, other, engine, workspace, _, headers, base, findings, _ = prepared(intake_site)
    rh = _login(other, "intake-other@example.invalid")
    reviewer_id = UUID(other.get("/api/v1/auth/session").json()["user_id"])
    with Session(engine) as session, session.begin():
        session.get(Membership, (workspace, reviewer_id)).role = "administrator"
    assert output(other, rh, base, findings, format).status_code == 404
    assigned = owner.put(
        base + "/handoff",
        json={
            "expected": findings["version"],
            "reviewer_id": str(reviewer_id),
            "require_approval": False,
        },
        headers=headers,
    )
    assert assigned.status_code == 200
    assert other.get(base + "/preview").status_code == 200
    current = owner.get(base + "/findings").json()
    confirm(owner, headers, base, current)
    assert output(other, rh, base, current, format).status_code == 404
    assert output(owner, {"Origin": headers["Origin"]}, base, current, format).status_code == 403
    assert (
        output(
            owner, {**headers, "Origin": "https://untrusted.example.test"}, base, current, format
        ).status_code
        == 403
    )


@pytest.mark.parametrize("format", ["pdf", "report"])
@pytest.mark.parametrize("unavailable", ["expired", "deleted", "revoked", "disabled"])
def test_current_unavailability_blocks_both_new_downloads(intake_site, format, unavailable):
    owner, _, engine, workspace, actor, headers, base, findings, _ = prepared(intake_site)
    with Session(engine) as session, session.begin():
        document = session.get(Document, UUID(findings["version"]["document_id"]))
        if unavailable == "expired":
            document.created_at = datetime.now(UTC) - timedelta(days=2)
            document.expires_at = datetime.now(UTC) - timedelta(days=1)
        elif unavailable == "deleted":
            document.deleted_at = datetime.now(UTC)
        elif unavailable == "revoked":
            session.get(Membership, (workspace, actor)).revoked_at = datetime.now(UTC)
        else:
            session.get(User, actor).disabled_at = datetime.now(UTC)
    expected_status = 410 if unavailable in ("expired", "deleted") else 401
    assert output(owner, headers, base, findings, format).status_code == expected_status
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count(ExportEvent.id)).where(
                    ExportEvent.document_id == UUID(findings["version"]["document_id"])
                )
            )
            == 0
        )


@pytest.mark.parametrize("format", ["pdf", "report"])
def test_exact_version_and_event_scope_are_enforced(intake_site, format):
    owner, _, engine, _, _, headers, base, findings, _ = prepared(intake_site)
    stale = {
        **findings,
        "version": {
            **findings["version"],
            "decision_version": findings["version"]["decision_version"] - 1,
        },
    }
    assert output(owner, headers, base, stale, format).status_code == 409
    event = uuid4()
    assert output(owner, headers, base, findings, format, event).status_code == 200
    assert output(owner, headers, base, findings, format, event).status_code == 200
    assert output(owner, headers, base, findings, "txt", event).status_code == 409
    with Session(engine) as session:
        assert (
            session.scalar(select(func.count(ExportEvent.id)).where(ExportEvent.id == event)) == 1
        )


def test_expiry_during_real_pdf_generation_discards_payload_and_rolls_back_event(
    intake_site, monkeypatch
):
    owner, _, engine, _, _, headers, base, findings, _ = prepared(intake_site)
    document_id = UUID(findings["version"]["document_id"])
    with Session(engine) as session, session.begin():
        session.get(Document, document_id).expires_at = datetime.now(UTC) + timedelta(seconds=30)
    ticks = iter([0, 60])
    monkeypatch.setattr(service, "perf_counter", lambda: next(ticks))
    assert output(owner, headers, base, findings, "pdf").status_code == 410
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count(ExportEvent.id)).where(ExportEvent.document_id == document_id)
            )
            == 0
        )


@pytest.mark.parametrize("change", ["owner_revoked", "reviewer_revoked", "policy_enabled"])
def test_access_or_policy_change_during_real_pdf_render_discards_output(
    intake_site, monkeypatch, change
):
    from app.exports import pdf

    owner, reviewer, engine, workspace, actor, headers, base, findings, _ = prepared(intake_site)
    reviewer_id = None
    if change == "reviewer_revoked":
        rh = _login(reviewer, "intake-other@example.invalid")
        reviewer_id = UUID(reviewer.get("/api/v1/auth/session").json()["user_id"])
        assigned = owner.put(
            base + "/handoff",
            json={
                "expected": findings["version"],
                "reviewer_id": str(reviewer_id),
                "require_approval": True,
            },
            headers=headers,
        )
        assert assigned.status_code == 200
        findings = owner.get(base + "/findings").json()
        confirm(owner, headers, base, findings)
        assert (
            reviewer.post(
                base + "/approval",
                json={"expected": findings["version"], "confirmed_preview": True},
                headers=rh,
            ).status_code
            == 200
        )
    generate = pdf.generate_pdf

    def render_then_change(text, now):
        payload = generate(text, now)
        with Session(engine) as session, session.begin():
            if change == "policy_enabled":
                session.get(Workspace, workspace).approval_policy = "always"
            else:
                session.get(
                    Membership, (workspace, reviewer_id or actor)
                ).revoked_at = datetime.now(UTC)
        return payload

    monkeypatch.setattr(pdf, "generate_pdf", render_then_change)
    response = output(owner, headers, base, findings, "pdf")
    # Losing the actor's only membership also ends their current session.
    assert response.status_code == (401 if change == "owner_revoked" else 409)
    if change == "policy_enabled":
        assert response.json()["code"] == "approval_required_by_policy"
    elif change == "reviewer_revoked":
        assert response.json()["code"] == "second_approval_required"
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count(ExportEvent.id)).where(
                    ExportEvent.document_id == UUID(findings["version"]["document_id"])
                )
            )
            == 0
        )
