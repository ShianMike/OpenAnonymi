"""CSV-only settings are not part of the public API or preset contract."""

from app.config import Settings
from app.factory import create_app


def test_schema_has_no_csv_routes_or_column_configuration():
    schema = create_app(Settings(database_url="postgresql+psycopg://schema:schema@localhost/schema",
                                 allowed_origins=["http://localhost:5173"], environment="test",
                                 _env_file=None)).openapi()
    assert not any("csv" in path or "column-rules" in path or "/columns/" in path
                   for path in schema["paths"])
    models = schema["components"]["schemas"]
    assert not any(name.startswith("Csv") or name in {"ColumnRule", "ColumnDecisionRequest"}
                   for name in models)
    assert "column_rules" not in models["PresetInput"]["properties"]
    assert "column_rules" not in models["PresetView"]["properties"]
    assert "csv" not in models["SourceView"]["properties"]
    for name in models:
        if name.startswith("Body_"):
            assert not any(field.startswith("csv_") for field in models[name]["properties"])
