"""Replace only selected Unicode code-point spans in source order."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from app.contracts import DecisionAction, SourceSpan


class InvalidTransformation(ValueError):
    """A span or decision cannot be applied without ambiguity."""


@dataclass(frozen=True)
class TransformFinding:
    finding_id: UUID
    span: SourceSpan
    action: DecisionAction | None
    label: str | None


@dataclass(frozen=True)
class SpanMapping:
    finding_id: UUID
    source_span: SourceSpan
    preview_span: SourceSpan
    action: DecisionAction | None


@dataclass(frozen=True)
class TransformedText:
    text: str
    mappings: tuple[SpanMapping, ...]
    unresolved_ids: tuple[UUID, ...]

    @property
    def complete(self) -> bool:
        return not self.unresolved_ids


def transform_text(source: str, findings: Sequence[TransformFinding]) -> TransformedText:
    """Build a complete or provisional preview without global string replacement.

    Unresolved spans remain unchanged and are returned explicitly. Intersecting
    spans fail before output is built, so no caller can double-replace text.
    """
    ordered = sorted(findings, key=lambda item: (item.span.start, item.span.end, item.finding_id))
    cursor = 0
    preview_cursor = 0
    chunks: list[str] = []
    mappings: list[SpanMapping] = []
    unresolved: list[UUID] = []
    for finding in ordered:
        span = finding.span
        if span.start < cursor:
            raise InvalidTransformation("Findings have intersecting source spans.")
        if span.start < 0 or span.end <= span.start or span.end > len(source):
            raise InvalidTransformation("A finding is outside the source text.")
        unchanged = source[cursor : span.start]
        chunks.append(unchanged)
        preview_cursor += len(unchanged)
        if finding.action == DecisionAction.LABEL:
            if not finding.label:
                raise InvalidTransformation("A Label decision has no group label.")
            replacement = finding.label
        elif finding.action == DecisionAction.REDACT:
            replacement = "[REDACTED]"
        elif finding.action in (DecisionAction.KEEP, None):
            replacement = source[span.start : span.end]
            if finding.action is None:
                unresolved.append(finding.finding_id)
        else:
            raise InvalidTransformation("Unsupported review decision.")
        chunks.append(replacement)
        mappings.append(
            SpanMapping(
                finding_id=finding.finding_id,
                source_span=span,
                preview_span=SourceSpan(
                    start=preview_cursor, end=preview_cursor + len(replacement)
                ),
                action=finding.action,
            )
        )
        preview_cursor += len(replacement)
        cursor = span.end
    chunks.append(source[cursor:])
    return TransformedText("".join(chunks), tuple(mappings), tuple(unresolved))


PreviewStatus = Literal["complete", "incomplete", "conflict"]
