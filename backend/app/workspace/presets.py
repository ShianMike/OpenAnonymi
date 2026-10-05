"""Versioned workspace presets; reviews keep their own intake snapshot."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from phonenumbers import SUPPORTED_REGIONS
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.accounts.access import active_workspace, refresh_workspace_access, require_administrator
from app.contracts import AUTOMATIC_CATEGORIES, FindingCategory
from app.db.column_rules import load_preset_rules
from app.db.crypto import KeyRing, ProtectedContentError
from app.db.models import Preset
from app.errors import ApiError
from app.workspace.activity import record_event


class PresetNotFound(LookupError):
    pass


class PresetExists(ValueError):
    pass


class PresetVersionConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class PresetRecord:
    id: UUID
    name: str
    categories: list[FindingCategory]
    phone_region: str
    preferred_action: str
    version: int
    is_default: bool
    category_defaults: dict
    column_rules: list[dict] = field(default_factory=list)


def _record(preset: Preset, keys: KeyRing | None = None) -> PresetRecord:
    return PresetRecord(
        id=preset.id,
        name=preset.name,
        categories=[FindingCategory(value) for value in preset.categories.split(",") if value],
        phone_region=preset.phone_region,
        preferred_action=preset.preferred_action,
        version=preset.version,
        is_default=preset.is_default,
        category_defaults=preset.category_defaults,
        column_rules=load_preset_rules(preset, keys),
    )


def list_presets(
    session: Session, *, workspace_id: UUID, actor_id: UUID, keys: KeyRing | None = None
) -> list[PresetRecord]:
    active_workspace(session, workspace_id, actor_id)
    rows = session.scalars(
        select(Preset)
        .where(Preset.workspace_id == workspace_id)
        .order_by(Preset.is_default.desc(), Preset.name, Preset.id)
    ).all()
    return [_record(row, keys) for row in rows]


def save_preset(
    session: Session,
    *,
    workspace_id: UUID,
    actor_id: UUID,
    preset_id: UUID | None,
    expected_version: int | None,
    name: str,
    categories: set[FindingCategory],
    phone_region: str,
    preferred_action: str,
    is_default: bool,
    now: datetime,
    category_defaults: dict | None = None,
    column_rules: list[dict] | None = None,
    keys: KeyRing | None = None,
    reauthorize: Callable[[], object] | None = None,
) -> PresetRecord:
    from app.transformations.defaults import validate_defaults

    validated_defaults = (
        validate_defaults(category_defaults) if category_defaults is not None else None
    )
    from app.intake.column_rules import validate_rules

    validated_columns = validate_rules(column_rules) if column_rules is not None else None
    name = name.strip()
    phone_region = phone_region.upper()
    if not name or len(name) > 100:
        raise ValueError("Choose a name of 1 to 100 characters.")
    if not categories.issubset(AUTOMATIC_CATEGORIES):
        raise ValueError("Choose supported automatic suggestion categories.")
    if phone_region not in SUPPORTED_REGIONS:
        raise ValueError("Choose a supported phone region.")
    if preferred_action not in ("label", "redact"):
        raise ValueError("Choose Label or Redact as the preferred action.")
    with session.begin():
        require_administrator(session, workspace_id=workspace_id, actor_id=actor_id, lock=True)
        refresh_workspace_access(session, workspace_id, actor_id, reauthorize, administrator=True)
        existing_name = session.scalar(
            select(Preset).where(
                Preset.workspace_id == workspace_id,
                Preset.name == name,
                Preset.id != preset_id,
            )
        )
        if existing_name is not None:
            raise PresetExists("A preset with this name already exists.")
        if preset_id is None:
            preset = Preset(id=uuid4(), workspace_id=workspace_id, created_at=now)
            session.add(preset)
            event_code = "preset_created"
        else:
            preset = session.scalar(
                select(Preset).where(Preset.workspace_id == workspace_id, Preset.id == preset_id)
            )
            if preset is None:
                raise PresetNotFound("Preset not found.")
            if preset.version != expected_version:
                raise PresetVersionConflict("This preset changed. Reload before saving.")
            preset.version += 1
            event_code = "preset_updated"
        preset.name = name
        preset.categories = ",".join(sorted(value.value for value in categories))
        preset.phone_region = phone_region
        preset.preferred_action = preferred_action
        if validated_defaults is not None or preset_id is None:
            preset.category_defaults = validated_defaults or {}
        if validated_columns is not None:
            if validated_columns:
                if keys is None:
                    raise ProtectedContentError("Protected preset settings are unavailable.")
                protected = keys.encrypt_text(json.dumps(validated_columns, separators=(",", ":")))
                preset.column_rules_ciphertext, preset.column_rules_key_id = (
                    protected.ciphertext,
                    protected.key_id,
                )
            else:
                preset.column_rules_ciphertext, preset.column_rules_key_id = None, None
        preset.is_default = False
        session.flush()
        if is_default:
            session.execute(
                update(Preset)
                .where(Preset.workspace_id == workspace_id, Preset.is_default.is_(True))
                .values(is_default=False)
            )
            session.flush()
            preset.is_default = True
        session.flush()
        record_event(
            session,
            workspace_id=workspace_id,
            actor_id=actor_id,
            document_id=None,
            event_code=event_code,
            now=now,
        )
        result = _record(preset, keys)
        session.flush()
        refresh_workspace_access(session, workspace_id, actor_id, reauthorize, administrator=True)
    return result


def validate_preset_view(session, workspace_id, actor_id, view):
    """Default switches also change other presets without increasing their version."""
    active_workspace(session, workspace_id, actor_id)
    statement = select(Preset.id, Preset.version, Preset.is_default).where(
        Preset.workspace_id == workspace_id
    )
    items = view if isinstance(view, list) else [view]
    if not isinstance(view, list):
        statement = statement.where(Preset.id == view.id)
    if set(session.execute(statement).all()) != {
        (item.id, item.version, item.is_default) for item in items
    }:
        raise ApiError(409, "presets_changed", "Presets changed. Reload before continuing.")
    active_workspace(session, workspace_id, actor_id)
