"""Remove batch ciphertext and metadata only once every child lost its content."""

from sqlalchemy import and_, delete, exists, func, or_, select, text

from app.db.batches import Batch, ScanJob
from app.db.models import Document, Workspace


def removable_batches(now):
    has_content = exists(
        select(Document.id).where(
            Document.batch_id == Batch.id,
            or_(Document.current_revision_id.is_not(None), Document.title_ciphertext.is_not(None)),
        )
    )
    has_documents = exists(select(Document.id).where(Document.batch_id == Batch.id))
    retention_days = func.least(
        Workspace.content_retention_days,
        func.coalesce(
            Batch.settings["retention_days"].as_integer(), Workspace.content_retention_days
        ),
    )
    old_empty = exists(
        select(Workspace.id).where(
            Workspace.id == Batch.workspace_id,
            Batch.created_at <= now - retention_days * text("INTERVAL '1 day'"),
        )
    )
    return and_(~has_content, or_(Batch.deleted_at.is_not(None), has_documents, old_empty))


def purge_empty_batches(session, now, batch_size):
    rows = session.scalars(
        select(Batch)
        .where(removable_batches(now))
        .order_by(Batch.created_at, Batch.id)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    ).all()
    count = 0
    for batch in rows:
        # A batch upload/delete holds this same lock. Lock child rows in order and
        # skip a busy child so document/batch cleanup cannot form a lock cycle.
        ids = list(session.scalars(select(Document.id).where(Document.batch_id == batch.id)))
        documents = session.scalars(
            select(Document)
            .where(Document.batch_id == batch.id)
            .order_by(Document.id)
            .with_for_update(skip_locked=True)
        ).all()
        if len(ids) != len(documents) or any(
            doc.current_revision_id is not None or doc.title_ciphertext is not None
            for doc in documents
        ):
            continue
        session.execute(delete(ScanJob).where(ScanJob.batch_id == batch.id))
        for document in documents:
            document.batch_id = None
            document.batch_position = None
        session.flush()
        session.delete(batch)
        count += 1
    session.flush()
    return count
