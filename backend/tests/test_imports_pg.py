from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models import Document
from tests.import_fixtures import docx_sample, pdf_sample
from tests.intake_support import _login


def test_authenticated_preview_is_transient_and_file_review_txt_gate(intake_site):
    owner, _other, engine, workspace, _user = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    path = "/api/v1/documents/import-preview"
    assert (
        owner.post(
            path,
            data={"workspace_id": str(workspace)},
            files={"file": ("sample.docx", docx_sample())},
            headers={"Origin": "http://localhost:5173"},
        ).status_code
        == 403
    )
    assert (
        owner.post(
            path,
            data={"workspace_id": str(uuid4())},
            files={"file": ("sample.docx", docx_sample())},
            headers=headers,
        ).status_code
        == 404
    )
    preview = owner.post(
        path,
        data={"workspace_id": str(workspace)},
        files={"file": ("sample.docx", docx_sample())},
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    assert "😀" in preview.json()["text"] and "Fictional footer" in preview.json()["text"]
    with Session(engine) as session:
        assert session.query(Document).filter(Document.workspace_id == workspace).count() == 0
    created = owner.post(
        "/api/v1/documents/from-file",
        data={"workspace_id": str(workspace), "categories": "email", "phone_region": "PH"},
        files={"file": ("sample.pdf", pdf_sample())},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    version = created.json()["version"]
    base = f"/api/v1/documents/{version['document_id']}"
    assert owner.get(base + "/source").json()["title"] is None
    source = owner.get(base + "/source").json()["text"]
    assert "nora@example.com" in source and "metadata" not in source
    assert (
        owner.post(
            base + "/exports/txt",
            json={"expected": version, "event_id": str(uuid4())},
            headers=headers,
        ).status_code
        == 409
    )
    scan = owner.post(base + "/scan", json={"expected": version}, headers=headers).json()
    item = scan["suggestions"][0]
    decision = owner.post(
        base + "/findings/" + item["finding_id"] + "/decision",
        json={
            "expected": scan["version"],
            "action": "redact",
            "keep_reason": None,
            "group_scope": False,
            "affected_finding_ids": [item["finding_id"]],
        },
        headers=headers,
    )
    assert decision.status_code == 200, decision.text
    confirmed = owner.post(
        base + "/complete",
        json={"expected": decision.json()["version"], "confirmed_preview": True},
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    exported = owner.post(
        base + "/exports/txt",
        json={"expected": confirmed.json()["version"], "event_id": str(uuid4())},
        headers=headers,
    )
    assert exported.status_code == 200, exported.text
    assert exported.content == source.replace("nora@example.com", "[REDACTED]").encode("utf-8")
    assert exported.headers["content-type"].startswith("text/plain")
    assert owner.get(base + "/source").json()["text"] == source


def test_markdown_file_scans_code_and_prose_without_losing_source(intake_site):
    owner, _other, _engine, workspace, _user = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    source = (
        "# Meeting 😀\r\n\r\nPrepared by (`maya@example.com`)\r\n"
        "| Contact |\r\n| --- |\r\n| daniel@example.org |\r\n"
        "**billing@example.com**\r\n\r\n"
        "```text\r\nuser=jordan@example.net ip=192.0.2.18\r\n```\r\n"
        "Phone: +1 (202) 555-0162\r\n"
    )
    created = owner.post(
        "/api/v1/documents/from-file",
        data={"workspace_id": str(workspace), "categories": "email,phone,identifier", "phone_region": "US"},
        files={"file": ("meeting.md", source.encode())}, headers=headers,
    )
    assert created.status_code == 201, created.text
    version = created.json()["version"]
    base = f"/api/v1/documents/{version['document_id']}"
    assert owner.get(base + "/source").json()["text"] == source
    scan = owner.post(base + "/scan", json={"expected": version}, headers=headers)
    assert scan.status_code == 200, scan.text
    assert [source[item["span"]["start"]:item["span"]["end"]] for item in scan.json()["suggestions"]] == [
        "maya@example.com", "daniel@example.org", "billing@example.com", "jordan@example.net",
        "192.0.2.18", "+1 (202) 555-0162",
    ]
    assert owner.get(base + "/source").json()["text"] == source
    assert owner.get(base + "/preview").json()["text"] == source
