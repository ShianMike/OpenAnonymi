"""Validate environment settings without opening a database connection."""

from app.config import ConfigurationError, load_settings


def main() -> None:
    try:
        load_settings()
    except ConfigurationError as exc:
        raise SystemExit(str(exc)) from None
    print("Configuration valid.")


if __name__ == "__main__":
    main()
