"""Paste, file, and revision workflow on an explicit local PostgreSQL database."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import (
    Finding,
)
from tests.intake_support import ORIGIN, _draft_body, _login


def test_manual_finding_boundary_correction_removal_and_overlap(intake_site):
    owner, other, engine, workspace_id, _owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    _login(other, "intake-other@example.invalid")
    source = "😀 Alice wrote alice@example.com. Alice called."
    created = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, source=source, categories=[]),
        headers=headers,
    )
    version = created.json()["version"]
    path = f"/api/v1/documents/{version['document_id']}/findings"
    assert owner.get(path).json()["findings"] == []
    assert other.get(path).status_code == 404
    first_start = source.index("Alice")
    added = owner.post(
        path,
        json={
            "expected": version,
            "span": {"start": first_start, "end": first_start + len("Alice")},
            "category": "person",
        },
        headers=headers,
    )
    assert added.status_code == 200, added.text
    first = added.json()["findings"][0]
    assert source[first["span"]["start"] : first["span"]["end"]] == "Alice"
    assert first["action"] is None
    assert first["origin"] == "manual"
    next_version = added.json()["version"]
    assert next_version["decision_version"] == version["decision_version"] + 1
    assert (
        owner.get(f"/api/v1/documents/{version['document_id']}/source").json()["status"]
        == "needs_review"
    )

    overlap = owner.post(
        path,
        json={
            "expected": next_version,
            "span": {"start": first_start + 1, "end": first_start + 4},
            "category": "custom",
        },
        headers=headers,
    )
    assert overlap.status_code == 422
    assert overlap.json()["code"] == "overlapping_finding"
    assert owner.get(path).json()["version"] == next_version
    whitespace = owner.post(
        path,
        json={
            "expected": next_version,
            "span": {"start": first_start - 1, "end": first_start},
            "category": "person",
        },
        headers=headers,
    )
    assert whitespace.status_code == 422

    correction = owner.put(
        f"{path}/{first['finding_id']}",
        json={
            "expected": next_version,
            "span": {"start": first_start, "end": first_start + 4},
            "category": "person",
        },
        headers=headers,
    )
    assert correction.status_code == 200, correction.text
    corrected_version = correction.json()["version"]
    assert correction.json()["findings"][0]["span"]["end"] == first_start + 4
    assert corrected_version["decision_version"] == next_version["decision_version"] + 1
    stale = owner.put(
        f"{path}/{first['finding_id']}",
        json={
            "expected": next_version,
            "span": {"start": first_start, "end": first_start + 5},
            "category": "person",
        },
        headers=headers,
    )
    assert stale.status_code == 409
    assert stale.json()["current_version"] == corrected_version
    denied = other.post(
        f"{path}/{first['finding_id']}/remove",
        json={"expected": corrected_version},
        headers={
            "Origin": ORIGIN,
            "X-CSRF-Token": other.get("/api/v1/auth/session").json()["csrf_token"],
        },
    )
    assert denied.status_code == 404
    removed = owner.post(
        f"{path}/{first['finding_id']}/remove",
        json={"expected": corrected_version},
        headers=headers,
    )
    assert removed.status_code == 200
    assert removed.json()["findings"] == []
    assert (
        removed.json()["version"]["decision_version"] == corrected_version["decision_version"] + 1
    )
    with Session(engine) as session:
        finding = session.get(Finding, UUID(first["finding_id"]))
        assert finding.removed_at is not None


def test_exact_matches_groups_and_decisions_are_versioned_and_owner_scoped(intake_site):
    owner, other, _engine, workspace_id, _owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    _login(other, "intake-other@example.invalid")
    source = "😀 Alice met Alice. Alicia met Alice."
    created = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, source=source, categories=[]),
        headers=headers,
    )
    version = created.json()["version"]
    path = f"/api/v1/documents/{version['document_id']}/findings"
    first = source.index("Alice")
    added = owner.post(
        path,
        json={
            "expected": version,
            "span": {"start": first, "end": first + 5},
            "category": "person",
        },
        headers=headers,
    ).json()
    version = added["version"]
    first_id = added["findings"][0]["finding_id"]
    matches_path = f"{path}/{first_id}/exact-matches"
    offered = owner.get(matches_path)
    assert offered.status_code == 200
    assert [source[span["start"] : span["end"]] for span in offered.json()["spans"]] == [
        "Alice",
        "Alice",
    ]
    assert other.get(matches_path).status_code == 404
    second_span = offered.json()["spans"][0]
    second = owner.post(
        matches_path, json={"expected": version, "span": second_span}, headers=headers
    )
    assert second.status_code == 200, second.text
    version = second.json()["version"]
    second_id = second.json()["findings"][1]["finding_id"]
    stale = owner.post(
        matches_path, json={"expected": added["version"], "span": second_span}, headers=headers
    )
    assert stale.status_code == 409
    assert (
        owner.post(
            matches_path,
            json={
                "expected": version,
                "span": {"start": source.index("Alicia"), "end": source.index("Alicia") + 6},
            },
            headers=headers,
        ).json()["code"]
        == "not_exact_match"
    )

    first_decision = owner.post(
        f"{path}/{first_id}/decision",
        json={
            "expected": version,
            "action": "label",
            "affected_finding_ids": [first_id],
        },
        headers=headers,
    )
    assert first_decision.status_code == 200, first_decision.text
    version = first_decision.json()["version"]
    label = first_decision.json()["findings"][0]["label"]
    assert label == "PERSON_001"
    assert first_decision.json()["findings"][1]["label"] is None
    assert (
        owner.post(
            f"{path}/{second_id}/decision",
            json={
                "expected": version,
                "action": "keep",
                "affected_finding_ids": [second_id],
            },
            headers=headers,
        ).json()["code"]
        == "keep_reason_required"
    )
    merged = owner.post(
        f"{path}/{second_id}/merge",
        json={
            "expected": version,
            "target_finding_id": first_id,
        },
        headers=headers,
    )
    assert merged.status_code == 200, merged.text
    version = merged.json()["version"]
    assert {item["label"] for item in merged.json()["findings"]} == {label}
    wrong_scope = owner.post(
        f"{path}/{first_id}/decision",
        json={
            "expected": version,
            "action": "redact",
            "group_scope": True,
            "affected_finding_ids": [first_id],
        },
        headers=headers,
    )
    assert wrong_scope.status_code == 422
    group_decision = owner.post(
        f"{path}/{first_id}/decision",
        json={
            "expected": version,
            "action": "redact",
            "group_scope": True,
            "affected_finding_ids": [first_id, second_id],
        },
        headers=headers,
    )
    assert group_decision.status_code == 200, group_decision.text
    version = group_decision.json()["version"]
    assert {item["action"] for item in group_decision.json()["findings"]} == {"redact"}
    split = owner.post(f"{path}/{second_id}/split", json={"expected": version}, headers=headers)
    assert split.status_code == 200, split.text
    version = split.json()["version"]
    assert {item["label"] for item in split.json()["findings"]} == {label, "PERSON_002"}
    keep = owner.post(
        f"{path}/{second_id}/decision",
        json={
            "expected": version,
            "action": "keep",
            "keep_reason": "intended_disclosure",
            "affected_finding_ids": [second_id],
        },
        headers=headers,
    )
    assert keep.status_code == 200, keep.text
    assert keep.json()["findings"][1]["keep_reason"] == "intended_disclosure"
    version = keep.json()["version"]
    alias_start = source.index("Alicia")
    alias = owner.post(
        path,
        json={
            "expected": version,
            "span": {"start": alias_start, "end": alias_start + 6},
            "category": "person",
        },
        headers=headers,
    ).json()
    alias_id = next(
        row["finding_id"] for row in alias["findings"] if row["span"]["start"] == alias_start
    )
    alias_label = owner.post(
        f"{path}/{alias_id}/decision",
        json={
            "expected": alias["version"],
            "action": "label",
            "affected_finding_ids": [alias_id],
        },
        headers=headers,
    ).json()
    assert (
        next(row["label"] for row in alias_label["findings"] if row["finding_id"] == alias_id)
        == "PERSON_003"
    )
    variant_merge = owner.post(
        f"{path}/{alias_id}/merge",
        json={"expected": alias_label["version"], "target_finding_id": first_id},
        headers=headers,
    )
    assert variant_merge.status_code == 200, variant_merge.text
    labels = {row["finding_id"]: row["label"] for row in variant_merge.json()["findings"]}
    assert labels == {first_id: "PERSON_001", second_id: "PERSON_002", alias_id: "PERSON_001"}


def test_review_undo_restores_multiple_edits_without_reusing_labels(intake_site):
    owner, other, _engine, workspace_id, _owner_id = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    _login(other, "intake-other@example.invalid")
    source = "😀 Ada met Ada."
    created = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace_id, source=source, categories=[]),
        headers=headers,
    )
    version = created.json()["version"]
    path = f"/api/v1/documents/{version['document_id']}/findings"
    undo_path = f"/api/v1/documents/{version['document_id']}/review/undo"
    first = source.index("Ada")
    added = owner.post(
        path,
        json={
            "expected": version,
            "span": {"start": first, "end": first + 3},
            "category": "person",
        },
        headers=headers,
    ).json()
    version = added["version"]
    first_id = added["findings"][0]["finding_id"]
    labeled = owner.post(
        f"{path}/{first_id}/decision",
        json={
            "expected": version,
            "action": "label",
            "affected_finding_ids": [first_id],
        },
        headers=headers,
    ).json()
    version = labeled["version"]
    assert labeled["findings"][0]["label"] == "PERSON_001"
    second = source.rindex("Ada")
    added_second = owner.post(
        path,
        json={
            "expected": version,
            "span": {"start": second, "end": second + 3},
            "category": "person",
        },
        headers=headers,
    ).json()
    version = added_second["version"]
    second_id = added_second["findings"][1]["finding_id"]
    merged = owner.post(
        f"{path}/{second_id}/merge",
        json={
            "expected": version,
            "target_finding_id": first_id,
        },
        headers=headers,
    ).json()
    version = merged["version"]
    assert {item["label"] for item in merged["findings"]} == {"PERSON_001"}
    redacted = owner.post(
        f"{path}/{first_id}/decision",
        json={
            "expected": version,
            "action": "redact",
            "group_scope": True,
            "affected_finding_ids": [first_id, second_id],
        },
        headers=headers,
    ).json()
    version = redacted["version"]
    assert {item["action"] for item in redacted["findings"]} == {"redact"}
    assert (
        other.post(
            undo_path,
            json={"expected": version},
            headers={
                "Origin": ORIGIN,
                "X-CSRF-Token": other.get("/api/v1/auth/session").json()["csrf_token"],
            },
        ).status_code
        == 404
    )

    restored_decisions = owner.post(undo_path, json={"expected": version}, headers=headers)
    assert restored_decisions.status_code == 200, restored_decisions.text
    version = restored_decisions.json()["version"]
    assert [item["action"] for item in restored_decisions.json()["findings"]] == ["label", None]
    assert (
        owner.post(undo_path, json={"expected": redacted["version"]}, headers=headers).status_code
        == 409
    )
    unmerged = owner.post(undo_path, json={"expected": version}, headers=headers).json()
    version = unmerged["version"]
    assert [item["label"] for item in unmerged["findings"]] == ["PERSON_001", None]
    unadded = owner.post(undo_path, json={"expected": version}, headers=headers).json()
    version = unadded["version"]
    assert len(unadded["findings"]) == 1
    unlabeled = owner.post(undo_path, json={"expected": version}, headers=headers).json()
    version = unlabeled["version"]
    assert unlabeled["findings"][0]["label"] is None
    assert unlabeled["findings"][0]["action"] is None
    empty = owner.post(undo_path, json={"expected": version}, headers=headers).json()
    assert empty["findings"] == []
    activity = owner.get(f"/api/v1/workspaces/{workspace_id}/activity").json()
    codes = [item["event_code"] for item in activity["own_events"]]
    assert codes.count("finding_added") == 2
    assert codes.count("group_merged") == 1
    assert codes.count("review_decision_saved") == 2
    assert codes.count("review_edit_undone") == 5
    assert "Ada" not in str(activity)
    assert (
        owner.post(undo_path, json={"expected": empty["version"]}, headers=headers).json()["code"]
        == "nothing_to_undo"
    )

    new_finding = owner.post(
        path,
        json={
            "expected": empty["version"],
            "span": {"start": first, "end": first + 3},
            "category": "person",
        },
        headers=headers,
    ).json()
    new_id = new_finding["findings"][0]["finding_id"]
    new_label = owner.post(
        f"{path}/{new_id}/decision",
        json={
            "expected": new_finding["version"],
            "action": "label",
            "affected_finding_ids": [new_id],
        },
        headers=headers,
    ).json()
    assert new_label["findings"][0]["label"] == "PERSON_002"
