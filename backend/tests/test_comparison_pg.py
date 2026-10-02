from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.cleanup.service import purge_unavailable_content
from app.db.models import Document, Membership
from app.factory import create_app
from tests.intake_support import _draft_body, _login


def test_protected_comparison_authorization_missing_keys_and_expiry(intake_site):
    owner, other, engine, workspace, owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    _login(other, "intake-other@example.invalid")
    left = "😀 Café 東京\r\nOld line\nEnd"
    right = "😀 Café 東京\r\nNew line\nEnd"
    first = owner.post(
        "/api/v1/documents", json=_draft_body(workspace, source=left), headers=headers
    ).json()["version"]
    base = f"/api/v1/documents/{first['document_id']}"
    second = owner.put(
        base + "/source", json={"expected": first, "source": right}, headers=headers
    ).json()["version"]
    query = {"before": first["source_revision_id"], "after": second["source_revision_id"]}
    result = owner.get(base + "/compare", params=query)
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store"
    data = result.json()
    assert "".join(block["left_text"] for block in data["blocks"]) == left
    assert "".join(block["right_text"] for block in data["blocks"]) == right
    assert data["changes"] == 1 and data["before"]["number"] == 1 and data["after"]["number"] == 2
    assert owner.get(base + "/source").json()["version"] == second
    assert owner.get(base + f"/revisions/{first['source_revision_id']}/source").status_code == 404
    other_id = UUID(other.get("/api/v1/auth/session").json()["user_id"])
    with Session(engine) as session, session.begin():
        session.get(Membership, (workspace, other_id)).role = "administrator"
    assert other.get(base + "/compare", params=query).status_code == 404
    foreign = other.post(
        "/api/v1/documents",
        json=_draft_body(workspace),
        headers=_login(other, "intake-other@example.invalid"),
    ).json()["version"]
    assert (
        owner.get(
            base + "/compare", params={**query, "before": foreign["source_revision_id"]}
        ).status_code
        == 404
    )
    assert owner.get(base + "/compare", params={**query, "after": str(uuid4())}).status_code == 404
    settings = owner.app.state.settings.model_copy(
        update={"active_key_id": None, "content_keys": {}}
    )
    with TestClient(create_app(settings, engine=engine)) as no_keys:
        _login(no_keys, "intake-owner@example.invalid")
        failed = no_keys.get(base + "/compare", params=query)
        assert failed.status_code == 503 and "Café" not in failed.text
    with Session(engine) as session, session.begin():
        doc = session.get(Document, first["document_id"])
        doc.created_at = datetime.now(UTC) - timedelta(days=10)
        doc.expires_at = datetime.now(UTC) - timedelta(days=1)
    assert owner.get(base + "/compare", params=query).status_code == 410
    purge_unavailable_content(engine, now=datetime.now(UTC))
    assert owner.get(base + "/compare", params=query).status_code == 410
    assert owner_id
