from datetime import datetime
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import DocumentNotFound, review_document
from app.contracts import VersionRef
from app.db.crypto import KeyRing, ProtectedValue
from app.db.models import Finding, User
from app.db.repository import VersionConflict, _version
from app.db.team_review import FindingComment
from app.reviews.service import CompletionRejected
from app.workspace.activity import record_event


class CommentView(BaseModel):
    id: UUID
    finding_id: UUID
    author_email: str
    is_mine: bool
    text: str
    created_at: datetime


def _finding(session, document, finding_id):
    row = session.get(Finding, finding_id)
    if (
        not row
        or row.document_id != document.id
        or row.source_revision_id != document.current_revision_id
        or row.removed_at
    ):
        raise DocumentNotFound("Current finding not found.")


def _view(session, row, actor, keys):
    return CommentView(
        id=row.id,
        finding_id=row.finding_id,
        author_email=session.get(User, row.author_id).email,
        is_mine=row.author_id == actor,
        text=keys.decrypt_text(ProtectedValue(row.text_ciphertext, row.text_key_id)),
        created_at=row.created_at,
    )


def load_comments(
    engine: Engine,
    *,
    document_id: UUID,
    finding_id: UUID,
    actor_id: UUID,
    keys: KeyRing,
    now: datetime,
):
    with Session(engine) as session, session.begin():
        document = review_document(session, document_id, actor_id, now, lock=True)
        _finding(session, document, finding_id)
        rows = session.scalars(
            select(FindingComment)
            .where(
                FindingComment.document_id == document_id, FindingComment.finding_id == finding_id
            )
            .order_by(FindingComment.created_at, FindingComment.id)
            .limit(100)
        ).all()
        return [_view(session, row, actor_id, keys) for row in rows]


def add_comment(
    engine: Engine,
    *,
    document_id: UUID,
    finding_id: UUID,
    actor_id: UUID,
    comment_id: UUID,
    expected: VersionRef,
    text: str,
    keys: KeyRing,
    now: datetime,
):
    with Session(engine) as session, session.begin():
        document = review_document(session, document_id, actor_id, now, lock=True)
        if _version(document) != expected:
            raise VersionConflict(_version(document))
        _finding(session, document, finding_id)
        existing = session.get(FindingComment, comment_id)
        if existing:
            if (
                existing.document_id != document_id
                or existing.finding_id != finding_id
                or existing.author_id != actor_id
                or _view(session, existing, actor_id, keys).text != text
            ):
                raise CompletionRejected(
                    "comment_conflict", "This comment attempt belongs to another operation."
                )
            return _view(session, existing, actor_id, keys)
        counts = session.execute(
            select(
                func.count(), func.count().filter(FindingComment.finding_id == finding_id)
            ).where(FindingComment.document_id == document_id)
        ).one()
        if counts[0] >= 200 or counts[1] >= 100:
            raise CompletionRejected("comment_limit", "This review has reached its comment limit.")
        if not text.strip() or len(text) > 2000:
            raise CompletionRejected(
                "invalid_comment", "Write a comment with 1 to 2,000 characters."
            )
        protected = keys.encrypt_text(text)
        row = FindingComment(
            id=comment_id,
            document_id=document_id,
            finding_id=finding_id,
            author_id=actor_id,
            text_ciphertext=protected.ciphertext,
            text_key_id=protected.key_id,
            created_at=now,
        )
        session.add(row)
        record_event(
            session,
            workspace_id=document.workspace_id,
            actor_id=actor_id,
            document_id=document_id,
            event_code="finding_comment_added",
            now=now,
        )
        from app.db.team_review import ReviewHandoff
        from app.notifications.service import notify

        handoff = session.get(ReviewHandoff, document.id)
        recipients = {document.owner_id, handoff.reviewer_id if handoff else None} - {
            actor_id,
            None,
        }
        for recipient in recipients:
            notify(session, document, recipient, actor_id, "comment_added", now)
        session.flush()
        return _view(session, row, actor_id, keys)


def delete_comment(
    engine: Engine, *, document_id: UUID, comment_id: UUID, actor_id: UUID, now: datetime
):
    with Session(engine) as session, session.begin():
        document = review_document(session, document_id, actor_id, now, lock=True)
        row = session.get(FindingComment, comment_id)
        if (
            not row
            or row.document_id != document_id
            or (row.author_id != actor_id and document.owner_id != actor_id)
        ):
            raise DocumentNotFound("Comment not found.")
        session.delete(row)


def revoke_member_handoffs(
    session: Session, workspace_id: UUID, user_id: UUID, now: datetime, *, actor_id=None
):
    """Restoring a membership must never restore a prior document grant/approval."""
    from app.db.models import Document
    from app.db.team_review import ReviewHandoff

    rows = session.scalars(
        select(Document)
        .join(ReviewHandoff, ReviewHandoff.document_id == Document.id)
        .where(
            Document.workspace_id == workspace_id,
            (ReviewHandoff.reviewer_id == user_id) | (Document.owner_id == user_id),
        )
        .order_by(Document.id)
        .with_for_update(of=Document)
    ).all()
    for document in rows:
        handoff = session.get(ReviewHandoff, document.id)
        from app.notifications.service import notify

        notify(
            session,
            document,
            handoff.reviewer_id,
            actor_id,
            "review_unassigned",
            now,
            require_active=False,
        )
        handoff.reviewer_id = None
        handoff.generation += 1
        handoff.updated_at = now
