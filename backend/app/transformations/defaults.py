"""Content-free category defaults; snapshots never record review decisions."""

import copy
from datetime import datetime
from uuid import UUID

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import owned_document
from app.contracts import FindingCategory
from app.db.models import Preset
from app.db.repository import VersionConflict
from app.groups.service import ReviewValidationError, _snapshot, _touch_review, _version
from app.groups.undo_store import clear_document
from app.transformations.styles import validate_style
from app.workspace.activity import record_event


def validate_defaults(value: dict | None) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict) or len(value) > len(FindingCategory):
        raise ValueError("Choose supported per-category defaults.")
    result = {}
    for category, choice in value.items():
        if (
            category not in {item.value for item in FindingCategory}
            or not isinstance(choice, dict)
            or set(choice) - {"action", "style", "style_option"}
        ):
            raise ValueError("Choose supported per-category defaults.")
        action, style, option = (
            choice.get("action"),
            choice.get("style", "token"),
            choice.get("style_option"),
        )
        if (
            not isinstance(action, str)
            or not isinstance(style, str)
            or (option is not None and not isinstance(option, str))
        ):
            raise ValueError("Choose supported per-category defaults.")
        validate_style(action, style, option, category)
        result[category] = {"action": action, "style": style, "style_option": option}
    return result


def refresh_defaults(
    engine: Engine,
    *,
    document_id: UUID,
    actor_id: UUID,
    expected_decision_version: int,
    now: datetime,
):
    with Session(engine) as session, session.begin():
        document = owned_document(session, document_id, actor_id, now, lock=True)
        if document.decision_version != expected_decision_version:
            raise VersionConflict(_version(document))
        preset = session.get(Preset, document.preset_id) if document.preset_id else None
        if preset is None or preset.workspace_id != document.workspace_id:
            raise ReviewValidationError(
                "preset_unavailable", "This review has no available preset to refresh."
            )
        document.category_defaults = copy.deepcopy(validate_defaults(preset.category_defaults))
        document.preset_version = preset.version
        _touch_review(document, now)
        clear_document(session, document.id)
        record_event(
            session,
            workspace_id=document.workspace_id,
            actor_id=actor_id,
            document_id=document.id,
            event_code="preset_defaults_applied",
            now=now,
        )
        session.flush()
        return _snapshot(session, _version(document), actor_id, now)
