"""Maintenance's global rows are isolated in the existing disposable test database."""

import hashlib
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.durable import AttemptEvent
from app.db.maintenance import MaintenanceRun
from app.factory import create_app

TOKEN = "synthetic-maintenance-token-with-more-than-32-bytes"


@pytest.fixture
def maintenance_site(intake_site):
    engine = intake_site[2]

    def clear():
        with Session(engine) as session, session.begin():
            session.execute(delete(MaintenanceRun))
            session.execute(
                delete(AttemptEvent).where(
                    AttemptEvent.scope.in_(["maintenance", "maintenance_denied"])
                )
            )

    clear()
    try:
        yield intake_site
    finally:
        clear()


@contextmanager
def configured(site, *, engine=None):
    settings = site[0].app.state.settings.model_copy(update={"maintenance_token_sha256": None})
    # Go through validation rather than bypassing the digest validator.
    settings = type(settings)(
        **(
            settings.model_dump()
            | {"maintenance_token_sha256": hashlib.sha256(TOKEN.encode()).hexdigest()}
        ),
        _env_file=None,
    )
    with TestClient(create_app(settings, engine=engine or site[2])) as client:
        yield client
