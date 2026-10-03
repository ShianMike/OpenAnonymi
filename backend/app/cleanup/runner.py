"""Periodic cleanup plus a one-shot operator command."""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.cleanup.service import purge_unavailable_content
from app.config import load_settings

LOGGER = logging.getLogger(__name__)
INTERVAL_SECONDS = 3600


async def periodic_cleanup(engine: Engine) -> None:
    while True:
        documents, activity = 0, 0
        try:
            while True:
                result = await asyncio.to_thread(
                    purge_unavailable_content,
                    engine,
                    now=datetime.now(UTC),
                )
                documents += result.documents_purged
                activity += result.activity_removed
                if result.documents_purged == 0:
                    break
            LOGGER.info(
                "Content cleanup complete: %d documents, %d activity rows.", documents, activity
            )
        except asyncio.CancelledError:
            raise
        except SQLAlchemyError:
            LOGGER.warning("Content cleanup failed; it will be retried.")
        await asyncio.sleep(INTERVAL_SECONDS)


def main() -> None:
    settings = load_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True, hide_parameters=True)
    documents = 0
    activity = 0
    try:
        while True:
            result = purge_unavailable_content(engine, now=datetime.now(UTC))
            documents += result.documents_purged
            activity += result.activity_removed
            if result.documents_purged == 0:
                break
    finally:
        engine.dispose()
    print(f"Cleanup complete: {documents} document(s), {activity} activity row(s).")


if __name__ == "__main__":
    main()
