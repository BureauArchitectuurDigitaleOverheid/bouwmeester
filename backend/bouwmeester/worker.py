"""Background worker for polling TK/EK APIs, importing parliamentary items,
and polling Mattermost for link codes."""

import asyncio
import logging

from bouwmeester.core.config import get_settings
from bouwmeester.core.database import async_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_MATTERMOST_POLL_INTERVAL_SECONDS = 5


async def _parlementair_loop(settings) -> None:  # type: ignore[no-untyped-def]
    """Poll TK/EK APIs for parliamentary items."""
    while True:
        try:
            async with async_session() as session:
                from bouwmeester.services.parlementair_import_service import (
                    ParlementairImportService,
                )

                service = ParlementairImportService(session)
                count = await service.poll_and_import()
                logger.info(f"Import cycle complete: {count} items imported")
        except Exception:
            logger.exception("Error in parlementair import cycle")

        await asyncio.sleep(settings.TK_POLL_INTERVAL_SECONDS)


async def _mattermost_link_loop() -> None:
    """Poll Mattermost bot DMs for link codes.

    Checks DB config each iteration so the poller starts automatically
    when MATTERMOST_ENABLED is toggled to true in Beheer > Instellingen.
    """
    import time

    started = False
    last_poll_ms: int = int(time.time() * 1000)
    seen_post_ids: set[str] = set()

    while True:
        try:
            async with async_session() as session:
                from bouwmeester.services.mattermost_service import (
                    MattermostService,
                )

                mm = MattermostService(session)
                if not await mm.is_enabled():
                    if started:
                        logger.info("Mattermost integration disabled, pausing poller")
                        started = False
                    await asyncio.sleep(_MATTERMOST_POLL_INTERVAL_SECONDS)
                    continue

                if not started:
                    logger.info("Mattermost link poller started")
                    started = True

                since = last_poll_ms
                last_poll_ms = int(time.time() * 1000)

                posts = await mm.get_bot_dm_posts(since=since)
                # Filter out posts we've already processed (Mattermost's
                # `since` API also returns posts whose threads were updated).
                new_posts = [
                    p for p in posts if p.get("id") not in seen_post_ids
                ]
                for p in new_posts:
                    seen_post_ids.add(p.get("id", ""))

                if new_posts:
                    from bouwmeester.services.mattermost_link_poller import (
                        MattermostLinkPoller,
                    )

                    poller = MattermostLinkPoller(session)
                    count = await poller.process_posts(new_posts)
                    if count:
                        logger.info(
                            f"Mattermost link poll: {count} accounts linked"
                        )
                    await poller.cleanup()

                # Cap the set size to prevent unbounded growth.
                if len(seen_post_ids) > 1000:
                    seen_post_ids = set(list(seen_post_ids)[-500:])

                await session.commit()
        except Exception:
            logger.exception("Error in Mattermost link poll cycle")

        await asyncio.sleep(_MATTERMOST_POLL_INTERVAL_SECONDS)


async def main() -> None:
    settings = get_settings()
    logger.info(
        f"Worker started. Parlementair poll interval: "
        f"{settings.TK_POLL_INTERVAL_SECONDS}s"
    )

    tasks = [
        asyncio.create_task(_parlementair_loop(settings)),
        asyncio.create_task(_mattermost_link_loop()),
    ]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
