from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.accounts.access import DocumentNotFound, owned_document, review_document
from app.contracts import DocumentStatus, VersionRef
from app.db.crypto import KeyRing
from app.db.models import Document, Membership, User, Workspace
from app.db.repository import VersionConflict, _version
from app.db.team_review import ReviewApproval, ReviewHandoff
from app.reviews.service import CompletionRejected, current_completion
from app.transformations.service import build_current_preview
from app.workspace.activity import record_event


class TeammateView(BaseModel):
    user_id: UUID
    email: str


class HandoffView(BaseModel):
    version: VersionRef
    is_owner: bool
    reviewer_id: UUID | None
    reviewer_email: str | None
    reviewer_active: bool
    require_approval: bool
    approved_at: datetime | None
    generation: int
    approval_policy: Literal["owner_choice", "always"]


class HandoffPolicyRejected(ValueError):
    pass


def approval_policy(session: Session, document: Document) -> str:
    # A scalar query reads the current policy even when the ORM workspace is cached.
    value = session.scalar(
        select(Workspace.approval_policy).where(Workspace.id == document.workspace_id)
    )
    if value is None:
        raise DocumentNotFound("Workspace not found.")
    return value


def active_reviewer(session: Session, document: Document, handoff: ReviewHandoff) -> bool:
    if not handoff.reviewer_id or handoff.reviewer_id == document.owner_id:
        return False
    member = session.get(Membership, (document.workspace_id, handoff.reviewer_id))
    user = session.get(User, handoff.reviewer_id)
    return bool(member and member.revoked_at is None and user and user.disabled_at is None)


def _approval(session: Session, document: Document, handoff: ReviewHandoff):
    if not active_reviewer(session, document, handoff):
        return None
    version = _version(document)
    return session.scalar(
        select(ReviewApproval).where(
            ReviewApproval.document_id == document.id,
            ReviewApproval.generation == handoff.generation,
            ReviewApproval.approved_by == handoff.reviewer_id,
            ReviewApproval.source_revision_id == version.source_revision_id,
            ReviewApproval.decision_version == version.decision_version,
            ReviewApproval.settings_version == version.settings_version,
        )
    )


def require_second_approval(session: Session, document: Document):
    handoff = session.get(ReviewHandoff, document.id)
    policy = approval_policy(session, document)
    if policy == "always" and (handoff is None or _approval(session, document, handoff) is None):
        raise CompletionRejected(
            "approval_required_by_policy",
            "Your workspace requires a reviewer to approve this version before export. Assign a reviewer.",
        )
    if handoff and handoff.require_approval and _approval(session, document, handoff) is None:
        raise CompletionRejected(
            "second_approval_required",
            "The assigned reviewer must approve this exact version before export.",
        )


def _view(session: Session, document: Document, actor_id: UUID):
    handoff = session.get(ReviewHandoff, document.id)
    approval = _approval(session, document, handoff) if handoff else None
    user = session.get(User, handoff.reviewer_id) if handoff and handoff.reviewer_id else None
    policy = approval_policy(session, document)
    return HandoffView(
        version=_version(document),
        is_owner=document.owner_id == actor_id,
        reviewer_id=handoff.reviewer_id if handoff else None,
        reviewer_email=user.email if user else None,
        reviewer_active=active_reviewer(session, document, handoff) if handoff else False,
        require_approval=policy == "always" or bool(handoff and handoff.require_approval),
        approved_at=approval.approved_at if approval else None,
        generation=handoff.generation if handoff else 0,
        approval_policy=policy,
    )


def load_handoff(engine: Engine, *, document_id: UUID, actor_id: UUID, now: datetime):
    with Session(engine) as session, session.begin():
        document = review_document(session, document_id, actor_id, now, lock=True)
        return _view(session, document, actor_id)


def list_teammates(engine: Engine, *, document_id: UUID, actor_id: UUID, now: datetime):
    with Session(engine) as session:
        document = owned_document(session, document_id, actor_id, now)
        rows = session.execute(
            select(User.id, User.email)
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.workspace_id == document.workspace_id,
                Membership.revoked_at.is_(None),
                User.disabled_at.is_(None),
                User.id != actor_id,
            )
            .order_by(User.email)
            .limit(200)
        ).all()
        return [TeammateView(user_id=user, email=email) for user, email in rows]


