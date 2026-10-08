"""Reusable real team/confirmation/scan cases; no fake service responses."""

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.team_review import FindingComment, ReviewApproval, ReviewHandoff
from tests.test_intake_lifecycle_access_pg import lifecycle_fingerprint
from tests.test_team_review_pg import _decision, _setup

OPERATIONS = (
    "handoff",
    "noop-handoff",
    "approval",
    "noop-approval",
    "comment",
    "noop-comment",
    "delete-comment",
    "confirm",
    "noop-confirm",
    "scan-settings",
    "noop-settings",
    "scan",
    "noop-scan",
)


def team_case(site, operation):
    owner, reviewer, engine, workspace, owner_id, reviewer_id, oh, rh, base, scanned = _setup(site)
    version, finding = scanned["version"], scanned["suggestions"][0]["finding_id"]
    case = {
        "client": owner,
        "owner": owner,
        "reviewer": reviewer,
        "engine": engine,
        "workspace": workspace,
        "actor": owner_id,
        "owner_id": owner_id,
        "reviewer_id": reviewer_id,
        "headers": oh,
        "owner_headers": oh,
        "reviewer_headers": rh,
        "base": base,
        "document_id": UUID(version["document_id"]),
        "finding_id": UUID(finding),
        "operation": operation,
    }
    if operation in (
        "noop-handoff",
        "approval",
        "noop-approval",
        "comment",
        "noop-comment",
        "delete-comment",
    ):
        assigned = owner.put(
            base + "/handoff",
            headers=oh,
            json={"expected": version, "reviewer_id": str(reviewer_id), "require_approval": True},
        )
        assert assigned.status_code == 200
        version = assigned.json()["version"]
    if operation in ("approval", "noop-approval", "confirm", "noop-confirm"):
        version = _decision(owner, base, finding, version, oh)
    body = {"expected": version}
    if operation in ("approval", "noop-approval", "noop-confirm"):
        completed = owner.post(
            base + "/complete", headers=oh, json={"expected": version, "confirmed_preview": True}
        )
        assert completed.status_code == 200
    if "handoff" in operation:
        body.update(reviewer_id=str(reviewer_id), require_approval=True)
        case["suffix"] = "/handoff"
    elif "approval" in operation:
        body["confirmed_preview"] = True
        case.update(client=reviewer, actor=reviewer_id, headers=rh, suffix="/approval")
        if operation == "noop-approval":
            assert reviewer.post(base + "/approval", headers=rh, json=body).status_code == 200
    elif "comment" in operation:
        case.update(client=reviewer, actor=reviewer_id, headers=rh)
        body.update(id=str(uuid4()), text="Fictional private discussion Café 東京")
        case["suffix"] = f"/findings/{finding}/comments"
        if operation in ("noop-comment", "delete-comment"):
            assert reviewer.post(base + case["suffix"], headers=rh, json=body).status_code == 201
            case["comment_id"] = UUID(body["id"])
            if operation == "delete-comment":
                case["suffix"] = "/comments/" + body["id"]
    elif "confirm" in operation:
        case["suffix"] = "/complete"
        body["confirmed_preview"] = True
    elif operation in ("scan-settings", "noop-settings"):
        case["suffix"] = "/scan-settings"
        body.update(
            categories=["email"] if operation == "noop-settings" else ["email", "url"],
            phone_region="PH",
            language="en",
        )
    else:
        case["suffix"] = "/scan"
        if operation == "scan":
            changed = owner.put(
                base + "/scan-settings",
                headers=oh,
                json={
                    **body,
                    "categories": ["email", "url"],
                    "phone_region": "PH",
                    "language": "en",
                },
            )
            assert changed.status_code == 200
            body["expected"] = changed.json()["version"]
    case["body"] = body
    return case


def team_perform(case):
    method = (
        "DELETE"
        if case["operation"] == "delete-comment"
        else "PUT"
        if case["operation"] in ("handoff", "noop-handoff", "scan-settings", "noop-settings")
        else "POST"
    )
    return case["client"].request(
        method,
        case["base"] + case["suffix"],
        headers=case["headers"],
        json=None if method == "DELETE" else case["body"],
    )


def team_fingerprint(case):
    from app.db.notifications import Notification

    with Session(case["engine"]) as session:
        models = (FindingComment, ReviewApproval, ReviewHandoff, Notification)
        rows = [
            sorted(
                [
                    tuple(getattr(row, column.name) for column in model.__table__.columns)
                    for row in session.scalars(
                        select(model).where(model.document_id == case["document_id"])
                    )
                ],
                key=repr,
            )
            for model in models
        ]
    return lifecycle_fingerprint(case), rows


def after_team(monkeypatch, case, change):
    from app.detection import service as detection
    from app.reviews import service as reviews
    from app.team_review import comments, service

    operation = case["operation"]
    if "handoff" in operation or "approval" in operation:
        module, hook = service, "_view"
    elif operation == "delete-comment":
        module, hook = Session, "flush"
    elif "comment" in operation:
        module, hook = comments, "_view"
    elif "confirm" in operation:
        module, hook = (
            reviews,
            "current_completion" if operation == "noop-confirm" else "record_event",
        )
    elif operation == "scan":
        module, hook = detection, "detect_suggestions"
    elif operation == "noop-scan":
        module, hook = detection, "_snapshot"
    else:
        module, hook = (
            detection,
            "_version" if operation == "noop-settings" else "invalidate_scan_settings",
        )
    original, fired = getattr(module, hook), []

    def changed(*args, **kwargs):
        ready = True
        if operation == "delete-comment":
            ready = any(
                isinstance(row, FindingComment) and row.id == case["comment_id"]
                for row in args[0].deleted
            )
        if hook == "record_event":
            ready = kwargs.get("event_code") == "review_completed"
        result = original(*args, **kwargs)
        if ready and not fired:
            fired.append(True)
            change()
        return result

    monkeypatch.setattr(module, hook, changed)
    return fired
