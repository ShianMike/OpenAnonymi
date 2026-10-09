"""Flag metadata and live reviewer grants must share the final database read."""
import inspect
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import delete, event, select
from sqlalchemy.orm import Session

from app.db.document_preferences import DocumentPreference
from app.db.models import Document, User
from app.db.team_review import ReviewHandoff
from tests.intake_support import _login
from tests.reporting_access_support import make_case, perform
from tests.test_document_organization_pg import draft
from tests.test_reporting_access_pg import denied


def reviewer_case(site, operation, count=1):
    case = make_case(site, operation)
    owner = case["client"]
    docs = [case["document"]]
    docs.extend(UUID(draft(owner, case["headers"], case["workspace"], "Synthetic flags"))
                for _ in range(count - 1))
    other = site[1]
    case["client"], case["headers"] = other, _login(other, "intake-other@example.invalid")
    with Session(case["engine"]) as session, session.begin():
        case["actor"] = session.scalar(select(User.id).where(User.email == "intake-other@example.invalid"))
        session.add_all(ReviewHandoff(document_id=doc, reviewer_id=case["actor"], generation=1) for doc in docs)
    if operation == "bulk-preference":
        case["body"]["document_ids"] = [str(doc) for doc in docs]
    case["documents"] = docs
    return case


def watch_flag_read(case, change):
    fired = []

    def before(connection, cursor, statement, parameters, context, executemany):
        if (not fired and statement.lstrip().lower().startswith("select")
                and "document_preferences" in statement
                and any(frame.function == "authorize" and frame.filename.endswith("organize_api.py")
                        for frame in inspect.stack())):
            fired.append(True)
            change()

    event.listen(case["engine"], "before_cursor_execute", before)
    return fired, lambda: event.remove(case["engine"], "before_cursor_execute", before)


def lose_document(case, change):
    with Session(case["engine"]) as session, session.begin():
        if change == "handoff":
            session.execute(delete(ReviewHandoff).where(ReviewHandoff.document_id == case["document"]))
        else:
            row = session.get(Document, case["document"])
            row.created_at = datetime.now(UTC) - timedelta(days=2)
            row.expires_at = datetime.now(UTC) - timedelta(days=1)


@pytest.mark.parametrize("operation", ("preference", "bulk-preference"))
@pytest.mark.parametrize("change", ("handoff", "expiry"))
def test_final_flag_read_also_checks_current_grant_and_content(intake_site, operation, change):
    case = reviewer_case(intake_site, operation)
    fired, remove = watch_flag_read(case, lambda: lose_document(case, change))
    try:
        denied(perform(case), 404 if change == "handoff" else 410)
    finally:
        remove()
    assert fired and case["client"].get("/api/v1/auth/session").status_code == 200
    with Session(case["engine"]) as session:
        # The authorized write preceded the response guard and remains committed.
        assert session.get(DocumentPreference, (case["actor"], case["document"])).favorite


@pytest.mark.parametrize("change", ("handoff", "expiry"))
def test_bulk_checks_all_updated_flags_and_grants_together(intake_site, change):
    case = reviewer_case(intake_site, "bulk-preference", count=3)
    fired, remove = watch_flag_read(case, lambda: lose_document(case, change))
    try:
        denied(perform(case), 404 if change == "handoff" else 410)
    finally:
        remove()
    assert fired
    with Session(case["engine"]) as session:
        assert all(session.get(DocumentPreference, (case["actor"], doc)).favorite for doc in case["documents"])


def test_bulk_fifty_current_flag_rows_use_one_authorized_read(intake_site):
    case = reviewer_case(intake_site, "bulk-preference", count=50)
    queries = []

    def after(connection, cursor, statement, parameters, context, executemany):
        if (statement.lstrip().lower().startswith("select") and "document_preferences" in statement
                and any(frame.function == "authorize" and frame.filename.endswith("organize_api.py")
                        for frame in inspect.stack())):
            queries.append(statement)

    event.listen(case["engine"], "after_cursor_execute", after)
    try:
        response = perform(case)
    finally:
        event.remove(case["engine"], "after_cursor_execute", after)
    assert response.status_code == 200 and len(response.json()["outcomes"]) == 50
    assert all(row["favorite"] and not row["pinned"] for row in response.json()["outcomes"])
    assert len(queries) == 1 and "review_handoffs" in queries[0]
