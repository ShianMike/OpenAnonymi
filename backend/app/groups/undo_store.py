"""Bounded per-edit diffs recorded atomically with their review mutation."""

import json
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.contracts import VersionRef
from app.db.durable import ReviewUndoEntry
from app.db.models import Decision, Finding

MAX_PAYLOAD_BYTES = 512 * 1024
MAX_ENTRIES = 20
TTL = timedelta(hours=1)
FINDING_FIELDS = (
    "start_offset",
    "end_offset",
    "category",
    "origin",
    "group_id",
    "scan_run_id",
    "rule_id",
    "rule_version",
    "reason",
    "date_format",
)
UUID_FIELDS = ("group_id", "scan_run_id")


class UndoUnavailable(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__("No current review edit is available to undo.")


def capture(session: Session, rows: list[Finding], *, created: tuple[UUID, ...] = ()) -> dict:
    ids = [row.id for row in rows]
    decisions = (
        {
            row.finding_id: row
            for row in session.scalars(select(Decision).where(Decision.finding_id.in_(ids))).all()
        }
        if ids
        else {}
    )
    findings = {}
    before_decisions = {}
    for row in rows:
        values = {field: getattr(row, field) for field in FINDING_FIELDS}
        for field in UUID_FIELDS:
            values[field] = str(values[field]) if values[field] is not None else None
        findings[str(row.id)] = values
        decision = decisions.get(row.id)
        before_decisions[str(row.id)] = (
            {"action": decision.action, "keep_reason": decision.keep_reason} if decision else None
        )
    return {
        "findings": findings,
        "decisions": before_decisions,
        "created": [str(id_) for id_ in created],
    }


def _entries(session: Session, document_id: UUID, actor_id: UUID, now: datetime):
    return session.scalars(
        select(ReviewUndoEntry)
        .where(
            ReviewUndoEntry.document_id == document_id,
            ReviewUndoEntry.actor_id == actor_id,
            ReviewUndoEntry.created_at > now - TTL,
        )
        .order_by(ReviewUndoEntry.sequence.desc())
    ).all()


def _matches(entry: ReviewUndoEntry, version: VersionRef) -> bool:
    return entry.after_version == version.decision_version and entry.payload.get(
        "version"
    ) == version.model_dump(mode="json")


def available(session: Session, version: VersionRef, actor_id: UUID, now: datetime) -> int:
    entries = _entries(session, version.document_id, actor_id, now)
    return min(len(entries), MAX_ENTRIES) if entries and _matches(entries[0], version) else 0


def clear_document(session: Session, document_id: UUID) -> None:
    session.execute(delete(ReviewUndoEntry).where(ReviewUndoEntry.document_id == document_id))


def _clear_actor(session: Session, document_id: UUID, actor_id: UUID) -> None:
    session.execute(
        delete(ReviewUndoEntry).where(
            ReviewUndoEntry.document_id == document_id, ReviewUndoEntry.actor_id == actor_id
        )
    )


def remember(
    session: Session,
    *,
    actor_id: UUID,
    before: VersionRef,
    after: VersionRef,
    payload: dict,
    now: datetime,
) -> None:
    if before == after:
        return
    entries = _entries(session, after.document_id, actor_id, now)
    if entries and not _matches(entries[0], before):
        _clear_actor(session, after.document_id, actor_id)
    payload = {**payload, "format": 1, "version": after.model_dump(mode="json")}
    size = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if size > MAX_PAYLOAD_BYTES:
        _clear_actor(session, after.document_id, actor_id)
        return
    session.add(
        ReviewUndoEntry(
            id=uuid4(),
            document_id=after.document_id,
            actor_id=actor_id,
            sequence=after.decision_version,
            after_version=after.decision_version,
            payload=payload,
            payload_bytes=size,
            created_at=now,
        )
    )
    session.flush()
    obsolete = (
        select(ReviewUndoEntry.id)
        .where(
            ReviewUndoEntry.document_id == after.document_id, ReviewUndoEntry.actor_id == actor_id
        )
        .order_by(ReviewUndoEntry.sequence.desc())
        .offset(MAX_ENTRIES)
    )
    session.execute(
        delete(ReviewUndoEntry).where(ReviewUndoEntry.id.in_(obsolete)),
        execution_options={"synchronize_session": False},
    )


def replay(session: Session, *, version: VersionRef, actor_id: UUID, now: datetime) -> None:
    # Caller holds the document lock, serializing edits and undo across processes.
    entries = _entries(session, version.document_id, actor_id, now)
    if not entries:
        raise UndoUnavailable("nothing_to_undo")
    entry = entries[0]
    if not _matches(entry, version):
        raise UndoUnavailable("undo_unavailable")
    for id_ in entry.payload["created"]:
        row = session.get(Finding, UUID(id_))
        if row is None or row.document_id != version.document_id:
            raise UndoUnavailable("undo_unavailable")
        session.delete(row)
    for id_, values in entry.payload["findings"].items():
        row = session.get(Finding, UUID(id_))
        if (
            row is None
            or row.document_id != version.document_id
            or row.source_revision_id != version.source_revision_id
        ):
            raise UndoUnavailable("undo_unavailable")
        for field in FINDING_FIELDS:
            value = values.get(field) if field == "date_format" else values[field]
            setattr(
                row, field, UUID(value) if field in UUID_FIELDS and value is not None else value
            )
        row.removed_at = None
        decision = session.get(Decision, row.id)
        prior = entry.payload["decisions"][id_]
        if prior is None:
            if decision is not None:
                session.delete(decision)
        else:
            if decision is None:
                decision = Decision(finding_id=row.id)
                session.add(decision)
            decision.action, decision.keep_reason = prior["action"], prior["keep_reason"]
            decision.decided_by, decision.decided_at = actor_id, now
            decision.decision_version = version.decision_version + 1
    session.delete(entry)
    session.flush()
    if len(entries) > 1:
        previous = entries[1]
        after = version.model_copy(update={"decision_version": version.decision_version + 1})
        previous.after_version = after.decision_version
        previous.payload = {**previous.payload, "version": after.model_dump(mode="json")}
        previous.payload_bytes = len(
            json.dumps(previous.payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
