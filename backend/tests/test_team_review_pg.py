from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.accounts.memberships import restore_member, revoke_member
from app.cleanup.service import purge_unavailable_content
from app.db.crypto import KeyRing, ProtectedValue
from app.db.models import AuditEvent, Document, Membership
from app.db.rotate_keys import rotate_comments
from app.db.team_review import FindingComment, ReviewApproval, ReviewHandoff
from tests.intake_support import _draft_body, _login


def _setup(site):
    owner, reviewer, engine, workspace, owner_id = site
    headers = _login(owner, "intake-owner@example.invalid")
    review_headers = _login(reviewer, "intake-other@example.invalid")
    reviewer_id = UUID(reviewer.get("/api/v1/auth/session").json()["user_id"])
    with Session(engine) as session, session.begin():
        session.get(Membership, (workspace, owner_id)).role = "administrator"
        session.get(Membership, (workspace, reviewer_id)).role = "administrator"
    version = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace, source="😀 Contact nora@example.com", categories=["email"]),
        headers=headers,
    ).json()["version"]
    base = f"/api/v1/documents/{version['document_id']}"
    scanned = owner.post(base + "/scan", json={"expected": version}, headers=headers).json()
    return (
        owner,
        reviewer,
        engine,
        workspace,
        owner_id,
        reviewer_id,
        headers,
        review_headers,
        base,
        scanned,
    )


