"""CSV is rejected at both import entry points without storing private content."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Document
from tests.intake_support import _login


@pytest.mark.parametrize("route", ["import-preview", "from-file"])
@pytest.mark.parametrize("filename", ["fictional.csv", "FICTIONAL.CSV"])
def test_csv_import_is_rejected_without_creating_a_document(intake_site, route, filename):
    owner, _, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    with Session(engine) as session:
        before = session.scalar(select(func.count()).select_from(Document))
    response = owner.post(
        "/api/v1/documents/" + route, data={"workspace_id": str(workspace)},
        files={"file": (filename, b"PRIVATE_CANARY,Email\nNora,nora@example.test\n", "text/csv")},
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["code"] == ("invalid_file" if route == "import-preview" else "invalid_source")
    assert "PRIVATE_CANARY" not in response.text and "nora@example.test" not in response.text
    assert "TXT" in response.json()["message"]
    assert response.headers["cache-control"] == "no-store"
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Document)) == before
