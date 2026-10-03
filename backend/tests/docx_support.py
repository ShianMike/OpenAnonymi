"""Real Word intake and reviewed output helpers for isolated PostgreSQL fixtures."""

from uuid import uuid4


def upload(owner, headers, workspace, content, categories="", region="GB", *, scan=True):
    result = owner.post(
        "/api/v1/documents/from-file",
        data={"workspace_id": str(workspace), "categories": categories, "phone_region": region},
        files={"file": ("fictional.docx", content)},
        headers=headers,
    )
    assert result.status_code == 201, result.text
    assert result.json()["structure"] == "kept"
    base = "/api/v1/documents/" + result.json()["version"]["document_id"]
    source = owner.get(base + "/source").json()
    version = result.json()["version"]
    if scan:
        result = owner.post(base + "/scan", json={"expected": version}, headers=headers)
        assert result.status_code == 200, result.text
    return base, owner.get(base + "/findings").json(), source


def mark(owner, headers, base, state, source, value, category, start=None):
    position = source.index(value) if start is None else start
    for finding in state["findings"]:
        if finding["span"] == {"start": position, "end": position + len(value)}:
            assert finding["category"] == category
            return state
    result = owner.post(
        base + "/findings",
        json={
            "expected": state["version"],
            "span": {"start": position, "end": position + len(value)},
            "category": category,
        },
        headers=headers,
    )
    assert result.status_code == 200, result.text
    return result.json()


def confirm(owner, headers, base, state):
    result = owner.post(
        base + "/complete",
        json={"expected": state["version"], "confirmed_preview": True},
        headers=headers,
    )
    assert result.status_code == 200, result.text


def output(owner, headers, base, state, format="docx", event=None):
    return owner.post(
        base + "/exports/" + format,
        json={"expected": state["version"], "event_id": str(event or uuid4())},
        headers=headers,
    )
