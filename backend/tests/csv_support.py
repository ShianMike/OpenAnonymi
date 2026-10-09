"""Real authenticated CSV upload and settings helpers for owned test databases."""


def upload_csv(
    owner,
    headers,
    workspace,
    source,
    categories="",
    *,
    delimiter="auto",
    header="auto",
    scan=True,
    preset=None,
):
    data = {
        "workspace_id": str(workspace),
        "categories": categories,
        "phone_region": "GB",
        "csv_delimiter": delimiter,
        "csv_header": header,
    }
    if preset:
        data["preset_id"] = str(preset)
    result = owner.post(
        "/api/v1/documents/from-file",
        data=data,
        files={"file": ("fictional.csv", source.encode("utf-8"), "text/csv")},
        headers=headers,
    )
    assert result.status_code == 201, result.text
    base = "/api/v1/documents/" + result.json()["version"]["document_id"]
    version = result.json()["version"]
    if scan:
        result = owner.post(base + "/scan", json={"expected": version}, headers=headers)
        assert result.status_code == 200, result.text
    return base, owner.get(base + "/findings").json(), owner.get(base + "/source").json()


def set_rules(owner, headers, base, rules):
    settings = owner.get(base + "/csv-settings").json()
    return owner.put(
        base + "/column-rules",
        json={"expected_settings_version": settings["version"]["settings_version"], "rules": rules},
        headers=headers,
    )
