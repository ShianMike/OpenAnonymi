"""An allowlisted redaction report with no document text or free-form fields."""

import json
from collections import Counter
from datetime import datetime

from app.contracts import VersionRef
from app.groups.service import FindingsSnapshot
from app.transformations.service import PreviewSnapshot


def build_report(
    version: VersionRef,
    confirmed_at: datetime,
    findings: FindingsSnapshot,
    preview: PreviewSnapshot,
) -> dict:
    mappings = {item.finding_id: item for item in preview.mappings}
    return {
        "schema_version": 1,
        "review_version": version.model_dump(mode="json"),
        "confirmed_at": confirmed_at.isoformat(),
        "finding_count": len(findings.findings),
        "counts_by_category": dict(Counter(item.category.value for item in findings.findings)),
        "counts_by_action": dict(Counter(item.action for item in findings.findings)),
        "counts_by_style": dict(Counter(item.style for item in findings.findings)),
        "findings": [
            {
                "finding_id": str(item.id),
                "category": item.category.value,
                "action": item.action,
                "style": item.style,
                "style_option": item.style_option,
                "source_span": item.span.model_dump(),
                "reviewed_span": mappings[item.id].preview_span.model_dump(),
            }
            for item in findings.findings
        ],
    }


def generate_report(report: dict, now: datetime) -> bytes:
    return (
        json.dumps({**report, "generated_at": now.isoformat()}, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
