"""CLI om TOOI-sync handmatig te draaien."""

from __future__ import annotations

import asyncio
import logging

from bouwmeester.core.database import async_session
from bouwmeester.services.tooi_sync import sync_tooi


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    async with async_session() as session:
        stats = await sync_tooi(session)
    print(
        f"TOOI sync klaar: run={stats.sync_run_id} "
        f"added={stats.added} renamed={stats.renamed} moved={stats.moved} "
        f"soft_deleted={stats.soft_deleted} conflicts={stats.conflicts} "
        f"sanity_skip={stats.skipped_sanity}"
    )


if __name__ == "__main__":
    asyncio.run(main())
