"""Scrape rijksoverheid.nl voor het huidige kabinet, schrijf naar
backend/bouwmeester/data/kabinet.yaml, en draai daarna kabinet_sync."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from bouwmeester.core.database import async_session
from bouwmeester.services.kabinet_scrape import write_kabinet_yaml
from bouwmeester.services.kabinet_sync import sync_kabinet

YAML = Path(__file__).resolve().parent.parent / "bouwmeester" / "data" / "kabinet.yaml"


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    async with async_session() as session:
        n = await write_kabinet_yaml(session, str(YAML))
    print(f"Kabinet-scrape: {n} bewindspersonen geschreven naar {YAML}")

    async with async_session() as session:
        stats = await sync_kabinet(session, YAML)
    print(
        f"Kabinet sync: nieuwe_personen={stats.nieuwe_personen} "
        f"new_placements={stats.new_placements} "
        f"verlopen={stats.verlopen_plaatsingen} "
        f"onveranderd={stats.onveranderd}"
    )
    for f in stats.fouten:
        print(f"  fout: {f}")


if __name__ == "__main__":
    asyncio.run(main())
