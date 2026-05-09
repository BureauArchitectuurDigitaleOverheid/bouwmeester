"""CLI runner voor TK OData -> DB sync."""

from __future__ import annotations

import asyncio
import logging

from bouwmeester.core.database import async_session
from bouwmeester.services.tk_persoon_sync import sync_tk_personen


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    async with async_session() as session:
        stats = await sync_tk_personen(session)
    print(
        f"TK OData sync: nieuwe_personen={stats.nieuwe_personen} "
        f"nieuwe_plaatsingen={stats.nieuwe_plaatsingen} "
        f"geupdate={stats.geupdate_plaatsingen} "
        f"onveranderd={stats.onveranderd} fouten={len(stats.fouten)}"
    )
    for f in stats.fouten:
        print(f"  fout: {f}")


if __name__ == "__main__":
    asyncio.run(main())
