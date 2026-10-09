"""Allowlisted decision diffs; never retain source, offsets, labels or reasons."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts import DecisionAction, FindingCategory
from app.db.models import Decision, Finding

Style = Literal["token", "partial_mask", "stand_in", "date_shift", "generalize"]
Option = Literal[
    "full",
    "last4",
    "first_letters",
    "email_domain",
    "email_first",
    "url_host",
    "secret_prefix",
    "month_year",
    "year",
    "age_band",
]
MAX_CHANGES = 256


class DecisionChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    finding_id: UUID
    category: FindingCategory
    before_action: DecisionAction | None
    before_style: Style | None
    before_option: Option | None
    after_action: DecisionAction | None
    after_style: Style | None
    after_option: Option | None


def decision_diff(session: Session, before: dict) -> tuple[list[dict], int]:
    ids = {UUID(item) for item in before["findings"]} | {UUID(item) for item in before["created"]}
    after = (
        {
            row.id: row
            for row in session.execute(
                select(
                    Finding.id,
                    Finding.category,
                    Finding.removed_at,
                    Decision.action,
                    Decision.style,
                    Decision.style_option,
                )
                .outerjoin(Decision, Decision.finding_id == Finding.id)
                .where(Finding.id.in_(ids))
            ).all()
        }
        if ids
        else {}
    )
    changes = []
    count = 0
    for id_ in sorted(ids):
        prior = before["decisions"].get(str(id_))
        latest = after.get(id_)
        previous = (
            (prior["action"], prior.get("style", "token"), prior.get("style_option"))
            if prior
            else (None, None, None)
        )
        current = (
            (latest.action, latest.style, latest.style_option)
            if latest and latest.removed_at is None and latest.action
            else (None, None, None)
        )
        if previous == current:
            continue
        count += 1
        if len(changes) < MAX_CHANGES:
            category = latest.category if latest else before["findings"][str(id_)]["category"]
            changes.append(
                DecisionChange(
                    finding_id=id_,
                    category=category,
                    before_action=previous[0],
                    before_style=previous[1],
                    before_option=previous[2],
                    after_action=current[0],
                    after_style=current[1],
                    after_option=current[2],
                ).model_dump(mode="json")
            )
    return changes, count
