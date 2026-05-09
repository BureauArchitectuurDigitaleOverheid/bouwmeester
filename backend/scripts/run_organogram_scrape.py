"""CLI runner voor de organogram-scrape."""

from __future__ import annotations

import asyncio
import logging

from bouwmeester.core.database import async_session
from bouwmeester.services.organogram_scrape import sync_organogram


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    async with async_session() as session:
        stats = await sync_organogram(session)
    print(
        f"Organogram-scrape: dgs_added={stats.dgs_added} "
        f"directies_added={stats.directies_added} "
        f"skipped={stats.skipped}"
    )


if __name__ == "__main__":
    asyncio.run(main())
