"""Actual HTTP setup for a synthetic style review, with no automatic decisions."""

from tests.intake_support import _draft_body


def draft(owner, headers, workspace, source, marks, **overrides):
    created = owner.post(
        "/api/v1/documents",
        json=_draft_body(workspace, source=source, categories=[], phone_region="GB", **overrides),
        headers=headers,
    )
    assert created.status_code == 201
    base = "/api/v1/documents/" + created.json()["version"]["document_id"]
    assert (
        owner.post(
            base + "/scan", json={"expected": created.json()["version"]}, headers=headers
        ).status_code
        == 200
    )
    state = owner.get(base + "/findings").json()
    for value, category in marks:
        start = source.index(value)
        added = owner.post(
            base + "/findings",
            json={
                "expected": state["version"],
                "span": {"start": start, "end": start + len(value)},
                "category": category,
            },
            headers=headers,
        )
        assert added.status_code == 200
        state = added.json()
    return base, state


def decide(owner, headers, base, state, finding, action, style="token", option=None, **extra):
    body = {
        "expected": state["version"],
        "action": action,
        "style": style,
        "style_option": option,
        "affected_finding_ids": [finding["finding_id"]],
        **extra,
    }
    return owner.post(
        base + "/findings/" + finding["finding_id"] + "/decision", json=body, headers=headers
    )
