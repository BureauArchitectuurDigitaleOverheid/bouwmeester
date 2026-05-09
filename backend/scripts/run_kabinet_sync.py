"""CLI runner voor kabinet.yaml -> DB sync."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from bouwmeester.core.database import async_session
from bouwmeester.services.kabinet_sync import sync_kabinet

YAML = Path(__file__).resolve().parent.parent / "bouwmeester" / "data" / "kabinet.yaml"


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    async with async_session() as session:
        stats = await sync_kabinet(session, YAML)
    print(
        f"Kabinet sync: nieuwe_personen={stats.nieuwe_personen} "
        f"nieuwe_plaatsingen={stats.nieuwe_plaatsingen} "
        f"verlopen={stats.verlopen_plaatsingen} "
        f"onveranderd={stats.onveranderd} fouten={len(stats.fouten)}"
    )
    for f in stats.fouten:
        print(f"  fout: {f}")


if __name__ == "__main__":
    asyncio.run(main())
