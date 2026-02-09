"""Background worker for polling TK/EK APIs and importing parliamentary items."""

import asyncio
import logging

from bouwmeester.core.config import get_settings
from bouwmeester.core.database import async_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    logger.info(
        f"Parlementair import worker started. Poll interval: "
        f"{settings.TK_POLL_INTERVAL_SECONDS}s"
    )

    while True:
        try:
            async with async_session() as session:
                from bouwmeester.services.parlementair_import_service import (
                    ParlementairImportService,
                )

                service = ParlementairImportService(session)
                count = await service.poll_and_import()
                await session.commit()
                logger.info(f"Import cycle complete: {count} items imported")
        except Exception:
            logger.exception("Error in parlementair import cycle")

        await asyncio.sleep(settings.TK_POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
