from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.contracts import (
    CompletionRef,
    ConflictResponse,
    DocumentStatus,
    OwnershipContext,
    SourceSpan,
    VersionRef,
    WorkspaceRole,
    service_metadata,
)
from app.lifecycle import (
    InvalidTransition,
    completion_matches_current,
    require_content_available,
    require_transition,
)
from app.offsets import slice_source


def test_code_point_spans_include_emoji_and_preserve_line_endings():
    source = "A😀é\r\n東京"
    assert slice_source(source, SourceSpan(start=1, end=3)) == "😀é"
    assert slice_source(source, SourceSpan(start=3, end=5)) == "\r\n"
    with pytest.raises(ValueError):
        slice_source(source, SourceSpan(start=0, end=9))
    with pytest.raises(ValidationError):
        SourceSpan(start=2, end=2)


def test_completion_binds_to_revision_decisions_and_settings():
    current = VersionRef(
        document_id=uuid4(), source_revision_id=uuid4(), decision_version=4, settings_version=2
    )
    completion = CompletionRef(version=current, confirmed_at=datetime.now(UTC))
    assert completion_matches_current(completion, current)
    assert not completion_matches_current(None, current)
    assert not completion_matches_current(
        completion, current.model_copy(update={"decision_version": 5})
    )
    assert not completion_matches_current(
        completion, current.model_copy(update={"settings_version": 3})
    )


def test_terminal_states_deny_content_and_invalid_transitions():
    require_transition(DocumentStatus.NEEDS_REVIEW, DocumentStatus.READY)
    with pytest.raises(InvalidTransition):
        require_transition(DocumentStatus.DELETED, DocumentStatus.READY)
    with pytest.raises(InvalidTransition):
        require_content_available(DocumentStatus.EXPIRED)


def test_metadata_exposes_server_limits_without_sample_data():
    metadata = service_metadata().model_dump(mode="json")
    assert metadata["source_max_utf8_bytes"] == 1_048_576
    assert metadata["source_max_code_points"] == 100_000
    assert "needs_review" in metadata["document_statuses"]


def test_ownership_and_conflict_contracts_serialize_without_content():
    actor = uuid4()
    workspace = uuid4()
    owner = OwnershipContext(actor_id=actor, workspace_id=workspace, role=WorkspaceRole.MEMBER)
    version = VersionRef(
        document_id=uuid4(), source_revision_id=uuid4(), decision_version=2, settings_version=1
    )
    conflict = ConflictResponse(current_version=version)
    assert owner.model_dump(mode="json")["role"] == "member"
    assert conflict.model_dump(mode="json")["current_version"]["decision_version"] == 2
    assert "source_text" not in conflict.model_dump_json()
