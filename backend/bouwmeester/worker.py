"""Background worker for polling TK/EK APIs, importing parliamentary items,
and polling Mattermost for link codes."""

import asyncio
import logging
import time
from collections import OrderedDict

from bouwmeester.core.config import get_settings
from bouwmeester.core.database import async_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


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


async def _mattermost_link_loop(settings) -> None:  # type: ignore[no-untyped-def]
    """Poll Mattermost bot DMs for link codes.

    Checks DB config each iteration so the poller starts automatically
    when MATTERMOST_ENABLED is toggled to true in Beheer > Instellingen.
    """
    started = False
    last_poll_ms: int = int(time.time() * 1000)
    # OrderedDict preserves insertion order for correct eviction.
    seen_post_ids: OrderedDict[str, None] = OrderedDict()

    while True:
        mm = None
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
                    await asyncio.sleep(settings.MATTERMOST_POLL_INTERVAL_SECONDS)
                    continue

                if not started:
                    logger.info("Mattermost link poller started")
                    started = True

                since = last_poll_ms
                last_poll_ms = int(time.time() * 1000)

                posts = await mm.get_bot_dm_posts(since=since)
                # Filter out posts we've already processed (Mattermost's
                # `since` API also returns posts whose threads were updated).
                new_posts = [p for p in posts if p.get("id") not in seen_post_ids]
                for p in new_posts:
                    seen_post_ids[p.get("id", "")] = None

                if new_posts:
                    from bouwmeester.services.mattermost_link_poller import (
                        MattermostLinkPoller,
                    )

                    poller = MattermostLinkPoller(session, mm_service=mm)
                    count = await poller.process_posts(new_posts)
                    if count:
                        logger.info(f"Mattermost link poll: {count} accounts linked")
                    await poller.cleanup()

                # Cap the dict size — evict oldest entries first.
                while len(seen_post_ids) > 1000:
                    seen_post_ids.popitem(last=False)

                await session.commit()
        except Exception:
            logger.exception("Error in Mattermost link poll cycle")
        finally:
            if mm:
                await mm.close()

        await asyncio.sleep(settings.MATTERMOST_POLL_INTERVAL_SECONDS)


async def _opdracht_task_loop(settings) -> None:  # type: ignore[no-untyped-def]
    """Daily check for deadline-approaching and budget-preparation tasks."""
    while True:
        try:
            async with async_session() as session:
                from bouwmeester.services.opdracht_task_service import (
                    OpdrachtTaskService,
                )

                service = OpdrachtTaskService(session)
                deadline_count = await service.check_deadlines()
                budget_count = await service.check_budget_preparation()
                await session.commit()
                logger.info(
                    f"Opdracht task cycle complete: "
                    f"{deadline_count} deadline, {budget_count} budget tasks"
                )
        except Exception:
            logger.exception("Error in opdracht task cycle")

        await asyncio.sleep(settings.OPDRACHT_TASK_INTERVAL_SECONDS)


async def _fcc_sync_loop(settings) -> None:  # type: ignore[no-untyped-def]
    """Bidirectional sync with Fortes Change Cloud."""
    while True:
        try:
            async with async_session() as session:
                from sqlalchemy import select

                from bouwmeester.core.encryption import decrypt_value
                from bouwmeester.models.app_config import AppConfig

                result = await session.execute(
                    select(AppConfig).where(AppConfig.key == "FCC_SYNC_ENABLED")
                )
                entry = result.scalar_one_or_none()
                if not entry or decrypt_value(entry.value) != "true":
                    await asyncio.sleep(settings.FCC_POLL_INTERVAL_SECONDS)
                    continue

                from bouwmeester.services.fcc_import_service import FccImportService

                import_service = FccImportService(session)
                pull_count = await import_service.poll_and_import()

                push_count = 0
                if await import_service.is_push_enabled():
                    from bouwmeester.services.fcc_export_service import (
                        FccExportService,
                    )

                    export_service = FccExportService(session)
                    push_count = await export_service.push_pending()

                await session.commit()
                logger.info(
                    "FCC sync cycle complete: %d pulled, %d pushed",
                    pull_count,
                    push_count,
                )

                # Match contacts for newly imported opdrachten
                if pull_count > 0:
                    try:
                        async with async_session() as match_session:
                            from bouwmeester.services.opdracht_matching_service import (
                                OpdrachtMatchingService,
                            )

                            svc = OpdrachtMatchingService(match_session)
                            result = await svc.match_all_unlinked()
                            await match_session.commit()
                            logger.info(
                                "Contact matching: %d matched, %d skipped",
                                result["matched"],
                                result["skipped"],
                            )
                    except Exception:
                        logger.exception("Error in contact matching after FCC sync")
        except Exception:
            logger.exception("Error in FCC sync cycle")

        await asyncio.sleep(settings.FCC_POLL_INTERVAL_SECONDS)


async def main() -> None:
    settings = get_settings()
    logger.info(
        f"Worker started. Parlementair poll interval: "
        f"{settings.TK_POLL_INTERVAL_SECONDS}s"
    )

    tasks = [
        asyncio.create_task(_parlementair_loop(settings)),
        asyncio.create_task(_mattermost_link_loop(settings)),
        asyncio.create_task(_opdracht_task_loop(settings)),
        asyncio.create_task(_fcc_sync_loop(settings)),
    ]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
