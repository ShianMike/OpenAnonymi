"""Central public document state and completion-binding rules."""

from app.contracts import CompletionRef, DocumentStatus, VersionRef


class InvalidTransition(ValueError):
    pass


ALLOWED_TRANSITIONS: dict[DocumentStatus, frozenset[DocumentStatus]] = {
    DocumentStatus.DRAFT: frozenset(
        {
            DocumentStatus.SCANNING,
            DocumentStatus.NEEDS_REVIEW,
            DocumentStatus.FAILED,
            DocumentStatus.EXPIRED,
            DocumentStatus.DELETED,
        }
    ),
    DocumentStatus.SCANNING: frozenset(
        {
            DocumentStatus.NEEDS_REVIEW,
            DocumentStatus.FAILED,
            DocumentStatus.EXPIRED,
            DocumentStatus.DELETED,
        }
    ),
    DocumentStatus.NEEDS_REVIEW: frozenset(
        {
            DocumentStatus.SCANNING,
            DocumentStatus.READY,
            DocumentStatus.FAILED,
            DocumentStatus.EXPIRED,
            DocumentStatus.DELETED,
        }
    ),
    DocumentStatus.READY: frozenset(
        {
            DocumentStatus.NEEDS_REVIEW,
            DocumentStatus.SCANNING,
            DocumentStatus.EXPORTED,
            DocumentStatus.EXPIRED,
            DocumentStatus.DELETED,
        }
    ),
    DocumentStatus.EXPORTED: frozenset(
        {
            DocumentStatus.NEEDS_REVIEW,
            DocumentStatus.SCANNING,
            DocumentStatus.EXPIRED,
            DocumentStatus.DELETED,
        }
    ),
    DocumentStatus.FAILED: frozenset(
        {
            DocumentStatus.SCANNING,
            DocumentStatus.NEEDS_REVIEW,
            DocumentStatus.EXPIRED,
            DocumentStatus.DELETED,
        }
    ),
    DocumentStatus.EXPIRED: frozenset({DocumentStatus.DELETED}),
    DocumentStatus.DELETED: frozenset(),
}


def require_transition(current: DocumentStatus, target: DocumentStatus) -> None:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransition(f"Cannot change document status from {current} to {target}")


def completion_matches_current(completion: CompletionRef | None, current: VersionRef) -> bool:
    return completion is not None and completion.version == current


def require_content_available(status: DocumentStatus) -> None:
    if status in (DocumentStatus.EXPIRED, DocumentStatus.DELETED):
        raise InvalidTransition("Document content is unavailable")
