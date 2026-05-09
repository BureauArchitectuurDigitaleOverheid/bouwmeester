"""CLI runner voor Wikidata QID auto-vulling op Person."""

from __future__ import annotations

import asyncio
import logging

from bouwmeester.core.database import async_session
from bouwmeester.services.wikidata_qid_sync import sync_wikidata_qid


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    async with async_session() as session:
        stats = await sync_wikidata_qid(session)
    print(
        f"Wikidata QID: {stats.matches} matches, {stats.geen_match} zonder match, "
        f"{len(stats.api_fouten)} api-fouten"
    )
    for f in stats.api_fouten[:3]:
        print(f"  fout: {f}")


if __name__ == "__main__":
    asyncio.run(main())
