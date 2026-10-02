"""Local model suggestions persist as pending findings under the normal review gate."""

from tests.intake_support import _draft_body, _login


def test_new_categories_scan_and_manual_correction(intake_site):
    owner, other, _engine, workspace, _user = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    _login(other, "intake-other@example.invalid")
    source = "😀 Nora Caldwell works at Microsoft in London. Network 192.0.2.17."
    created = owner.post(
        "/api/v1/documents",
        json=_draft_body(
            workspace,
            source=source,
            categories=["person", "organization", "location", "identifier"],
        ),
        headers=headers,
    )
    assert created.status_code == 201, created.text
    version = created.json()["version"]
    base = f"/api/v1/documents/{version['document_id']}"
    assert (
        other.post(
            base + "/scan",
            json={"expected": version},
            headers=_login(other, "intake-other@example.invalid"),
        ).status_code
        == 404
    )
    scanned = owner.post(base + "/scan", json={"expected": version}, headers=headers)
    assert scanned.status_code == 200, scanned.text
    categories = {item["category"] for item in scanned.json()["suggestions"]}
    assert categories == {"person", "organization", "location", "identifier"}
    current = scanned.json()["version"]
    findings = owner.get(base + "/findings").json()
    assert all(item["action"] is None for item in findings["findings"])
    assert (
        owner.post(
            base + "/complete",
            json={"expected": current, "confirmed_preview": True},
            headers=headers,
        ).status_code
        == 422
    )
    place = next(item for item in findings["findings"] if item["category"] == "location")
    changed = owner.put(
        base + "/findings/" + place["finding_id"],
        json={"expected": current, "span": place["span"], "category": "custom"},
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    assert (
        next(
            item for item in changed.json()["findings"] if item["finding_id"] == place["finding_id"]
        )["category"]
        == "custom"
    )
