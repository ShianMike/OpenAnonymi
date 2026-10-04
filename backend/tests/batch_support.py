from tests.intake_support import _login


def batch_client(site, **overrides):
    owner, _, _, workspace, _ = site
    headers = _login(owner, "intake-owner@example.invalid")
    response = owner.post(
        "/api/v1/batches",
        json={
            "workspace_id": str(workspace),
            "name": "Fictional batch 😀",
            "categories": ["email"],
            "phone_region": "GB",
            **overrides,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return owner, headers, f"/api/v1/batches/{response.json()['id']}"


def upload(owner, headers, base, source=b"Fictional nora@example.test", filename="private.txt"):
    response = owner.post(base + "/documents", files={"file": (filename, source)}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["version"]


def review_and_confirm(owner, headers, version, action="redact"):
    base = f"/api/v1/documents/{version['document_id']}"
    scanned = owner.post(base + "/scan", json={"expected": version}, headers=headers)
    assert scanned.status_code == 200, scanned.text
    state = owner.get(base + "/findings").json()
    for finding in state["findings"]:
        if finding["action"] is None:
            saved = owner.post(
                base + f"/findings/{finding['finding_id']}/decision",
                json={
                    "expected": state["version"],
                    "action": action,
                    "group_scope": False,
                    "affected_finding_ids": [finding["finding_id"]],
                },
                headers=headers,
            )
            assert saved.status_code == 200, saved.text
            state = saved.json()
    confirmed = owner.post(
        base + "/complete",
        json={
            "expected": state["version"],
            "confirmed_preview": True,
        },
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    return base, state, owner.get(base + "/preview").json()["text"]
