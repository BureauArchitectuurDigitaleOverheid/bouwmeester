"""Background worker for polling TK/EK APIs, importing parliamentary items,
and running the persistent Mattermost websocket."""

import asyncio
import logging
import traceback

from bouwmeester.core.config import get_settings
from bouwmeester.core.database import async_session
from bouwmeester.services.worker_health import tick as health_tick

# Note on stdout buffering: PYTHONUNBUFFERED=1 lives in the Dockerfile and
# entrypoint.sh runs us with `python -u`. Setting it from inside Python is
# pointless (the runtime reads the env var at startup, before this module
# runs).

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _short_error(exc: BaseException) -> str:
    """One-line summary of an exception for the heartbeat detail field."""
    tb = traceback.format_exception_only(type(exc), exc)
    return "".join(tb).strip()[:500]


async def _parlementair_loop(settings) -> None:  # type: ignore[no-untyped-def]
    """Poll TK/EK APIs for parliamentary items."""
    await health_tick("parlementair", status="starting")
    while True:
        try:
            async with async_session() as session:
                from bouwmeester.services.parlementair_import_service import (
                    ParlementairImportService,
                )

                service = ParlementairImportService(session)
                count = await service.poll_and_import()
                logger.info(f"Import cycle complete: {count} items imported")
            await health_tick("parlementair", detail=f"{count} items imported")
        except Exception as exc:
            logger.exception("Error in parlementair import cycle")
            await health_tick("parlementair", status="error", detail=_short_error(exc))

        await asyncio.sleep(settings.TK_POLL_INTERVAL_SECONDS)


async def _opdracht_task_loop(settings) -> None:  # type: ignore[no-untyped-def]
    """Daily check for deadline-approaching and budget-preparation tasks."""
    await health_tick("opdracht_task", status="starting")
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
            await health_tick(
                "opdracht_task",
                detail=f"{deadline_count} deadline, {budget_count} budget",
            )
        except Exception as exc:
            logger.exception("Error in opdracht task cycle")
            await health_tick("opdracht_task", status="error", detail=_short_error(exc))

        await asyncio.sleep(settings.OPDRACHT_TASK_INTERVAL_SECONDS)


async def _fcc_sync_loop(settings) -> None:  # type: ignore[no-untyped-def]
    """Bidirectional sync with Fortes Change Cloud."""
    await health_tick("fcc_sync", status="starting")
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
                    await health_tick(
                        "fcc_sync",
                        status="disabled",
                        detail="FCC_SYNC_ENABLED is false",
                    )
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
            await health_tick(
                "fcc_sync",
                detail=f"{pull_count} pulled, {push_count} pushed",
            )
        except Exception as exc:
            logger.exception("Error in FCC sync cycle")
            await health_tick("fcc_sync", status="error", detail=_short_error(exc))

        await asyncio.sleep(settings.FCC_POLL_INTERVAL_SECONDS)


async def _mattermost_websocket_loop(settings) -> None:  # type: ignore[no-untyped-def]
    """Persistent Mattermost websocket voor het meelezen in gekoppelde kanalen.

    Service heeft eigen reconnect/backoff binnen ``run()``. Deze loop vangt
    alleen onverwachte exceptions op en herstart dan na een korte pauze.
    """
    await health_tick("mattermost_websocket", status="starting")
    while True:
        try:
            from bouwmeester.services.mattermost_websocket_service import (
                MattermostWebsocketService,
            )

            service = MattermostWebsocketService()
            await service.run()
            # run() only returns when stop() is called from the outside.
            await health_tick("mattermost_websocket", status="stopped")
        except Exception as exc:
            logger.exception("Mattermost websocket loop crashed, restart in 5s")
            await health_tick(
                "mattermost_websocket", status="error", detail=_short_error(exc)
            )
        await asyncio.sleep(5)


async def main() -> None:
    settings = get_settings()
    logger.info(
        f"Worker started. Parlementair poll interval: "
        f"{settings.TK_POLL_INTERVAL_SECONDS}s"
    )

    tasks = [
        asyncio.create_task(_parlementair_loop(settings)),
        asyncio.create_task(_mattermost_websocket_loop(settings)),
        asyncio.create_task(_opdracht_task_loop(settings)),
        asyncio.create_task(_fcc_sync_loop(settings)),
    ]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
