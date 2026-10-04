import csv
import io
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ExportEvent
from tests.csv_support import upload_csv
from tests.docx_support import confirm, output
from tests.intake_support import _login
from tests.styles_support import decide


def read(response, delimiter=","):
    assert response.status_code == 200, response.text
    return list(
        csv.reader(
            io.StringIO(response.content.decode("utf-8-sig"), newline=""), delimiter=delimiter
        )
    )


def test_csv_preview_txt_and_decoded_export_styles_shared_gate_and_formula_count(intake_site):
    owner, other, engine, workspace, _ = intake_site
    headers = _login(owner, "intake-owner@example.invalid")
    other_headers = _login(other, "intake-other@example.invalid")
    source = 'Name,Email,Date,Formula,Notes\r\nNora,nora@example.test,2024-02-29,=1+2,"Said ""hello""\nthere"\r\n'
    base, state, saved = upload_csv(owner, headers, workspace, source, "email,date")
    assert output(owner, headers, base, state, "csv").status_code == 409
    for finding in state["findings"]:
        result = decide(
            owner,
            headers,
            base,
            state,
            finding,
            "redact" if finding["category"] == "email" else "label",
            "partial_mask" if finding["category"] == "email" else "date_shift",
            "email_domain" if finding["category"] == "email" else None,
        )
        assert result.status_code == 200, result.text
        state = result.json()
    preview = owner.get(base + "/preview").json()
    confirm(owner, headers, base, state)
    event = uuid4()
    response = output(owner, headers, base, state, "csv", event)
    cells = read(response)
    assert cells[1][1] == "****@example.test" and cells[1][2] != "2024-02-29"
    assert cells[1][3] == "'=1+2" and cells[1][4] == 'Said "hello"\nthere'
    assert response.headers["x-csv-prefixed-cells"] == "1"
    assert response.headers["content-type"].startswith("text/csv")
    assert (
        response.headers["cache-control"] == "no-store"
        and response.headers["x-content-type-options"] == "nosniff"
    )
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="reviewed-{state["version"]["document_id"]}.csv"'
    )
    assert "x-csv-prefixed-cells" in response.headers["access-control-expose-headers"].lower()
    exact = owner.post(
        base + "/exports/csv",
        json={"expected": state["version"], "event_id": str(uuid4()), "variant": "unmodified"},
        headers=headers,
    )
    exact_cells = read(exact)
    assert exact_cells[1][3] == "=1+2" and not exact.content.startswith(b"\xef\xbb\xbf")
    assert exact.headers["x-csv-prefixed-cells"] == "0"
    assert exact_cells[1][:3] == cells[1][:3]
    assert output(owner, headers, base, state, "txt").content == preview["text"].encode("utf-8")
    assert owner.get(base + "/source").json()["text"] == saved["text"] == source
    assert output(owner, headers, base, state, "csv", event).status_code == 200
    assert (
        other.post(
            base + "/exports/csv",
            json={"expected": state["version"], "event_id": str(uuid4())},
            headers=other_headers,
        ).status_code
        == 404
    )
    assert (
        owner.post(
            base + "/exports/csv",
            json={"expected": state["version"], "event_id": str(uuid4())},
            headers={"Origin": headers["Origin"]},
        ).status_code
        == 403
    )
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count()).select_from(ExportEvent).where(ExportEvent.id == event)
            )
            == 1
        )
    edited = owner.put(
        base + "/source",
        json={"expected": state["version"], "source": source.replace("Nora", "Ada")},
        headers=headers,
    )
    assert edited.status_code == 200, edited.text
    assert output(owner, headers, base, state, "csv").status_code == 409
    assert (
        output(owner, headers, base, {"version": edited.json()["version"]}, "csv").status_code
        == 409
    )
