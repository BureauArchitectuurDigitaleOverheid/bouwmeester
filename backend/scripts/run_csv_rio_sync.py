"""Runner voor Ministeries CSV + RIO sync."""

from __future__ import annotations

import asyncio
import logging

from bouwmeester.core.database import async_session
from bouwmeester.services.ministeries_csv_sync import sync_ministeries_csv
from bouwmeester.services.rio_sync import sync_rio


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    async with async_session() as session:
        s1 = await sync_ministeries_csv(session)
        print(f"Ministeries CSV: enriched={s1.enriched} no_match={s1.no_tooi_match}")

    async with async_session() as session:
        s2 = await sync_rio(session)
        print(
            f"RIO: domeinen_added={s2.domeinen_added} "
            f"skipped={s2.domeinen_skipped_no_match} "
            f"orgs_zonder_match={len(s2.organisaties_zonder_match)}"
        )


if __name__ == "__main__":
    asyncio.run(main())
