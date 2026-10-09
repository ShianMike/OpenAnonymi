"""Fresh, fully quoted CSV output with explicit spreadsheet-safe mitigation."""

import csv
import io
from dataclasses import dataclass, field

FORMULA_LEADS = frozenset("=+-@\t\r\n＝＋－＠")


@dataclass(frozen=True)
class CsvOutput:
    payload: bytes = field(repr=False)
    prefixed_cells: int


def generate_csv(records, delimiter: str, variant="spreadsheet_safe") -> CsvOutput:
    if delimiter not in (",", ";", "\t", "|") or variant not in ("spreadsheet_safe", "unmodified"):
        raise ValueError("Choose a supported CSV output variant and delimiter.")
    stream = io.StringIO(newline="")
    if variant == "spreadsheet_safe":
        stream.write("\ufeff")
    writer = csv.writer(stream, delimiter=delimiter, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    prefixed = 0
    for record in records:
        cells = []
        for value in record:
            if variant == "spreadsheet_safe" and value and value[0] in FORMULA_LEADS:
                value = "'" + value
                prefixed += 1
            cells.append(value)
        writer.writerow(cells)
    return CsvOutput(stream.getvalue().encode("utf-8"), prefixed)
