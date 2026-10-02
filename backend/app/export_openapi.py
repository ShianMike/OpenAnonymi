"""Emit the backend schema for generated frontend types without a database connection."""

import json
import sys
from pathlib import Path

from app.config import Settings
from app.factory import create_app


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m app.export_openapi OUTPUT_PATH")
    output = Path(sys.argv[1])
    settings = Settings(
        database_url="postgresql+psycopg://schema:schema@localhost/schema",
        allowed_origins=["http://localhost:5173"],
        environment="test",
        _env_file=None,
    )
    app = create_app(settings)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
