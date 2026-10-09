"""Periodic cleanup plus a one-shot operator command."""

import asyncio
import logging

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.config import load_settings
from app.maintenance.service import run_cleanup

LOGGER = logging.getLogger(__name__)
INTERVAL_SECONDS = 3600


async def periodic_cleanup(engine: Engine) -> None:
    first = True
    while True:
        try:
            result = await asyncio.to_thread(
                run_cleanup, engine, trigger="startup" if first else "periodic"
            )
            LOGGER.info(
                "Content cleanup complete: %d documents, %d activity rows.",
                result.documents_purged,
                result.activity_removed,
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 -- background loop retries with fixed, content-free logging
            LOGGER.warning("Content cleanup failed; it will be retried.")
        first = False
        await asyncio.sleep(INTERVAL_SECONDS)


def main() -> None:
    settings = load_settings()
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"connect_timeout": settings.database_connect_timeout},
    )
    try:
        result = run_cleanup(engine, trigger="cli")
    finally:
        engine.dispose()
    print(
        f"Cleanup complete: {result.documents_purged} document(s), {result.activity_removed} activity row(s), "
        f"{result.expired_rows_removed} expired row(s). More remaining: {str(result.more_remaining).lower()}."
    )


if __name__ == "__main__":
    main()
