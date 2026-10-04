"""Conditional review reads require fresh access after the content is assembled."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.db.models import Document, Membership, User, Workspace
from app.db.models import Session as StoredSession
from app.reviews.state_api import ReviewStateView
from tests.intake_support import ORIGIN, _login
from tests.test_review_state_pg import prepare


def test_conditional_body_parity_zero_body_and_session_bound_validator(intake_site):
    owner, _, _, _, _, _, base, _ = prepare(intake_site)
    first = owner.get(base + "/review-state")
    assert first.status_code == 200
    tag = first.headers["etag"]
    assert tag.startswith('"rs1-') and len(tag) == 70
    for candidate in (tag, "W/" + tag, '"other", ' + tag, "*"):
        same = owner.get(base + "/review-state", headers={"If-None-Match": candidate})
        assert same.status_code == 304 and same.content == b""
        assert same.headers["etag"] == tag
        assert same.headers["cache-control"] == "no-store"
        assert "Cookie" in same.headers["vary"]
    _login(owner, "intake-owner@example.invalid")
    fresh = owner.get(base + "/review-state", headers={"If-None-Match": tag})
    assert fresh.status_code == 200 and fresh.json() == first.json()
    assert fresh.headers["etag"] != tag


def test_changed_content_and_nonmatching_headers_cannot_reuse_old_snapshot(intake_site):
    owner, _, _, _, _, headers, base, findings = prepare(intake_site)
    first = owner.get(base + "/review-state")
    tag = first.headers["etag"]
    item = findings["findings"][0]
    change = owner.post(
        base + "/findings/" + item["finding_id"] + "/decision",
        json={
            "expected": findings["version"],
            "action": "redact",
            "keep_reason": None,
            "group_scope": False,
            "affected_finding_ids": [item["finding_id"]],
        },
        headers=headers,
    )
    assert change.status_code == 200
    response = owner.get(base + "/review-state", headers={"If-None-Match": tag})
    assert response.status_code == 200 and response.headers["etag"] != tag
    assert response.json()["preview"]["text"] == "Fictional 😀 [REDACTED]"
    for candidate in ('"bad"', "x" * 4097, ",".join(['"bad"'] * 17), b'"\xe9"'):
        assert (
            owner.get(base + "/review-state", headers={"If-None-Match": candidate}).status_code
            == 200
        )


@pytest.mark.parametrize("conditional", [False, True])
@pytest.mark.parametrize(
    "change", ["session", "disabled", "membership", "expired", "deleted", "version", "policy"]
)
def test_late_access_or_version_change_denies_even_a_matching_tag(
    intake_site, monkeypatch, conditional, change
):
    owner, _, engine, workspace, actor, _, base, findings = prepare(intake_site)
    tag = owner.get(base + "/review-state").headers["etag"]
    document_id = UUID(findings["version"]["document_id"])
    original = ReviewStateView.model_dump_json

    def after_serializing(view, *args, **kwargs):
        payload = original(view, *args, **kwargs)
        with Session(engine) as session, session.begin():
            now = datetime.now(UTC)
            if change == "session":
                for item in session.query(StoredSession).filter(StoredSession.user_id == actor):
                    item.revoked_at = now
            elif change == "disabled":
                session.get(User, actor).disabled_at = now
            elif change == "membership":
                session.get(Membership, (workspace, actor)).revoked_at = now
            elif change == "policy":
                session.get(Workspace, workspace).approval_policy = "always"
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

    monkeypatch.setattr(ReviewStateView, "model_dump_json", after_serializing)
    response = owner.get(
        base + "/review-state", headers={"If-None-Match": tag} if conditional else {}
    )
    assert response.status_code in (401, 404, 409, 410)
    assert "nora@example.test" not in response.text and "etag" not in response.headers


def test_reviewer_cached_read_denied_after_late_handoff_removal(intake_site, monkeypatch):
    owner, reviewer, engine, _, _, headers, base, findings = prepare(intake_site)
    reviewer_id = reviewer.get("/api/v1/auth/session").json()["user_id"]
    assignment = owner.put(
        base + "/handoff",
        headers=headers,
        json={
            "expected": findings["version"],
            "reviewer_id": reviewer_id,
            "require_approval": False,
        },
    )
    assert assignment.status_code == 200
    first = reviewer.get(base + "/review-state")
    assert first.status_code == 200 and first.json()["source"]["can_edit"] is False
    from app.db.team_review import ReviewHandoff

    original = ReviewStateView.model_dump_json

    def revoke(view, *args, **kwargs):
        payload = original(view, *args, **kwargs)
        with Session(engine) as session, session.begin():
            session.get(ReviewHandoff, UUID(findings["version"]["document_id"])).reviewer_id = None
        return payload

    monkeypatch.setattr(ReviewStateView, "model_dump_json", revoke)
    response = reviewer.get(
        base + "/review-state", headers={"If-None-Match": first.headers["etag"]}
    )
    assert response.status_code == 404 and "nora@example.test" not in response.text


def test_cross_origin_conditional_header_and_etag_are_exposed_only_to_allowed_origin(intake_site):
    owner, _, _, _, _, _, base, _ = prepare(intake_site)
    allowed = ORIGIN
    preflight = owner.options(
        base + "/review-state",
        headers={
            "Origin": allowed,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "If-None-Match",
        },
    )
    assert preflight.status_code == 200
    response = owner.get(base + "/review-state", headers={"Origin": allowed})
    assert "etag" in response.headers["access-control-expose-headers"].lower()
    foreign = owner.options(
        base + "/review-state",
        headers={
            "Origin": "https://foreign.example.invalid",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "If-None-Match",
        },
    )
    assert foreign.status_code == 400 and "access-control-allow-origin" not in foreign.headers
