"""Cached seed hashes must not share mutable account, app, or client state."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Membership, User


@pytest.mark.parametrize("repeat", range(2))
def test_seed_hash_reuse_keeps_each_workflow_case_fresh(intake_site, intake_password_hashes, repeat):
    owner, other, engine, workspace, _ = intake_site
    with Session(engine) as session, session.begin():
        users = session.scalars(
            select(User).join(Membership).where(Membership.workspace_id == workspace)
        ).all()
        assert len(users) == 2
        assert {user.password_hash for user in users} == set(intake_password_hashes)
        assert len(set(intake_password_hashes)) == 2
        assert all(value.startswith("$argon2id$") for value in intake_password_hashes)
        users[0].password_hash = f"changed-only-in-case-{repeat}"
    assert not owner.cookies and not other.cookies
    assert owner.app.state.settings.registration_enabled
    owner.cookies.set("fixture-only", str(repeat))
    owner.app.state.settings.registration_enabled = False