def change_handoff(
    engine: Engine,
    *,
    document_id: UUID,
    actor_id: UUID,
    expected: VersionRef,
    reviewer_id: UUID | None,
    require_approval: bool,
    now: datetime,
):
    with Session(engine) as session, session.begin():
        document = owned_document(session, document_id, actor_id, now, lock=True)
        current = _version(document)
        if current != expected:
            raise VersionConflict(current)
        if approval_policy(session, document) == "always" and not require_approval:
            raise HandoffPolicyRejected("Workspace policy requires reviewer approval.")
        if document.status == DocumentStatus.SCANNING:
            raise CompletionRejected(
                "scan_in_progress", "Finish the current scan before changing review access."
            )
        if reviewer_id:
            member = session.get(Membership, (document.workspace_id, reviewer_id))
            user = session.get(User, reviewer_id)
            if (
                reviewer_id == actor_id
                or not member
                or member.revoked_at
                or not user
                or user.disabled_at
            ):
                raise DocumentNotFound("Active reviewer not found.")
        handoff = session.get(ReviewHandoff, document_id)
        if (
            handoff
            and handoff.reviewer_id == reviewer_id
            and handoff.require_approval == require_approval
        ):
            return _view(session, document, actor_id)
        from app.notifications.events import invalidate_approval
        from app.notifications.service import notify

        previous_reviewer = handoff.reviewer_id if handoff else None
        invalidate_approval(session, document, actor_id, now)
        if previous_reviewer != reviewer_id:
            notify(
                session,
                document,
                previous_reviewer,
                actor_id,
                "review_unassigned",
                now,
                require_active=False,
            )
            notify(session, document, reviewer_id, actor_id, "review_assigned", now)
        if not handoff:
            handoff = ReviewHandoff(
                document_id=document_id,
                generation=1,
                reviewer_id=reviewer_id,
                require_approval=require_approval,
                updated_at=now,
            )
            session.add(handoff)
        else:
            handoff.generation += 1
            handoff.reviewer_id, handoff.require_approval, handoff.updated_at = (
                reviewer_id,
                require_approval,
                now,
            )
        document.decision_version += 1
        if document.status in (DocumentStatus.READY, DocumentStatus.EXPORTED):
            document.status = DocumentStatus.NEEDS_REVIEW
        document.updated_at = now
        record_event(
            session,
            workspace_id=document.workspace_id,
            actor_id=actor_id,
            document_id=document_id,
            event_code="review_handoff_changed",
            now=now,
        )
        session.flush()
        return _view(session, document, actor_id)


def approve_review(
    engine: Engine,
    *,
    document_id: UUID,
    actor_id: UUID,
    expected: VersionRef,
    confirmed_preview: bool,
    keys: KeyRing,
    now: datetime,
):
    with Session(engine) as session, session.begin():
        document = review_document(session, document_id, actor_id, now, lock=True)
        handoff = session.get(ReviewHandoff, document_id)
        if document.owner_id == actor_id or not handoff or handoff.reviewer_id != actor_id:
            raise DocumentNotFound("Assigned reviewer not found.")
        if _version(document) != expected:
            raise VersionConflict(_version(document))
        if not confirmed_preview:
            raise CompletionRejected(
                "confirmation_required",
                "Read the full reviewed output and explicitly approve this version.",
            )
        current_completion(session, document)
        if build_current_preview(session, document=document, keys=keys).status != "complete":
            raise CompletionRejected(
                "review_not_completed",
                "The owner must confirm the current review before second approval.",
            )
        if _approval(session, document, handoff) is None:
            session.add(
                ReviewApproval(
                    id=uuid4(),
                    document_id=document_id,
                    generation=handoff.generation,
                    source_revision_id=expected.source_revision_id,
                    decision_version=expected.decision_version,
                    settings_version=expected.settings_version,
                    approved_by=actor_id,
                    approved_at=now,
                )
            )
            record_event(
                session,
                workspace_id=document.workspace_id,
                actor_id=actor_id,
                document_id=document_id,
                event_code="review_second_approved",
                now=now,
            )
            from app.notifications.service import notify

            notify(session, document, document.owner_id, actor_id, "review_approved", now)
            session.flush()
        return _view(session, document, actor_id)
