"""CLI runner voor historische-kabinetten YAML sync."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from bouwmeester.core.database import async_session
from bouwmeester.services.historische_kabinetten_sync import (
    sync_historische_kabinetten,
)

YAML = (
    Path(__file__).resolve().parent.parent
    / "bouwmeester"
    / "data"
    / "kabinetten_historisch.yaml"
)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    async with async_session() as session:
        stats = await sync_historische_kabinetten(session, YAML)
    print(
        f"Historische kabinetten: nieuwe_personen={stats.nieuwe_personen} "
        f"nieuwe_plaatsingen={stats.nieuwe_plaatsingen} "
        f"onveranderd={stats.onveranderd} fouten={len(stats.fouten)}"
    )
    for f in stats.fouten[:5]:
        print(f"  fout: {f}")


if __name__ == "__main__":
    asyncio.run(main())
