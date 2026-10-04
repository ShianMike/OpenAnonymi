"""The same seven authored stand-ins through real review and both CSV variants."""

import csv
import io
import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.db.crypto import KeyRing
from app.db.models import EntityGroup, Finding
from app.db.replacement_secrets import DocumentReplacementSecret
from tests.csv_support import upload_csv
from tests.docx_fixtures import read_word
from tests.docx_support import confirm, mark, output
from tests.intake_support import _login
from tests.style_fixtures import STAND_IN_FIXTURES
from tests.styles_support import decide


@pytest.mark.parametrize(
    "index,fixture", list(enumerate(STAND_IN_FIXTURES)), ids=[row[0] for row in STAND_IN_FIXTURES]
)
def test_authored_standin_fixture_matches_preview_copy_txt_word_and_csv(
    intake_site, index, fixture
):
    category, value, expected = fixture
    if category == "phone":
        # The authored E.164 fixture keeps the original international spacing
        # when presented in a reviewed document.
        expected = "+44 7700 900686"
    owner, _, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    source = f"Value,Other\n😀 {value},Unmarked\n"
    base, state, _ = upload_csv(owner, headers, workspace, source)
    state = mark(owner, headers, base, state, source, value, category)
    finding = state["findings"][0]
    document_id = UUID(state["version"]["document_id"])
    protected = KeyRing.from_settings(owner.app.state.settings).encrypt_text(
        json.dumps({"version": 1, "seed": bytes(32).hex(), "offset": 30})
    )
    # Only deterministic fixture seed/identity is prepared directly in the owned
    # database. Decisions, confirmation, authorization and serialization are real.
    with Session(engine) as session, session.begin():
        group = EntityGroup(
            id=UUID(int=index + 1),
            document_id=document_id,
            source_revision_id=UUID(state["version"]["source_revision_id"]),
            category=category,
            label=category.upper() + "_001",
        )
        session.add(group)
        session.flush()
        session.get(Finding, UUID(finding["finding_id"])).group_id = group.id
        session.add(
            DocumentReplacementSecret(
                document_id=document_id,
                secret_ciphertext=protected.ciphertext,
                key_id=protected.key_id,
                created_at=datetime.now(UTC),
            )
        )
    saved = decide(owner, headers, base, state, finding, "label", "stand_in")
    assert saved.status_code == 200
    state = saved.json()
    preview = owner.get(base + "/preview").json()
    assert preview["text"] == f"Value,Other\n😀 {expected},Unmarked\n"
    confirm(owner, headers, base, state)
    copy = owner.post(
        base + "/exports/copy-payload", json={"expected": state["version"]}, headers=headers
    )
    assert copy.status_code == 200 and copy.json()["text"] == preview["text"]
    txt = output(owner, headers, base, state, "txt")
    assert txt.status_code == 200 and txt.content == preview["text"].encode()
    word = output(owner, headers, base, state, "docx")
    assert word.status_code == 200 and read_word(word.content)[0] == preview["text"]
    for variant in ("spreadsheet_safe", "unmodified"):
        from uuid import uuid4

        exported = owner.post(
            base + "/exports/csv",
            json={"expected": state["version"], "event_id": str(uuid4()), "variant": variant},
            headers=headers,
        )
        assert exported.status_code == 200
        assert list(csv.reader(io.StringIO(exported.content.decode("utf-8-sig"), newline=""))) == [
            ["Value", "Other"],
            ["😀 " + expected, "Unmarked"],
        ]
