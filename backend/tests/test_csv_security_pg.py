"""Protected CSV snapshots, immutable updates, rotation and retention gates."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.cleanup.service import purge_unavailable_content
from app.db.column_rules import DocumentColumnRules, load_preset_rules, load_rules
from app.db.crypto import KeyRing
from app.db.models import Document, Membership, Preset
from app.db.rotate_keys import (
    rotate_column_rules,
    rotate_preset_columns,
    rotate_source_structures,
    rotate_sources,
)
from app.db.source_structures import SourceStructure
from app.intake.csv_structure import CsvError
from tests.csv_support import set_rules, upload_csv
from tests.intake_support import _login


def admin_preset(owner, headers, engine, workspace, actor):
    with Session(engine) as session, session.begin():
        session.get(Membership, (workspace, actor)).role = "administrator"
    response = owner.post(
        f"/api/v1/workspaces/{workspace}/presets",
        json={
            "name": "CSV rotation",
            "categories": [],
            "phone_region": "GB",
            "column_rules": [
                {"column": 0, "header": "Name", "mode": "category", "category": "person"}
            ],
        },
        headers=headers,
    )
    assert response.status_code == 201
    return UUID(response.json()["id"])


def test_csv_rules_and_maps_immutable_rotated_readable_with_only_new_key_then_purged(intake_site):
    owner, _, engine, workspace, actor = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    preset_id = admin_preset(owner, headers, engine, workspace, actor)
    source = "Name,Notes\nAda,東京\n"
    base, state, saved = upload_csv(owner, headers, workspace, source, scan=False, preset=preset_id)
    result = set_rules(
        owner, headers, base, [{"column": 0, "mode": "keep", "keep_reason": "intended_disclosure"}]
    )
    assert result.status_code == 200
    edited = owner.put(
        base + "/source",
        json={"expected": result.json()["version"], "source": source.replace("Ada", "😀 Ada")},
        headers=headers,
    )
    assert edited.status_code == 200
    document_id = UUID(state["version"]["document_id"])
    old = KeyRing.from_settings(owner.app.state.settings)
    with Session(engine) as session:
        document = session.get(Document, document_id)
        rules = load_rules(session, document, old)
        preset_rules = load_preset_rules(session.get(Preset, preset_id), old)
        rows = session.scalars(
            select(DocumentColumnRules)
            .where(DocumentColumnRules.document_id == document_id)
            .order_by(DocumentColumnRules.settings_version)
        ).all()
        ciphers = [row.rules_ciphertext for row in rows]
        assert len(rows) == 2
        rows[0].rules_ciphertext = old.encrypt_text("[]").ciphertext
        with pytest.raises(CsvError, match="immutable"):
            session.flush()
        session.rollback()
    with Session(engine) as session:
        with pytest.raises(DBAPIError, match="immutable"):
            session.execute(
                text("UPDATE document_column_rules SET csv_has_header=false WHERE document_id=:id"),
                {"id": document_id},
            )
        session.rollback()
    new_value = Fernet.generate_key()
    new = KeyRing(
        "new",
        {
            "test": owner.app.state.settings.content_keys["test"].get_secret_value().encode(),
            "new": new_value,
        },
    )
    with Session(engine) as session, session.begin():
        session.info["allow_source_key_rotation"] = True
        session.execute(text("SET LOCAL openanonymi.key_rotation='on'"))
        assert rotate_column_rules(session, new) == 2
        assert rotate_preset_columns(session, new) == 1
        assert rotate_source_structures(session, new) == 2
        assert rotate_sources(session, new) == 2
    with Session(engine) as session:
        assert load_rules(session, session.get(Document, document_id), new) == rules
        assert load_preset_rules(session.get(Preset, preset_id), new) == preset_rules
        rows = session.scalars(
            select(DocumentColumnRules)
            .where(DocumentColumnRules.document_id == document_id)
            .order_by(DocumentColumnRules.settings_version)
        ).all()
        assert all(
            row.key_id == "new" and row.rules_ciphertext != previous
            for row, previous in zip(rows, ciphers, strict=True)
        )
    owner.app.state.settings.active_key_id = "new"
    owner.app.state.settings.content_keys = {"new": SecretStr(new_value.decode())}
    assert owner.get(base + "/source").json()["csv"]["rules"] == rules
    with Session(engine) as session, session.begin():
        document = session.get(Document, document_id)
        document.created_at = datetime.now(UTC) - timedelta(days=2)
        document.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    for path in ("/source", "/csv-settings", "/column-rules"):
        assert owner.get(base + path).status_code == 410
    assert (
        purge_unavailable_content(engine, now=datetime.now(UTC), batch_size=100).documents_purged
        == 1
    )
    with Session(engine) as session:
        assert (
            session.scalars(
                select(DocumentColumnRules).where(DocumentColumnRules.document_id == document_id)
            ).all()
            == []
        )
        assert session.get(SourceStructure, UUID(saved["version"]["source_revision_id"])) is None
        assert (
            session.get(SourceStructure, UUID(edited.json()["version"]["source_revision_id"]))
            is None
        )
        assert load_preset_rules(session.get(Preset, preset_id), new) == preset_rules


@pytest.mark.parametrize("protected", ["map", "rules", "preset"])
def test_corrupt_protected_csv_content_is_generic_503_and_cannot_import_or_review(
    intake_site, protected
):
    owner, _, engine, workspace, actor = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    preset_id = admin_preset(owner, headers, engine, workspace, actor)
    base, state, _ = upload_csv(
        owner, headers, workspace, "Name,Other\nAda,value\n", scan=False, preset=preset_id
    )
    with Session(engine) as session, session.begin():
        session.info["allow_source_key_rotation"] = True
        session.execute(text("SET LOCAL openanonymi.key_rotation='on'"))
        if protected == "map":
            session.get(
                SourceStructure, UUID(state["version"]["source_revision_id"])
            ).layout_ciphertext = b"invalid-ciphertext"
        elif protected == "rules":
            session.get(
                DocumentColumnRules, (UUID(state["version"]["document_id"]), 1)
            ).rules_ciphertext = b"invalid-ciphertext"
        else:
            session.get(Preset, preset_id).column_rules_ciphertext = b"invalid-ciphertext"
    if protected == "preset":
        response = owner.post(
            "/api/v1/documents/from-file",
            data={"workspace_id": str(workspace), "preset_id": str(preset_id)},
            files={"file": ("fictional.csv", b"Name,Other\nAda,value\n", "text/csv")},
            headers=headers,
        )
    else:
        response = owner.get(base + "/source")
        denied = owner.post(base + "/scan", json={"expected": state["version"]}, headers=headers)
        assert denied.status_code == 503
    assert response.status_code == 503
    assert (
        "Ada" not in response.text
        and "ciphertext" not in response.text
        and "Name" not in response.text
    )
