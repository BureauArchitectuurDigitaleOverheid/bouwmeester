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


async def _cleanup_obsolete_heartbeats() -> None:
    """Verwijder heartbeat-rijen van loops die niet meer bestaan.

    De ``mattermost_link``-rij bleef hangen toen we die loop schrapten,
    waardoor de admin-UI 'm als 'unexpected, down' bleef tonen. Run-once
    bij worker-startup is genoeg — best-effort, fout wordt gelogd.
    """
    from sqlalchemy import delete

    from bouwmeester.models.worker_heartbeat import WorkerHeartbeat

    obsolete = ["mattermost_link"]
    try:
        async with async_session() as session:
            await session.execute(
                delete(WorkerHeartbeat).where(WorkerHeartbeat.loop_name.in_(obsolete))
            )
            await session.commit()
    except Exception:
        logger.exception("Cleanup obsolete heartbeats faalde")


async def _overheidsorganisaties_dagelijks_loop(settings) -> None:  # type: ignore[no-untyped-def]
    """Dagelijkse sync van fast-changing data: TK-leden, kabinet, ABD-feeds.

    Deze data verandert vaker (kamerleden rotaties, ABD-benoemingen)
    dan TOOI/organogram. Default 24h.
    """
    interval_seconds = getattr(
        settings, "OVERHEIDSORG_DAILY_INTERVAL_SECONDS", 24 * 3600
    )
    await health_tick("overheidsorganisaties_daily", status="starting")
    while True:
        try:
            async with async_session() as session:
                from bouwmeester.services.kabinet_scrape import write_kabinet_yaml
                from bouwmeester.services.kabinet_sync import sync_kabinet
                from bouwmeester.services.tk_persoon_sync import sync_tk_personen

                tk_stats = await sync_tk_personen(session)

                from pathlib import Path

                kab_yaml = Path(__file__).resolve().parent / "data" / "kabinet.yaml"
            async with async_session() as session2:
                await write_kabinet_yaml(session2, str(kab_yaml))
                kab_stats = await sync_kabinet(session2, kab_yaml)

            # ABD-scrape via Playwright (separaat session ivm browser-lifecycle)
            abd_added = 0
            try:
                from bouwmeester.services.abd_scrape import sync_abd

                async with async_session() as session3:
                    abd_stats = await sync_abd(session3)
                    abd_added = abd_stats.new_placements
            except Exception as exc:  # noqa: BLE001
                logger.warning("ABD-scrape gefaald: %s", _short_error(exc))

            await health_tick(
                "overheidsorganisaties_daily",
                detail=(
                    f"tk+{tk_stats.new_placements} "
                    f"kab+{kab_stats.new_placements} abd+{abd_added}"
                ),
            )
        except Exception as exc:
            logger.exception("Error in daily overheidsorg sync")
            await health_tick(
                "overheidsorganisaties_daily",
                status="error",
                detail=_short_error(exc),
            )

        await asyncio.sleep(interval_seconds)


async def _overheidsorganisaties_wekelijks_loop(settings) -> None:  # type: ignore[no-untyped-def]
    """Wekelijkse sync van slow-changing data: TOOI-spine, RIO, organogram.

    TOOI/RIO/organogram-mutaties zijn zeldzaam (gemeente-fusie,
    ministerie-reshuffle). Default 7 dagen om bandwidth + parsing
    overhead te beperken. Volgorde: TOOI eerst zodat URI's bestaan
    voor CSV/RIO matching.
    """
    interval_seconds = getattr(
        settings, "OVERHEIDSORG_WEEKLY_INTERVAL_SECONDS", 7 * 24 * 3600
    )
    await health_tick("overheidsorganisaties_weekly", status="starting")
    while True:
        try:
            async with async_session() as session:
                from bouwmeester.services.ministeries_csv_sync import (
                    sync_ministeries_csv,
                )
                from bouwmeester.services.organogram_scrape import sync_organogram
                from bouwmeester.services.rio_sync import sync_rio
                from bouwmeester.services.tooi_sync import sync_tooi

                tooi_stats = await sync_tooi(session)
                csv_stats = await sync_ministeries_csv(session)
                rio_stats = await sync_rio(session)
                org_stats = await sync_organogram(session)

            await health_tick(
                "overheidsorganisaties_weekly",
                detail=(
                    f"tooi+{tooi_stats.added} csv+{csv_stats.enriched} "
                    f"rio+{rio_stats.domeinen_added} dg+{org_stats.dgs_added}"
                ),
            )
        except Exception as exc:
            logger.exception("Error in weekly overheidsorg sync")
            await health_tick(
                "overheidsorganisaties_weekly",
                status="error",
                detail=_short_error(exc),
            )

        await asyncio.sleep(interval_seconds)


async def main() -> None:
    settings = get_settings()
    logger.info(
        f"Worker started. Parlementair poll interval: "
        f"{settings.TK_POLL_INTERVAL_SECONDS}s"
    )

    await _cleanup_obsolete_heartbeats()

    tasks = [
        asyncio.create_task(_parlementair_loop(settings)),
        asyncio.create_task(_mattermost_websocket_loop(settings)),
        asyncio.create_task(_opdracht_task_loop(settings)),
        asyncio.create_task(_fcc_sync_loop(settings)),
        asyncio.create_task(_overheidsorganisaties_dagelijks_loop(settings)),
        asyncio.create_task(_overheidsorganisaties_wekelijks_loop(settings)),
    ]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
