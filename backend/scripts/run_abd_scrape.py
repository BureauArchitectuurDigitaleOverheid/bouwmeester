"""CLI runner voor ABD-benoemingen-scrape via Playwright."""

from __future__ import annotations

import asyncio
import logging

from bouwmeester.core.database import async_session
from bouwmeester.services.abd_scrape import sync_abd


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    async with async_session() as session:
        stats = await sync_abd(session)
    print(
        f"ABD-scrape: nieuwe_personen={stats.nieuwe_personen} "
        f"nieuwe_plaatsingen={stats.nieuwe_plaatsingen} "
        f"onveranderd={stats.onveranderd} "
        f"geen_org_match={stats.geen_org_match}"
    )
    for f in stats.fouten[:10]:
        print(f"  fout: {f}")
    if len(stats.fouten) > 10:
        print(f"  ... en {len(stats.fouten) - 10} meer")


if __name__ == "__main__":
    asyncio.run(main())
