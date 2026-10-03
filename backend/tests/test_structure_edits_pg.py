from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db.crypto import KeyRing
from app.db.rotate_keys import rotate_source_structures, rotate_sources
from app.db.source_structures import SourceStructure, load_word
from app.intake.structure import InvalidLayout, joined_text
from tests.docx_fixtures import simple_docx
from tests.docx_support import upload
from tests.intake_support import _login


def test_leaf_edit_retains_layout_immutable_old_spans_and_rotation(intake_site):
    owner, other, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    rh = _login(other, "intake-other@example.invalid")
    base, state, source = upload(owner, headers, workspace, simple_docx("😀 Nora", "Next block"))
    old_id = UUID(state["version"]["source_revision_id"])
    old = KeyRing.from_settings(owner.app.state.settings)
    with Session(engine) as session:
        row = session.get(SourceStructure, old_id)
        original_ciphertext = row.layout_ciphertext
        original = load_word(session, old_id, old, len(source["text"]), source["text"])
        assert row.layout_ciphertext.startswith(b"gAAAA") and b"blocks" not in row.layout_ciphertext
    body = {"expected": state["version"], "source": source["text"].replace("Nora", "Nora Caldwell")}
    assert other.put(base + "/source", json=body, headers=rh).status_code == 404
    saved = owner.put(base + "/source", json=body, headers=headers)
    assert saved.status_code == 200 and saved.json()["structure"] == "kept"
    assert owner.put(base + "/source", json=body, headers=headers).status_code == 409
    new_id = UUID(saved.json()["version"]["source_revision_id"])
    with Session(engine) as session:
        assert session.get(SourceStructure, old_id).layout_ciphertext == original_ciphertext
        assert (
            joined_text(
                load_word(session, new_id, old, len(body["source"]), body["source"]), body["source"]
            )
            == body["source"]
        )
        assert load_word(session, old_id, old, len(source["text"]), source["text"]) == original
        row = session.get(SourceStructure, old_id)
        row.layout_ciphertext = old.encrypt_text("{}").ciphertext
        with pytest.raises(InvalidLayout, match="immutable"):
            session.flush()
        session.rollback()
    with Session(engine) as session:
        with pytest.raises(DBAPIError, match="immutable"):
            session.execute(
                text("UPDATE source_structures SET block_count=1 WHERE revision_id=:id"),
                {"id": old_id},
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
        assert rotate_source_structures(session, new) == 2
        assert rotate_sources(session, new) >= 2
    with Session(engine) as session:
        assert load_word(session, old_id, new, len(source["text"]), source["text"]) == original
        assert session.get(SourceStructure, old_id).layout_ciphertext != original_ciphertext
    owner.app.state.settings.active_key_id = "new"
    owner.app.state.settings.content_keys = {"new": SecretStr(new_value.decode())}
    assert owner.get(base + "/source").status_code == 200


@pytest.mark.parametrize(
    "changed",
    [
        "😀 Nora\tCaldwell\nNext block",
        "😀 Nora\nInserted\nNext block",
        "😀 Nora Next block",
        "X Nora\nNext note",
    ],
)
def test_boundary_or_multiple_leaf_edits_simplify_without_rewriting_earlier_layout(
    intake_site, changed
):
    owner, _, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    base, state, _ = upload(owner, headers, workspace, simple_docx("😀 Nora", "Next block"))
    result = owner.put(
        base + "/source", json={"expected": state["version"], "source": changed}, headers=headers
    )
    assert result.status_code == 200 and result.json()["structure"] == "simplified"
    with Session(engine) as session:
        assert (
            session.get(SourceStructure, UUID(state["version"]["source_revision_id"])) is not None
        )
        assert (
            session.get(SourceStructure, UUID(result.json()["version"]["source_revision_id"]))
            is None
        )
    assert owner.get(base + "/source").json()["text"] == changed
    assert owner.get(base + "/findings").json()["findings"] == []
