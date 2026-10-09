"""Genuine document flags, deletion, retention and reporting requests."""
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.accounts.security import _digest
from app.db.document_preferences import DocumentPreference
from app.db.models import AuditEvent, Document, SourceRevision
from app.db.models import Session as StoredSession
from tests.intake_support import _draft_body
from tests.test_custom_rules_pg import admin_headers

WRITES = ("preference", "bulk-preference", "bulk-delete", "retention-renew")
READS = ("overview", "activity", "admin-activity", "retention-read", "preference")


def make_case(site, operation):
    client, _, engine, workspace, actor = site
    headers = admin_headers(site)
    response = client.post("/api/v1/documents", headers=headers, json=_draft_body(workspace))
    assert response.status_code == 201
    doc = UUID(response.json()["version"]["document_id"])
    with Session(engine) as session:
        current = session.scalar(select(StoredSession.id).where(
            StoredSession.token_hash == _digest(client.cookies.get("openanonymi_session"))))
    path, method, body = f"/api/v1/workspaces/{workspace}/" + operation, "GET", None
    if operation == "admin-activity":
        path, method, body = f"/api/v1/workspaces/{workspace}/activity/admin", "POST", {"days":30}
    elif operation.startswith("retention"):
        path = f"/api/v1/documents/{doc}/retention"
        if operation.endswith("renew"):
            view = client.get(path).json()
            method, body = "PATCH", {"expected_expires_at":view["expires_at"],"days_from_now":7}
    elif operation == "preference":
        path, method, body = f"/api/v1/documents/{doc}/preferences", "PATCH", {"favorite":True}
    elif operation.startswith("bulk"):
        path, method, body = f"/api/v1/workspaces/{workspace}/documents/bulk", "POST", {
            "document_ids":[str(doc)],"action":"delete" if operation == "bulk-delete" else "favorite"}
    return {"client":client,"engine":engine,"workspace":workspace,"actor":actor,"document":doc,
        "current_session":current,"headers":headers,"operation":operation,"path":path,"method":method,"body":body}


def perform(case):
    return case["client"].request(case["method"], case["path"], headers=case["headers"], json=case["body"])


def revoke(case):
    with Session(case["engine"]) as session, session.begin():
        session.get(StoredSession, case["current_session"]).revoked_at = datetime.now(UTC)


def state(case):
    with Session(case["engine"]) as session:
        return tuple(tuple(sorted([tuple(getattr(row, col.name) for col in model.__table__.columns)
            for row in session.scalars(select(model).where(condition))], key=repr)) for model, condition in (
                (Document, Document.id == case["document"]),
                (SourceRevision, SourceRevision.document_id == case["document"]),
                (DocumentPreference, DocumentPreference.document_id == case["document"]),
                (AuditEvent, AuditEvent.document_id == case["document"])))


def watch_prepared(case, change):
    fired = []
    table_name = "document_preferences" if "preference" in case["operation"] else "documents"
    def after(connection, cursor, statement, parameters, context, executemany):
        clause = getattr(getattr(context,"compiled",None),"statement",None)
        if not fired and getattr(getattr(clause,"table",None),"name",None) == table_name and (
            getattr(clause,"is_insert",False) or getattr(clause,"is_update",False) or getattr(clause,"is_delete",False)
        ):
            fired.append(True)
            change()
    event.listen(case["engine"], "after_cursor_execute", after)
    return fired, lambda: event.remove(case["engine"], "after_cursor_execute", after)


def after_json(monkeypatch, case, change):
    from app.workspace import admin_activity, api, organize, retention

    operation = case["operation"]
    model = (api.OverviewView if operation == "overview" else api.ActivityView if operation == "activity" else
             admin_activity.AdminActivityView if operation == "admin-activity" else
             retention.RetentionView if operation.startswith("retention") else
             organize.DocumentPreferenceView if operation == "preference" else organize.BulkDocumentsView)
    original, fired = model.model_dump_json, []
    def serialized(*args, **kwargs):
        payload = original(*args, **kwargs)
        if not fired:
            fired.append(True)
            change()
        return payload
    monkeypatch.setattr(model,"model_dump_json",serialized)
    return fired
