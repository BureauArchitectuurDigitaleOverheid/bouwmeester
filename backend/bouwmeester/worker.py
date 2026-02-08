"""Background worker for polling TK/EK APIs and importing moties."""

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
        f"Motie import worker started. Poll interval: "
        f"{settings.TK_POLL_INTERVAL_SECONDS}s"
    )

    while True:
        try:
            async with async_session() as session:
                from bouwmeester.services.motie_import_service import (
                    MotieImportService,
                )

                service = MotieImportService(session)
                count = await service.poll_and_import()
                await session.commit()
                logger.info(f"Import cycle complete: {count} moties imported")
        except Exception:
            logger.exception("Error in motie import cycle")

        await asyncio.sleep(settings.TK_POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
