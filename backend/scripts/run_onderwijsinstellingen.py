"""CLI runner voor onderwijsinstellingen YAML-sync."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from bouwmeester.core.database import async_session
from bouwmeester.services.onderwijsinstellingen_sync import (
    sync_onderwijsinstellingen,
)

YAML = (
    Path(__file__).resolve().parent.parent
    / "bouwmeester"
    / "data"
    / "onderwijsinstellingen.yaml"
)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    async with async_session() as session:
        stats = await sync_onderwijsinstellingen(session, YAML)
    print(
        f"Onderwijs: +{stats.nieuwe_universiteiten} universiteiten, "
        f"+{stats.nieuwe_hogescholen} hogescholen, {stats.onveranderd} onveranderd, "
        f"{len(stats.fouten)} fouten"
    )


if __name__ == "__main__":
    asyncio.run(main())
