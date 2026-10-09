"""Canonical preview responses refresh actual grants after output serialization."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document, Membership, User
from app.db.models import Session as StoredSession
from app.db.team_review import ReviewHandoff
from app.transformations.api import PreviewView
from tests.test_review_mutation_access_pg import decision
from tests.test_review_state_pg import prepare


@pytest.mark.parametrize(
    "change", ["session", "membership", "disabled", "expired", "deleted", "version"]
)
def test_late_preview_change_returns_neutral_denial(intake_site, monkeypatch, change):
    owner, _, engine, workspace, actor, headers, base, findings = prepare(intake_site)
    assert decision(owner, headers, base, findings).status_code == 200
    first = owner.get(base + "/preview")
    assert first.status_code == 200 and first.json()["text"] is not None
    document_id = UUID(findings["version"]["document_id"])
    original = PreviewView.model_dump_json

    def revoke(view, *args, **kwargs):
        payload = original(view, *args, **kwargs)
        with Session(engine) as session, session.begin():
            now = datetime.now(UTC)
            if change == "session":
                for row in session.scalars(
                    select(StoredSession).where(StoredSession.user_id == actor)
                ):
                    row.revoked_at = now
            elif change == "membership":
                session.get(Membership, (workspace, actor)).revoked_at = now
            elif change == "disabled":
                session.get(User, actor).disabled_at = now
            else:
                item = session.get(Document, document_id)
                if change == "expired":
                    item.created_at = now - timedelta(days=2)
                    item.expires_at = now - timedelta(seconds=1)
                elif change == "deleted":
                    item.status = "deleted"
                    item.deleted_at = now
                else:
                    item.decision_version += 1
        return payload

    monkeypatch.setattr(PreviewView, "model_dump_json", revoke)
    response = owner.get(base + "/preview")
    assert response.status_code in (401, 404, 409, 410)
    assert "Fictional" not in response.text and "EMAIL_001" not in response.text
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("change", ["handoff", "owner_disabled", "owner_membership"])
def test_late_reviewer_preview_grant_is_refreshed(intake_site, monkeypatch, change):
    owner, reviewer, engine, workspace, actor, headers, base, findings = prepare(intake_site)
    result = decision(owner, headers, base, findings)
    assert result.status_code == 200
    findings = result.json()
    reviewer_id = reviewer.get("/api/v1/auth/session").json()["user_id"]
    assert (
        owner.put(
            base + "/handoff",
            headers=headers,
            json={
                "expected": findings["version"],
                "reviewer_id": reviewer_id,
                "require_approval": False,
            },
        ).status_code
        == 200
    )
    assert reviewer.get(base + "/preview").status_code == 200
    original = PreviewView.model_dump_json

    def revoke(view, *args, **kwargs):
        payload = original(view, *args, **kwargs)
        with Session(engine) as session, session.begin():
            now = datetime.now(UTC)
            if change == "handoff":
                session.get(
                    ReviewHandoff, UUID(findings["version"]["document_id"])
                ).reviewer_id = None
            elif change == "owner_disabled":
                session.get(User, actor).disabled_at = now
            else:
                session.get(Membership, (workspace, actor)).revoked_at = now
        return payload

    monkeypatch.setattr(PreviewView, "model_dump_json", revoke)
    response = reviewer.get(base + "/preview")
    assert response.status_code == 404
    assert "Fictional" not in response.text and "EMAIL_001" not in response.text
