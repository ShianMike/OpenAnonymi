"""Document-scoped label allocation under the document's transaction lock."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts import DocumentStatus, FindingCategory, VersionRef
from app.db.models import EntityGroup, LabelCounter
from app.db.repository import VersionConflict, _owned_document, _version
from app.lifecycle import require_transition


def create_labeled_group(
    session: Session,
    *,
    document_id: UUID,
    actor_id: UUID,
    expected: VersionRef,
    category: FindingCategory,
    now: datetime,
) -> EntityGroup:
    """Lock one document before reading/incrementing its category counter.

    All group creation must use this path. The database also enforces unique
    (document_id, label), so a stray writer cannot assign one label twice.
    """
    with session.begin():
        document = _owned_document(session, document_id, actor_id, now, lock=True)
        current = _version(document)
        if current != expected:
            raise VersionConflict(current)
        counter = session.scalar(
            select(LabelCounter)
            .where(
                LabelCounter.document_id == document_id,
                LabelCounter.category == category.value,
            )
            .with_for_update()
        )
        if counter is None:
            counter = LabelCounter(document_id=document_id, category=category.value, next_number=1)
            session.add(counter)
            session.flush()
        number = counter.next_number
        counter.next_number += 1
        group = EntityGroup(
            id=uuid4(),
            document_id=document_id,
            source_revision_id=current.source_revision_id,
            category=category.value,
            label=f"{category.value.upper()}_{number:03d}",
            created_at=now,
        )
        session.add(group)
        document.decision_version += 1
        if document.status != DocumentStatus.NEEDS_REVIEW:
            require_transition(DocumentStatus(document.status), DocumentStatus.NEEDS_REVIEW)
        document.status = DocumentStatus.NEEDS_REVIEW
        document.updated_at = now
        session.flush()
        session.expunge(group)
    return group
