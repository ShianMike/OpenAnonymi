"""Content-free aggregates over the actor's active, recently created reviews."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.contracts import DocumentStatus, FindingCategory
from app.db.models import Document, ExportEvent, Finding, ReviewCompletion


@dataclass(frozen=True)
class CategoryCount:
    category: FindingCategory
    count: int


@dataclass(frozen=True)
class OverviewAnalytics:
    since: datetime
    cohort_documents: int
    confirmed_documents: int
    exported_documents: int
    average_time_to_confirm_seconds: float | None
    export_rate: float | None
    findings_total: int
    categories: list[CategoryCount]


def load_analytics(
    session: Session, *, workspace_id: UUID, actor_id: UUID, now: datetime
) -> OverviewAnalytics:
    since = now - timedelta(days=30)
    cohort = (
        select(Document.id, Document.current_revision_id, Document.created_at)
        .where(
            Document.workspace_id == workspace_id,
            Document.owner_id == actor_id,
            Document.deleted_at.is_(None),
            Document.status.not_in((DocumentStatus.DELETED, DocumentStatus.EXPIRED)),
            Document.expires_at > now,
            Document.created_at >= since,
            Document.created_at <= now,
        )
        .cte("overview_cohort")
    )
    first_confirmation = (
        select(
            ReviewCompletion.document_id,
            func.min(ReviewCompletion.confirmed_at).label("first_at"),
        )
        .join(cohort, cohort.c.id == ReviewCompletion.document_id)
        .where(
            ReviewCompletion.confirmed_at >= cohort.c.created_at,
            ReviewCompletion.confirmed_at <= now,
        )
        .group_by(ReviewCompletion.document_id)
        .subquery()
    )
    exported = (
        select(ExportEvent.id)
        .where(
            ExportEvent.document_id == cohort.c.id,
            # Copy is a reviewed output. A source-free report is not one.
            ExportEvent.format.in_(("copy", "txt", "docx", "csv", "pdf")),
            ExportEvent.occurred_at >= cohort.c.created_at,
            ExportEvent.occurred_at <= now,
        )
        .exists()
    )
    total, confirmed, exported_count, average = session.execute(
        select(
            func.count(cohort.c.id),
            func.count(first_confirmation.c.first_at),
            func.coalesce(func.sum(case((exported, 1), else_=0)), 0),
            func.avg(func.extract("epoch", first_confirmation.c.first_at - cohort.c.created_at)),
        )
        .select_from(cohort)
        .outerjoin(first_confirmation, first_confirmation.c.document_id == cohort.c.id)
    ).one()
    categories = [
        CategoryCount(FindingCategory(category), count)
        for category, count in session.execute(
            select(Finding.category, func.count(Finding.id).label("count"))
            .join(cohort, cohort.c.id == Finding.document_id)
            .where(
                Finding.source_revision_id == cohort.c.current_revision_id,
                Finding.removed_at.is_(None),
            )
            .group_by(Finding.category)
            .order_by(func.count(Finding.id).desc(), Finding.category)
        ).all()
    ]
    return OverviewAnalytics(
        since=since,
        cohort_documents=total,
        confirmed_documents=confirmed,
        exported_documents=exported_count,
        average_time_to_confirm_seconds=float(average) if average is not None else None,
        export_rate=exported_count / total if total else None,
        findings_total=sum(item.count for item in categories),
        categories=categories,
    )
