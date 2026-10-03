"""Real device ownership, coarse labels, revocation and bounded last-seen writes."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.security import _digest, read_session
from app.cleanup.service import purge_unavailable_content
from app.db.models import Session as StoredSession
from tests.intake_support import ORIGIN, PASSWORD, _login


def test_devices_show_coarse_labels_and_revoke_only_the_owners_sessions(intake_site):
    owner, other, _, _, _ = intake_site
    response = owner.post(
        "/api/v1/auth/sign-in",
        headers={
            "Origin": ORIGIN,
            "User-Agent": "Mozilla Windows Chrome/123.0 private-useragent-canary",
        },
        json={"email": "intake-owner@example.invalid", "password": PASSWORD},
    )
    headers = {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}
    _login(other, "intake-owner@example.invalid")
    rows = owner.get("/api/v1/auth/sessions").json()
    assert len(rows) == 2 and sum(row["current"] for row in rows) == 1
    current = next(row for row in rows if row["current"])
    assert current["device_label"] == "Chrome · Windows"
    assert "private-useragent-canary" not in str(rows) and "127.0.0.1" not in str(rows)
    target = next(row for row in rows if not row["current"])
    assert (
        owner.post(f"/api/v1/auth/sessions/{target['id']}/revoke", headers=headers).status_code
        == 204
    )
    assert other.get("/api/v1/auth/session").status_code == 401
    foreign_headers = _login(other, "intake-other@example.invalid")
    assert (
        other.post(
            f"/api/v1/auth/sessions/{current['id']}/revoke", headers=foreign_headers
        ).status_code
        == 404
    )
    assert owner.get("/api/v1/auth/session").status_code == 200
    _login(other, "intake-owner@example.invalid")
    assert owner.post("/api/v1/auth/sessions/revoke-others", headers=headers).status_code == 204
    assert other.get("/api/v1/auth/session").status_code == 401
    assert len(owner.get("/api/v1/auth/sessions").json()) == 1


def test_last_seen_writes_after_five_minutes_and_cleanup_keeps_recent_revocations(intake_site):
    owner, _, engine, _, _ = intake_site
    _login(owner, "intake-owner@example.invalid")
    token = owner.cookies.get("openanonymi_session")
    with Session(engine) as session:
        record = session.scalar(
            select(StoredSession).where(StoredSession.token_hash == _digest(token))
        )
        created, row_id = record.last_seen_at, record.id
    with Session(engine) as session, session.begin():
        read_session(session, token=token, now=created + timedelta(minutes=4))
        assert session.get(StoredSession, row_id).last_seen_at == created
    with Session(engine) as session, session.begin():
        read_session(session, token=token, now=created + timedelta(minutes=5))
        assert session.get(StoredSession, row_id).last_seen_at == created + timedelta(minutes=5)
    now = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        session.get(StoredSession, row_id).revoked_at = now - timedelta(hours=23)
    purge_unavailable_content(engine, now=now)
    with Session(engine) as session:
        assert session.get(StoredSession, row_id) is not None
    purge_unavailable_content(engine, now=now + timedelta(hours=2))
    with Session(engine) as session:
        assert session.get(StoredSession, row_id) is None
