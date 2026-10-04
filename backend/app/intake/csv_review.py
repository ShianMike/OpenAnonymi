"""The canonical replacement strings applied to logical, unescaped CSV cells."""

from app.intake.csv_structure import CsvError, cell_value, value_span


def logical_finding_values(source: str, layout: dict, spans) -> dict:
    ordered = sorted(spans, key=lambda item: (item[1], item[2]))
    index, result = 0, {}
    for row in layout["records"]:
        for cell in row:
            while index < len(ordered) and ordered[index][1] < cell["end"]:
                finding_id, start, end = ordered[index]
                if not cell["start"] <= start < end <= cell["end"]:
                    raise CsvError(
                        "finding_crosses_block", "A finding must stay inside one CSV cell."
                    )
                value_span(source, cell, start, end)
                raw = source[start:end]
                result[finding_id] = raw.replace('""', '"') if cell["quoted"] else raw
                index += 1
    if index != len(ordered):
        raise CsvError("finding_crosses_block", "A finding must stay inside one CSV cell.")
    return result


def reviewed_cells(
    source: str, layout: dict, preview: str, mappings
) -> tuple[tuple[str, ...], ...]:
    """Use exact canonical mappings; replacement quotes are never unescaped again."""
    ordered = sorted(mappings, key=lambda item: (item.source_span.start, item.source_span.end))
    index, records = 0, []
    for row in layout["records"]:
        cells = []
        for cell in row:
            cursor, pieces = cell["start"], []
            while index < len(ordered) and ordered[index].source_span.start < cell["end"]:
                mapping = ordered[index]
                start, end = mapping.source_span.start, mapping.source_span.end
                if not cursor <= start < end <= cell["end"]:
                    raise CsvError(
                        "finding_crosses_block", "A finding must stay inside one CSV cell."
                    )
                value_span(source, cell, start, end)
                raw = source[cursor:start]
                pieces.append(raw.replace('""', '"') if cell["quoted"] else raw)
                if mapping.action in ("label", "redact"):
                    pieces.append(preview[mapping.preview_span.start : mapping.preview_span.end])
                else:
                    raw = source[start:end]
                    pieces.append(raw.replace('""', '"') if cell["quoted"] else raw)
                cursor = end
                index += 1
            raw = source[cursor : cell["end"]]
            pieces.append(raw.replace('""', '"') if cell["quoted"] else raw)
            cells.append("".join(pieces))
        records.append(tuple(cells))
    if index != len(ordered):
        raise CsvError("finding_crosses_block", "A finding must stay inside one CSV cell.")
    return tuple(records)


def logical_source(source: str, layout: dict) -> str:
    return "\n".join(cell_value(source, cell) for row in layout["records"] for cell in row)
