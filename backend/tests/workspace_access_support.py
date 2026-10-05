"""Real workspace rule, preset, snapshot and title operations for access tests."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.custom_rules import DocumentRuleSnapshot, RuleVersion, WorkspaceRule
from app.db.models import AuditEvent, Document, Preset
from tests.intake_support import _draft_body
from tests.test_custom_rules_pg import RULE, admin_headers

OPERATIONS = (
    "rules-read",
    "rule-create",
    "rule-update",
    "rule-test",
    "snapshot-read",
    "snapshot-refresh",
    "snapshot-unchanged",
    "presets-read",
    "preset-create",
    "preset-update",
    "document-index",
    "document-search",
)
PRIVATE_RULE = {
    **RULE,
    "name": "Fictional private rule",
    "kind": "phrase",
    "expression": "Fictional private phrase",
}
PRIVATE_PRESET = {
    "name": "Fictional private preset",
    "categories": ["email"],
    "phone_region": "PH",
    "column_rules": [{"column": 0, "header": "Fictional protected header", "mode": "scan"}],
}


def workspace_case(site, operation):
    client, _, engine, workspace, actor = site
    headers = admin_headers(site)
    rules = f"/api/v1/workspaces/{workspace}/rules"
    presets = f"/api/v1/workspaces/{workspace}/presets"
    rule = client.post(rules, headers=headers, json=PRIVATE_RULE)
    preset = client.post(presets, headers=headers, json=PRIVATE_PRESET)
    assert rule.status_code == preset.status_code == 201
    document = client.post(
        "/api/v1/documents",
        headers=headers,
        json=_draft_body(
            workspace,
            title="Fictional protected title",
            source=PRIVATE_RULE["expression"],
            categories=[],
        ),
    )
    assert document.status_code == 201
    version = document.json()["version"]
    case = {
        "client": client,
        "engine": engine,
        "workspace": workspace,
        "actor": actor,
        "headers": headers,
        "document_id": UUID(version["document_id"]),
        "operation": operation,
        "expected": version,
        "rule_id": UUID(rule.json()["id"]),
        "preset_id": UUID(preset.json()["id"]),
    }
    if operation == "rules-read":
        case.update(method="GET", path=rules)
    elif operation == "rule-create":
        case.update(
            method="POST", path=rules, body={**PRIVATE_RULE, "name": "Fictional second rule"}
        )
    elif operation == "rule-update":
        case.update(
            method="PUT",
            path=rules + "/" + rule.json()["id"],
            body={**PRIVATE_RULE, "expression": "Fictional edited phrase", "expected_version": 1},
        )
    elif operation == "rule-test":
        case.update(
            method="POST",
            path=rules + "/test",
            body={"rule": PRIVATE_RULE, "text": PRIVATE_RULE["expression"]},
        )
    elif operation.startswith("snapshot"):
        case.update(
            method="GET" if operation == "snapshot-read" else "PUT",
            path=f"/api/v1/documents/{case['document_id']}/rules",
            body={"expected": version},
        )
        if operation == "snapshot-refresh":
            changed = client.put(
                rules + "/" + rule.json()["id"],
                headers=headers,
                json={
                    **PRIVATE_RULE,
                    "expression": "Fictional latest phrase",
                    "expected_version": 1,
                },
            )
            assert changed.status_code == 200
    elif operation == "presets-read":
        case.update(method="GET", path=presets)
    elif operation == "preset-create":
        case.update(
            method="POST", path=presets, body={**PRIVATE_PRESET, "name": "Fictional second preset"}
        )
    elif operation == "preset-update":
        case.update(
            method="PUT",
            path=presets + "/" + preset.json()["id"],
            body={**PRIVATE_PRESET, "name": "Fictional edited preset", "expected_version": 1},
        )
    elif operation == "document-index":
        case.update(method="GET", path=f"/api/v1/workspaces/{workspace}/documents")
    else:
        case.update(
            method="POST", path="/api/v1/search/documents", body={"workspace_id": str(workspace)}
        )
    return case


def perform(case):
    return case["client"].request(
        case["method"],
        case["path"],
        headers=case["headers"],
        json=None if case["method"] == "GET" else case["body"],
    )


def fingerprint(case):
    with Session(case["engine"]) as session:
        queries = (
            (WorkspaceRule, WorkspaceRule.workspace_id == case["workspace"]),
            (
                RuleVersion,
                RuleVersion.rule_id.in_(
                    select(WorkspaceRule.id).where(WorkspaceRule.workspace_id == case["workspace"])
                ),
            ),
            (Preset, Preset.workspace_id == case["workspace"]),
            (DocumentRuleSnapshot, DocumentRuleSnapshot.document_id == case["document_id"]),
            (Document, Document.id == case["document_id"]),
            (AuditEvent, AuditEvent.workspace_id == case["workspace"]),
        )
        return tuple(
            tuple(
                sorted(
                    [
                        tuple(getattr(row, column.name) for column in model.__table__.columns)
                        for row in session.scalars(select(model).where(condition))
                    ],
                    key=repr,
                )
            )
            for model, condition in queries
        )


def after_actual_work(monkeypatch, case, change):
    from app.custom_rules import api, service
    from app.workspace import api as workspace_api
    from app.workspace import organize_api, presets, presets_api

    operation = case["operation"]
    if operation == "rules-read":
        module, hook = api, "workspace_rules"
    elif operation.startswith("rule-") and operation != "rule-test":
        module, hook = service, "rule_view"
    elif operation == "rule-test":
        module, hook = api, "matches"
    elif operation == "snapshot-read":
        module, hook = api, "snapshot_state"
    elif operation.startswith("snapshot"):
        module, hook = service, "snapshot_state"
    elif operation == "presets-read":
        module, hook = presets_api, "list_presets"
    elif operation.startswith("preset"):
        module, hook = presets, "_record"
    elif operation == "document-index":
        module, hook = workspace_api.DocumentIndexView, "model_validate"
    else:
        module, hook = organize_api, "search_documents"
    original, fired = getattr(module, hook), []

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        # A changed snapshot first checks update availability; hook the final
        # actual result after its persisted settings/version have been prepared.
        ready = (
            operation != "snapshot-refresh"
            or result.version.settings_version > case["expected"]["settings_version"]
        )
        if ready and not fired:
            fired.append(True)
            change()
        return result

    monkeypatch.setattr(module, hook, changed)
    return fired
