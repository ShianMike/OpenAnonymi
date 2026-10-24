"""Seed historical CSV records directly; the product no longer accepts CSV uploads."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.contracts import FindingCategory
from app.db.crypto import KeyRing
from app.db.repository import create_document
from app.intake.csv_service import change_csv_settings
from app.intake.csv_structure import parse_csv


def legacy_csv(owner, headers, workspace, source, categories="", *, delimiter="auto",
               header="auto", scan=True, preset=None):
    app = owner.app
    actor = UUID(owner.get("/api/v1/auth/session").json()["user_id"])
    parsed = parse_csv(source, delimiter, header)
    with Session(app.state.engine) as session:
        saved = create_document(
            session, owner_id=actor, workspace_id=workspace, source=parsed.source.text,
            validated_source=parsed.source, title=None,
            categories={FindingCategory(value) for value in categories.split(",") if value},
            phone_region="GB", keys=KeyRing.from_settings(app.state.settings), now=datetime.now(UTC),
            layout=parsed.layout, layout_kind="csv", preset_id=preset,
        )
    base = "/api/v1/documents/" + str(saved.version.document_id)
    if scan:
        result = owner.post(base + "/scan", json={"expected": saved.version.model_dump(mode="json")},
                            headers=headers)
        assert result.status_code == 200, result.text
    return base, owner.get(base + "/findings").json(), owner.get(base + "/source").json()


def set_legacy_rules(owner, headers, base, rules):
    app = owner.app
    actor = UUID(owner.get("/api/v1/auth/session").json()["user_id"])
    version = owner.get(base + "/source").json()["version"]
    result = change_csv_settings(
        app.state.engine, document_id=UUID(version["document_id"]), actor_id=actor,
        expected_settings_version=version["settings_version"], rules=rules, delimiter=None, has_header=None,
        keys=KeyRing.from_settings(app.state.settings), now=datetime.now(UTC),
    )
    return {**result, "version": result["version"].model_dump(mode="json")}
