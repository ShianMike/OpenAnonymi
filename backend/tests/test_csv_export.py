"""Removed output formats fail before opening a database or rendering content."""

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.exports.service import ExportConflict, generate_output


def test_csv_output_is_not_an_available_service_format():
    engine = MagicMock()
    with pytest.raises(ExportConflict, match="supported reviewed output format"):
        generate_output(engine, document_id=uuid4(), actor_id=uuid4(), expected=None,
                        event_id=uuid4(), keys=None, now=datetime.now(UTC), format="csv")
    engine.connect.assert_not_called()
