"""One canonical per-request plan; encrypted seed/offset decrypted at most once."""

from collections import defaultdict
from datetime import UTC

from sqlalchemy.orm import Session

from app.db.crypto import KeyRing
from app.db.models import Document
from app.transformations.engine import ReplacementPlan
from app.transformations.secrets import load_secret
from app.transformations.styles import (
    MASK_CATEGORIES,
    STAND_IN_CATEGORIES,
    StandInGroup,
    StyleUnavailable,
    format_phone,
    generalize_date,
    partial_mask,
    shift_date,
    stand_ins,
    validate_style,
)


def build_plan(
    session: Session,
    document: Document,
    source: str,
    findings,
    keys: KeyRing,
    *,
    logical_values=None,
    collision_source=None,
) -> ReplacementPlan:
    values = logical_values or {
        item.id: source[item.span.start : item.span.end] for item in findings
    }
    needs_secret = any(item.style in {"stand_in", "date_shift"} for item in findings)
    secret = load_secret(session, document.id, keys) if needs_secret else None
    candidates = {}
    if any(item.style == "stand_in" for item in findings):
        grouped = defaultdict(list)
        for item in findings:
            if item.group_id is not None and item.category.value in STAND_IN_CATEGORIES:
                grouped[item.group_id].append(item)
        groups = [
            StandInGroup(
                group_id,
                rows[0].category.value,
                rows[0].label,
                tuple(values[row.id] for row in rows),
            )
            for group_id, rows in grouped.items()
        ]
        candidates = stand_ins(
            secret.seed,
            groups,
            collision_source if collision_source is not None else source,
            document.phone_region,
        )
    replacements, fictional, fallback = {}, [], []
    for item in findings:
        if item.action is None or item.style == "token":
            continue
        value = values[item.id]
        validate_style(
            item.action,
            item.style,
            item.style_option,
            item.category.value,
            value=value,
            date_format=item.date_format,
            region=document.phone_region,
            offset=secret.offset if secret else None,
            created=document.created_at.astimezone(UTC).date(),
        )
        if item.style == "partial_mask":
            replacement = partial_mask(value, item.style_option)
        elif item.style == "stand_in":
            replacement = candidates.get(item.group_id)
            if replacement is None:
                replacement = item.label
                fallback.append(item.id)
            else:
                if item.category.value == "phone":
                    replacement = format_phone(replacement, value)
                fictional.append(item.id)
        elif item.style == "date_shift":
            replacement = shift_date(value, item.date_format, secret.offset)
        else:
            replacement = generalize_date(
                value,
                item.date_format,
                item.style_option,
                document.created_at.astimezone(UTC).date(),
            )
        replacements[item.id] = replacement
    return ReplacementPlan(replacements, tuple(fictional), tuple(fallback))


def style_capabilities(document: Document, source: str, findings, *, logical_values=None):
    """Only content-free codes; actual decisions are validated again under lock."""
    result = {}
    for item in findings:
        value = (
            logical_values[item.id]
            if logical_values is not None
            else source[item.span.start : item.span.end]
        )
        choices = {
            "label": [{"style": "token", "style_option": None}],
            "redact": [{"style": "token", "style_option": None}],
            "keep": [{"style": "token", "style_option": None}],
        }
        offered = [("label", "stand_in", None), ("label", "date_shift", None)]
        offered.extend(("redact", "partial_mask", option) for option in MASK_CATEGORIES)
        offered.extend(
            ("redact", "generalize", option) for option in ("month_year", "year", "age_band")
        )
        for action, style, option in offered:
            try:
                validate_style(
                    action,
                    style,
                    option,
                    item.category.value,
                    value=value,
                    date_format=item.date_format,
                    region=document.phone_region,
                    created=document.created_at.astimezone(UTC).date(),
                )
            except StyleUnavailable:
                continue
            choices[action].append({"style": style, "style_option": option})
        result[item.id] = choices
    return result
