"""Exact source text in bounded line-aligned blocks; no stored plaintext diffs."""

from datetime import datetime
from difflib import SequenceMatcher
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import DocumentNotFound, review_document
from app.db.crypto import KeyRing, ProtectedValue
from app.db.models import SourceRevision


class RevisionSide(BaseModel):
    id: UUID
    number: int
    created_at: datetime


class DiffBlock(BaseModel):
    kind: str
    left_text: str
    right_text: str
    left_start: int
    right_start: int
    left_lines: int
    right_lines: int
    change: int | None


class ComparisonView(BaseModel):
    document_id: UUID
    before: RevisionSide
    after: RevisionSide
    blocks: list[DiffBlock]
    changes: int
    added_lines: int
    removed_lines: int
    coarse: bool


def _coarse_opcodes(left: list[str], right: list[str]):
    """Retain shared edges and show the exact changed middle as one larger block."""
    prefix = 0
    while prefix < min(len(left), len(right)) and left[prefix] == right[prefix]:
        prefix += 1
    suffix = 0
    while (
        suffix < min(len(left), len(right)) - prefix
        and left[len(left) - suffix - 1] == right[len(right) - suffix - 1]
    ):
        suffix += 1
    codes = []
    if prefix:
        codes.append(("equal", 0, prefix, 0, prefix))
    lend, rend = len(left) - suffix, len(right) - suffix
    if lend > prefix or rend > prefix:
        kind = (
            "replace"
            if lend > prefix and rend > prefix
            else "delete"
            if lend > prefix
            else "insert"
        )
        codes.append((kind, prefix, lend, prefix, rend))
    if suffix:
        codes.append(("equal", lend, len(left), rend, len(right)))
    return codes


def align_sources(before: str, after: str) -> tuple[list[DiffBlock], bool]:
    left, right = before.splitlines(keepends=True), after.splitlines(keepends=True)
    coarse = max(len(left), len(right)) > 5000 or len(left) * len(right) > 2_000_000
    codes = (
        _coarse_opcodes(left, right)
        if coarse
        else SequenceMatcher(None, left, right, autojunk=True).get_opcodes()
    )
    if len(codes) > 400:
        coarse, codes = True, _coarse_opcodes(left, right)
    change = 0
    blocks = []
    for kind, lstart, lend, rstart, rend in codes:
        if kind != "equal":
            change += 1
        blocks.append(
            DiffBlock(
                kind=kind,
                left_text="".join(left[lstart:lend]),
                right_text="".join(right[rstart:rend]),
                left_start=lstart + 1,
                right_start=rstart + 1,
                left_lines=lend - lstart,
                right_lines=rend - rstart,
                change=change if kind != "equal" else None,
            )
        )
    return blocks, coarse


def compare_revisions(
    engine: Engine,
    *,
    document_id: UUID,
    actor_id: UUID,
    before_id: UUID,
    after_id: UUID,
    keys: KeyRing,
    now: datetime,
) -> ComparisonView:
    with Session(engine) as session, session.begin():
        review_document(session, document_id, actor_id, now, lock=True)
        rows = session.scalars(
            select(SourceRevision).where(
                SourceRevision.document_id == document_id,
                SourceRevision.id.in_([before_id, after_id]),
            )
        ).all()
        by_id = {row.id: row for row in rows}
        if before_id not in by_id or after_id not in by_id:
            raise DocumentNotFound("Revision not found.")
        before, after = by_id[before_id], by_id[after_id]
        left = keys.decrypt_text(ProtectedValue(before.source_ciphertext, before.source_key_id))
        right = keys.decrypt_text(ProtectedValue(after.source_ciphertext, after.source_key_id))
        blocks, coarse = align_sources(left, right)
        return ComparisonView(
            document_id=document_id,
            before=RevisionSide(
                id=before.id, number=before.revision_number, created_at=before.created_at
            ),
            after=RevisionSide(
                id=after.id, number=after.revision_number, created_at=after.created_at
            ),
            blocks=blocks,
            changes=sum(block.change is not None for block in blocks),
            added_lines=sum(block.right_lines for block in blocks if block.kind != "equal"),
            removed_lines=sum(block.left_lines for block in blocks if block.kind != "equal"),
            coarse=coarse,
        )
