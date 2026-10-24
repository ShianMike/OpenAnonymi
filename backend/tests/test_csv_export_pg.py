"""Historical reviews retain text access without re-enabling CSV entry points."""

from uuid import uuid4

from tests.csv_support import legacy_csv
from tests.docx_support import confirm, output
from tests.intake_support import _login


def test_legacy_csv_keeps_owned_source_and_txt_output_but_no_csv_controls(intake_site):
    owner, other, _, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    _login(other, "intake-other@example.invalid")
    source = "Name,Note\r\nNora,Fictional legacy review\r\n"
    base, state, saved = legacy_csv(owner, headers, workspace, source)
    assert saved["text"] == source and saved["file_format"] == "txt"
    assert "csv" not in saved
    assert other.get(base + "/source").status_code == 404
    confirm(owner, headers, base, state)
    exported = output(owner, headers, base, state, "txt")
    assert exported.status_code == 200 and exported.content == source.encode()
    for method, suffix in [("get", "/csv-settings"), ("put", "/csv-settings"),
                           ("get", "/column-rules"), ("put", "/column-rules"),
                           ("post", "/columns/0/decision"), ("post", "/exports/csv")]:
        response = getattr(owner, method)(base + suffix, headers=headers,
                                         **({"json": {"event_id": str(uuid4())}} if method != "get" else {}))
        assert response.status_code == 404
        assert "Fictional legacy review" not in response.text
