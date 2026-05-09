"""Admin endpoints om de externe-data syncs handmatig te triggeren.

Vereist `org:manage` permission. In normale werking draaien deze syncs via
de worker op een cron-schedule; deze endpoints zijn voor 'sync nu'-acties
en debugging.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import require_permission
from bouwmeester.services.kabinet_scrape import schrijf_kabinet_yaml
from bouwmeester.services.kabinet_sync import sync_kabinet
from bouwmeester.services.ministeries_csv_sync import sync_ministeries_csv
from bouwmeester.services.organogram_scrape import sync_organogram
from bouwmeester.services.rio_sync import sync_rio
from bouwmeester.services.tk_persoon_sync import sync_tk_personen
from bouwmeester.services.tooi_sync import sync_tooi

router = APIRouter(prefix="/api/admin/sync", tags=["admin-sync"])

# Pad naar kabinet.yaml — relatief vanaf backend-root
from pathlib import Path  # noqa: E402

KABINET_YAML = Path(__file__).resolve().parent.parent.parent / "data" / "kabinet.yaml"


@router.post("/tooi", summary="Trigger TOOI-waardelijsten sync")
async def trigger_tooi(
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("org:manage")),
) -> dict:
    stats = await sync_tooi(db)
    return {
        "sync_run_id": str(stats.sync_run_id),
        "added": stats.added,
        "renamed": stats.renamed,
        "moved": stats.moved,
        "soft_deleted": stats.soft_deleted,
        "conflicts": stats.conflicts,
        "skipped_sanity": stats.skipped_sanity,
    }


@router.post("/ministeries-csv", summary="Trigger Ministeries.csv verrijking")
async def trigger_ministeries_csv(
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("org:manage")),
) -> dict:
    stats = await sync_ministeries_csv(db)
    return {
        "sync_run_id": str(stats.sync_run_id),
        "enriched": stats.enriched,
        "no_tooi_match": stats.no_tooi_match,
    }


@router.post("/rio", summary="Trigger RIO email-domeinen sync")
async def trigger_rio(
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("org:manage")),
) -> dict:
    stats = await sync_rio(db)
    return {
        "sync_run_id": str(stats.sync_run_id),
        "domeinen_added": stats.domeinen_added,
        "domeinen_skipped": stats.domeinen_skipped_no_match,
        "orgs_zonder_match": len(stats.organisaties_zonder_match),
    }


@router.post("/organogram", summary="Trigger DG/directie-scrape per ministerie")
async def trigger_organogram(
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("org:manage")),
) -> dict:
    stats = await sync_organogram(db)
    return {
        "sync_run_id": str(stats.sync_run_id),
        "dgs_added": stats.dgs_added,
        "directies_added": stats.directies_added,
        "skipped": stats.skipped,
    }


@router.post("/tk-personen", summary="Trigger Tweede Kamer personen sync")
async def trigger_tk_personen(
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("org:manage")),
) -> dict:
    stats = await sync_tk_personen(db)
    return {
        "sync_run_id": str(stats.sync_run_id),
        "nieuwe_personen": stats.nieuwe_personen,
        "nieuwe_plaatsingen": stats.nieuwe_plaatsingen,
        "geupdate_plaatsingen": stats.geupdate_plaatsingen,
        "onveranderd": stats.onveranderd,
    }


@router.post(
    "/kabinet",
    summary="Scrape rijksoverheid.nl en synchroniseer kabinet.yaml",
)
async def trigger_kabinet(
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("org:manage")),
) -> dict:
    aantal = await schrijf_kabinet_yaml(db, str(KABINET_YAML))
    stats = await sync_kabinet(db, KABINET_YAML)
    return {
        "scrape_aantal": aantal,
        "sync_run_id": str(stats.sync_run_id),
        "nieuwe_personen": stats.nieuwe_personen,
        "nieuwe_plaatsingen": stats.nieuwe_plaatsingen,
        "verlopen_plaatsingen": stats.verlopen_plaatsingen,
        "onveranderd": stats.onveranderd,
        "fouten": stats.fouten,
    }


@router.post(
    "/all",
    summary="Trigger alle syncs (TOOI -> CSV -> RIO -> Organogram -> TK -> Kabinet)",
)
async def trigger_all(
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("org:manage")),
) -> dict:
    """Volledige sync-cyclus. Volgorde is belangrijk: TOOI eerst (anders geen
    TOOI-URI's om CSV/RIO tegen te matchen), kabinet pas na TOOI omdat hij
    ministerie-rijen nodig heeft."""
    results = {}
    s1 = await sync_tooi(db)
    results["tooi"] = {"added": s1.added, "renamed": s1.renamed}
    s2 = await sync_ministeries_csv(db)
    results["ministeries_csv"] = {"enriched": s2.enriched}
    s3 = await sync_rio(db)
    results["rio"] = {"domeinen_added": s3.domeinen_added}
    s4 = await sync_organogram(db)
    results["organogram"] = {"dgs": s4.dgs_added, "directies": s4.directies_added}
    s5 = await sync_tk_personen(db)
    results["tk"] = {
        "nieuwe_personen": s5.nieuwe_personen,
        "nieuwe_plaatsingen": s5.nieuwe_plaatsingen,
    }
    aantal = await schrijf_kabinet_yaml(db, str(KABINET_YAML))
    s6 = await sync_kabinet(db, KABINET_YAML)
    results["kabinet"] = {
        "scrape_aantal": aantal,
        "nieuwe_plaatsingen": s6.nieuwe_plaatsingen,
        "verlopen": s6.verlopen_plaatsingen,
    }
    return results