def _decision(client, base, finding, version, headers, action="redact"):
    response = client.post(
        base + f"/findings/{finding}/decision",
        json={
            "expected": version,
            "action": action,
            "keep_reason": "intended_disclosure" if action == "keep" else None,
            "group_scope": False,
            "affected_finding_ids": [finding],
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["version"]


def test_explicit_handoff_comment_approval_exact_export_and_revocation(intake_site):
    owner, reviewer, engine, workspace, _owner_id, reviewer_id, headers, rh, base, scanned = _setup(
        intake_site
    )
    version, finding = scanned["version"], scanned["suggestions"][0]["finding_id"]
    assert reviewer.get(base + "/source").status_code == 404  # administrator alone has no grant
    assert reviewer.get(base + "/teammates").status_code == 404
    body = {"expected": version, "reviewer_id": str(reviewer_id), "require_approval": True}
    assert (
        owner.put(base + "/handoff", json=body, headers={"Origin": headers["Origin"]}).status_code
        == 403
    )
    granted = owner.put(base + "/handoff", json=body, headers=headers)
    assert granted.status_code == 200, granted.text
    version = granted.json()["version"]
    assert owner.put(base + "/handoff", json=body, headers=headers).status_code == 409
    source = reviewer.get(base + "/source")
    assert source.status_code == 200 and source.json()["can_edit"] is False
    assert reviewer.get(base + "/preview").status_code == 200
    assert reviewer.get(base + "/findings").status_code == 200
    index = reviewer.get(f"/api/v1/workspaces/{workspace}/documents").json()
    assert len(index) == 1 and index[0]["is_owner"] is False
    assert (
        reviewer.put(
            base + "/source", json={"expected": version, "source": "forbidden"}, headers=rh
        ).status_code
        == 404
    )
    assert reviewer.delete(base, headers=rh).status_code == 404
    assert reviewer.post(base + "/scan", json={"expected": version}, headers=rh).status_code == 404
    comment_id = uuid4()
    comment = {
        "id": str(comment_id),
        "expected": version,
        "text": "Fictional private comment 😀 Café 東京",
    }
    assert (
        reviewer.post(base + f"/findings/{finding}/comments", json=comment, headers=rh).status_code
        == 201
    )
    assert (
        reviewer.post(base + f"/findings/{finding}/comments", json=comment, headers=rh).status_code
        == 201
    )
    assert len(owner.get(base + f"/findings/{finding}/comments").json()) == 1
    with Session(engine) as session:
        row = session.get(FindingComment, comment_id)
        assert b"Fictional private comment" not in row.text_ciphertext
        assert all(
            "Fictional private" not in event.event_code for event in session.query(AuditEvent).all()
        )
    version = _decision(reviewer, base, finding, version, rh)
    assert (
        reviewer.post(
            base + "/complete", json={"expected": version, "confirmed_preview": True}, headers=rh
        ).status_code
        == 404
    )
    assert (
        reviewer.post(
            base + "/approval", json={"expected": version, "confirmed_preview": True}, headers=rh
        ).status_code
        == 409
    )
    assert (
        owner.post(
            base + "/complete",
            json={"expected": version, "confirmed_preview": True},
            headers=headers,
        ).status_code
        == 200
    )
    export = {"expected": version, "event_id": str(uuid4())}
    assert (
        owner.post(base + "/exports/txt", json=export, headers=headers).json()["code"]
        == "second_approval_required"
    )
    assert (
        owner.post(
            base + "/exports/copy-payload", json={"expected": version}, headers=headers
        ).status_code
        == 409
    )
    assert (
        owner.post(
            base + "/approval",
            json={"expected": version, "confirmed_preview": True},
            headers=headers,
        ).status_code
        == 404
    )
    assert (
        reviewer.post(
            base + "/approval", json={"expected": version, "confirmed_preview": False}, headers=rh
        ).status_code
        == 409
    )
    approved = reviewer.post(
        base + "/approval", json={"expected": version, "confirmed_preview": True}, headers=rh
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["approved_at"]
    assert (
        owner.post(base + "/exports/txt", json=export, headers=headers).content
        == "😀 Contact [REDACTED]".encode()
    )
    assert reviewer.post(base + "/exports/txt", json=export, headers=rh).status_code == 404
    revised = _decision(owner, base, finding, version, headers, action="keep")
    assert owner.get(base + "/handoff").json()["approved_at"] is None
    assert (
        reviewer.post(
            base + "/approval", json={"expected": version, "confirmed_preview": True}, headers=rh
        ).status_code
        == 409
    )
    assert (
        owner.post(
            base + "/complete",
            json={"expected": revised, "confirmed_preview": True},
            headers=headers,
        ).status_code
        == 200
    )
    assert (
        owner.post(
            base + "/exports/txt",
            json={"expected": revised, "event_id": str(uuid4())},
            headers=headers,
        ).status_code
        == 409
    )
    revoked = owner.put(
        base + "/handoff",
        json={"expected": revised, "reviewer_id": None, "require_approval": True},
        headers=headers,
    )
    assert revoked.status_code == 200
    for path in ("/source", "/preview", "/findings", f"/findings/{finding}/comments", "/handoff"):
        assert reviewer.get(base + path).status_code == 404
    assert reviewer.get(f"/api/v1/workspaces/{workspace}/documents").json() == []


def test_membership_restore_does_not_restore_grant_comments_rotate_and_expire(intake_site):
    owner, reviewer, engine, workspace, owner_id, reviewer_id, headers, _rh, base, scanned = _setup(
        intake_site
    )
    version = owner.put(
        base + "/handoff",
        json={
            "expected": scanned["version"],
            "reviewer_id": str(reviewer_id),
            "require_approval": True,
        },
        headers=headers,
    ).json()["version"]
    finding = scanned["suggestions"][0]["finding_id"]
    comment_id = uuid4()
    assert (
        owner.post(
            base + f"/findings/{finding}/comments",
            json={
                "id": str(comment_id),
                "expected": version,
                "text": "Synthetic discussion for rotation",
            },
            headers=headers,
        ).status_code
        == 201
    )
    settings = owner.app.state.settings
    previous = settings.content_keys["test"].get_secret_value().encode()
    rotated = KeyRing("new", {"test": previous, "new": Fernet.generate_key()})
    with Session(engine) as session, session.begin():
        assert rotate_comments(session, rotated) == 1
    with Session(engine) as session:
        row = session.get(FindingComment, comment_id)
        assert (
            rotated.decrypt_text(ProtectedValue(row.text_ciphertext, row.text_key_id))
            == "Synthetic discussion for rotation"
        )
    with Session(engine) as session:
        revoke_member(
            session,
            workspace_id=workspace,
            actor_id=owner_id,
            user_id=reviewer_id,
            now=datetime.now(UTC),
        )
    with Session(engine) as session:
        restore_member(session, workspace_id=workspace, actor_id=owner_id, user_id=reviewer_id)
    _login(reviewer, "intake-other@example.invalid")
    assert reviewer.get(base + "/source").status_code == 404
    with Session(engine) as session, session.begin():
        row = session.get(Document, version["document_id"])
        row.created_at = datetime.now(UTC) - timedelta(days=10)
        row.expires_at = datetime.now(UTC) - timedelta(days=1)
    assert owner.get(base + "/handoff").status_code == 410
    purge_unavailable_content(engine, now=datetime.now(UTC))
    with Session(engine) as session:
        assert session.get(FindingComment, comment_id) is None
        assert session.get(ReviewHandoff, UUID(version["document_id"])) is None
        assert (
            session.query(ReviewApproval)
            .filter(ReviewApproval.document_id == version["document_id"])
            .count()
            == 0
        )
