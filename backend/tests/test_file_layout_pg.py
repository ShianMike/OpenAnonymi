"""File layout review through authenticated, versioned HTTP and encrypted storage."""

import io
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.db.crypto import KeyRing, ProtectedValue
from app.db.models import Document
from app.db.source_structures import SourceStructure
from tests.docx_support import confirm, output
from tests.import_fixtures import pdf_sample
from tests.intake_support import _login
from tests.styles_support import decide


@pytest.mark.parametrize("kind", ["pdf", "txt"])
def test_file_review_export_and_access_boundaries(intake_site, kind):
    owner, other, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    payload = {
        "pdf": pdf_sample(),
        "txt": b"  nora@example.test\r\n\tLiteral # heading  ",
    }[kind]
    result = owner.post(
        "/api/v1/documents/from-file",
        data={"workspace_id": str(workspace), "categories": "email"},
        files={"file": ("fictional." + kind, payload)},
        headers=headers,
    )
    assert result.status_code == 201, result.text
    version = result.json()["version"]
    base = "/api/v1/documents/" + version["document_id"]
    source = owner.get(base + "/source").json()
    assert source["file_format"] == kind
    view = owner.get(base + "/layout")
    assert view.status_code == 200 and view.headers["cache-control"] == "no-store"
    assert view.json()["version"] == version and view.json()["layout"]["kind"] == kind
    with Session(engine) as session:
        row = session.get(SourceStructure, UUID(version["source_revision_id"]))
        assert row.kind == kind and row.layout_ciphertext.startswith(b"gAAAA")
        keys = KeyRing.from_settings(owner.app.state.settings)
        decrypted = json.loads(keys.decrypt_text(ProtectedValue(row.layout_ciphertext, row.key_id)))
        assert decrypted["kind"] == kind
    other_headers = _login(other, "intake-other@example.invalid")
    assert other.get(base + "/layout").status_code == 404
    assert output(other, other_headers, base, {"version": version}, kind).status_code == 404
    assert output(owner, headers, base, {"version": version}, kind).status_code == 409
    scanned = owner.post(base + "/scan", json={"expected": version}, headers=headers)
    assert scanned.status_code == 200, scanned.text
    state = owner.get(base + "/findings").json()
    assert state["findings"]
    for finding in state["findings"][:]:
        result = decide(owner, headers, base, state, finding, "redact")
        assert result.status_code == 200, result.text
        state = result.json()
    preview = owner.get(base + "/layout?variant=preview")
    assert preview.status_code == 200, preview.text
    assert b"nora@example" not in preview.content
    confirm(owner, headers, base, state)
    response = output(owner, headers, base, state, kind)
    assert response.status_code == 200, response.text
    if kind == "pdf":
        assert PdfReader(io.BytesIO(response.content)).pages[0].extract_text() == ""
        assert (
            owner.put(
                base + "/source",
                json={"expected": state["version"], "source": "changed"},
                headers=headers,
            ).status_code
            == 422
        )
    else:
        assert response.content == b"  [REDACTED]\r\n\tLiteral # heading  "
    stale = output(owner, headers, base, {"version": version}, kind)
    assert stale.status_code == 409
    with Session(engine) as session, session.begin():
        document = session.get(Document, UUID(version["document_id"]))
        document.expires_at = datetime.now(UTC) - timedelta(microseconds=1)
    assert owner.get(base + "/layout").status_code == 410
    assert output(owner, headers, base, state, kind).status_code == 410
