from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.column_rules import DocumentColumnRules
from app.db.crypto import KeyRing, ProtectedValue
from app.db.models import Document, SourceRevision
from app.db.source_structures import SourceStructure
from tests.csv_support import upload_csv
from tests.docx_support import mark, output
from tests.intake_support import _login


@pytest.mark.parametrize("delimiter", [",", ";", "\t", "|"])
def test_transient_preview_exact_unicode_bom_saved_encrypted_cell_map(intake_site, delimiter):
    owner, other, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    _login(other, "intake-other@example.invalid")
    canonical = f'\ufeffName{delimiter}Notes\r\n李{delimiter}"Said ""hi""\nand left"\r\n'
    source = "\ufeff" + canonical
    preview = owner.post(
        "/api/v1/documents/import-preview",
        data={"workspace_id": str(workspace), "csv_delimiter": delimiter},
        files={"file": ("fictional.csv", source.encode())},
        headers=headers,
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["text"] == canonical and preview.json()["csv"]["delimiter"] == delimiter
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count()).select_from(Document).where(Document.workspace_id == workspace)
            )
            == 0
        )
    base, state, saved = upload_csv(owner, headers, workspace, source, delimiter=delimiter)
    assert saved["text"] == canonical and saved["csv"]["columns"] == 2
    assert other.get(base + "/csv-settings").status_code == 404
    keys = KeyRing.from_settings(owner.app.state.settings)
    with Session(engine) as session:
        structure = session.get(SourceStructure, UUID(state["version"]["source_revision_id"]))
        assert structure.kind == "csv" and structure.block_count == 4
        assert canonical.encode() not in structure.layout_ciphertext
        payload = keys.decrypt_text(ProtectedValue(structure.layout_ciphertext, structure.key_id))
        assert "Said" not in payload and "Name" not in payload
        rules = session.get(DocumentColumnRules, (UUID(state["version"]["document_id"]), 1))
        assert keys.decrypt_text(ProtectedValue(rules.rules_ciphertext, rules.key_id)) == "[]"


def test_settings_reparse_same_immutable_revision_and_rejected_edit_atomic(intake_site):
    owner, other, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    other_headers = _login(other, "intake-other@example.invalid")
    source = "Name,City;Area\nAda,Oslo;North\n"
    base, state, _ = upload_csv(owner, headers, workspace, source)
    document_id, revision_id = (
        UUID(state["version"]["document_id"]),
        UUID(state["version"]["source_revision_id"]),
    )
    with Session(engine) as session:
        old_ciphertext = session.get(SourceStructure, revision_id).layout_ciphertext
    body = {"delimiter": ";", "has_header": True, "expected_settings_version": 1}
    assert (
        owner.put(
            base + "/csv-settings", json=body, headers={"Origin": headers["Origin"]}
        ).status_code
        == 403
    )
    assert other.put(base + "/csv-settings", json=body, headers=other_headers).status_code == 404
    changed = owner.put(base + "/csv-settings", json=body, headers=headers)
    assert changed.status_code == 200, changed.text
    version = changed.json()["version"]
    assert version["settings_version"] == 2 and version["source_revision_id"] == str(revision_id)
    assert owner.get(base + "/source").json()["status"] == "draft"
    assert owner.get(base + "/scan").json()["status"] == "not_started"
    assert owner.put(base + "/csv-settings", json=body, headers=headers).status_code == 409
    assert output(owner, headers, base, {"version": version}, "txt").status_code == 409
    rejected = owner.put(
        base + "/source",
        json={"expected": version, "source": "Name;City;Extra\nAda;Oslo;North\n"},
        headers=headers,
    )
    assert rejected.status_code == 422 and rejected.json()["code"] == "csv_structure_invalid"
    assert owner.get(base + "/source").json()["text"] == source
    assert owner.get(base + "/source").json()["version"] == version
    with Session(engine) as session:
        assert session.get(SourceStructure, revision_id).layout_ciphertext == old_ciphertext
        assert (
            session.scalar(
                select(func.count())
                .select_from(SourceRevision)
                .where(SourceRevision.document_id == document_id)
            )
            == 1
        )
    edited = owner.put(
        base + "/source",
        json={"expected": version, "source": source.replace("North", "South")},
        headers=headers,
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["structure"] == "kept"
    assert edited.json()["version"]["source_revision_id"] != str(revision_id)
    assert owner.get(base + "/source").json()["csv"]["delimiter"] == ";"


def test_detection_per_unescaped_cell_and_manual_escaped_pair_boundaries(intake_site):
    owner, _, _, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    source = 'Name,Email,SplitA,SplitB,Notes\r\nAda,"Said ""nora@example.test""",nora@,example.test,"line1\nline2"\r\n'
    base, state, _ = upload_csv(owner, headers, workspace, source, "email")
    assert len(state["findings"]) == 1
    finding = state["findings"][0]
    assert source[finding["span"]["start"] : finding["span"]["end"]] == "nora@example.test"
    for start, end, code in [
        (source.index('""'), source.index('""') + 1, "finding_splits_escape"),
        (
            source.index("nora@,example"),
            source.index("nora@,example") + len("nora@,example.test"),
            "finding_crosses_block",
        ),
    ]:
        rejected = owner.post(
            base + "/findings",
            json={
                "expected": state["version"],
                "span": {"start": start, "end": end},
                "category": "custom",
            },
            headers=headers,
        )
        assert rejected.status_code == 422 and rejected.json()["code"] == code
        assert owner.get(base + "/findings").json() == state
    changed = mark(owner, headers, base, state, source, "line1\nline2", "custom")
    assert len(changed["findings"]) == 2


@pytest.mark.parametrize(
    "data,code",
    [
        (b"Name,City\nPRIVATE_DATA\n", "csv_delimiter_unknown"),
        (b"Name,City\n\xff,b\n", "invalid_source"),
        (b"a" * 1048577, "invalid_source"),
    ],
    ids=["ragged", "invalid-utf8", "oversized"],
)
def test_invalid_imports_are_rejected_without_document_or_content_error(intake_site, data, code):
    owner, _, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    response = owner.post(
        "/api/v1/documents/from-file",
        data={"workspace_id": str(workspace)},
        files={"file": ("fictional.csv", data)},
        headers=headers,
    )
    assert response.status_code == 422 and response.json()["code"] == code
    assert "PRIVATE_DATA" not in response.text
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count()).select_from(Document).where(Document.workspace_id == workspace)
            )
            == 0
        )
