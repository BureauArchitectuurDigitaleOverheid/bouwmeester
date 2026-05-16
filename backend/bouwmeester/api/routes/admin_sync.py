"""Admin endpoints om de externe-data syncs handmatig te triggeren.

Vereist `org:manage` permission. In normale werking draaien deze syncs via
de worker op een cron-schedule; deze endpoints zijn voor 'sync nu'-acties
en debugging.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import require_permission
from bouwmeester.services.detect_orphan_handmatig import (
    detect_orphan_handmatig_matches,
)
from bouwmeester.services.kabinet_scrape import write_kabinet_yaml
from bouwmeester.services.kabinet_sync import sync_kabinet
from bouwmeester.services.ministeries_csv_sync import sync_ministeries_csv
from bouwmeester.services.organogram_scrape import sync_organogram
from bouwmeester.services.rio_sync import sync_rio
from bouwmeester.services.tk_persoon_sync import sync_tk_personen
from bouwmeester.services.tooi_sync import sync_tooi

router = APIRouter(prefix="/admin/sync", tags=["admin-sync"])

from bouwmeester.core.storage import kabinet_yaml_path  # noqa: E402


@router.get(
    "/log",
    summary="Recente sync-log entries (drilldown van sync-status)",
)
async def sync_log(
    bron: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("org:manage")),
) -> list[dict]:
    """Levert tot `limit` recente TooiSyncLog-rijen, optioneel per bron.

    Gebruikt voor drilldown op de sync-status pagina: 'wat ging er fout
    bij de laatste sync', 'welke organisaties zijn toegevoegd', etc.
    """
    from bouwmeester.models.tooi_sync_log import TooiSyncLog

    stmt = select(TooiSyncLog).order_by(TooiSyncLog.created_at.desc()).limit(limit)
    if bron:
        stmt = stmt.where(TooiSyncLog.bron == bron)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(r.id),
            "sync_run_id": str(r.sync_run_id),
            "bron": r.bron,
            "action": r.action,
            "tooi_uri": r.tooi_uri,
            "organisatie_eenheid_id": (
                str(r.organisatie_eenheid_id) if r.organisatie_eenheid_id else None
            ),
            "person_id": str(r.person_id) if r.person_id else None,
            "before": r.before,
            "after": r.after,
            "note": r.note,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get(
    "/status",
    summary="Status: laatste sync-run per bron met counts",
)
async def sync_status(
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("org:manage")),
) -> dict:
    """Geef laatste sync-run per bron + bron-tellingen.

    Resultaat: { 'tooi': {laatste_run, ...}, 'rio': {...}, ... } plus
    organisatie-eenheid-tellingen per bron en open reconciliations.
    """
    from sqlalchemy import func

    from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
    from bouwmeester.models.pending_reconciliation import PendingReconciliation
    from bouwmeester.models.tooi_sync_log import TooiSyncLog

    # Laatste run per bron
    sub = (
        select(
            TooiSyncLog.bron,
            func.max(TooiSyncLog.created_at).label("laatste"),
        )
        .group_by(TooiSyncLog.bron)
        .subquery()
    )
    rows = (await db.execute(select(sub))).all()
    laatste_run_per_bron = {r.bron: r.laatste.isoformat() for r in rows}

    # Tellingen per bron
    cnt_rows = (
        await db.execute(
            select(OrganisatieEenheid.bron, func.count())
            .where(OrganisatieEenheid.geldig_tot.is_(None))
            .group_by(OrganisatieEenheid.bron)
        )
    ).all()
    actief_per_bron = {b: c for b, c in cnt_rows}

    # Open reconciliations
    open_rec = (
        await db.execute(
            select(func.count(PendingReconciliation.id)).where(
                PendingReconciliation.status == "open"
            )
        )
    ).scalar_one()

    return {
        "laatste_run_per_bron": laatste_run_per_bron,
        "actief_per_bron": actief_per_bron,
        "open_reconciliations": open_rec,
    }


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


@router.post(
    "/orphan-handmatig",
    summary="Detecteer handmatige rijen die alsnog matchen op een TOOI-rij",
)
async def trigger_orphan_handmatig_scan(
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("org:manage")),
) -> dict:
    """Vind handmatige rijen (FCC-import zonder YAML-entry) die op afkorting
    of genormaliseerde naam matchen met een TOOI-rij. Genereert
    PendingReconciliation-rijen voor elke kandidaat zodat de admin ze
    via Beheer > Reconciliatie kan mergen.
    """
    stats = await detect_orphan_handmatig_matches(db)
    return {
        "scanned": stats.scanned,
        "found_match": stats.found_match,
        "new_reconciliations": stats.new_reconciliations,
        "already_pending": stats.already_pending,
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


@router.post(
    "/onderwijsinstellingen",
    summary="Importeer onderwijsinstellingen-YAML (universiteiten + hogescholen)",
)
async def trigger_onderwijsinstellingen(
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("org:manage")),
) -> dict:
    from pathlib import Path

    from bouwmeester.services.onderwijsinstellingen_sync import (
        sync_onderwijsinstellingen,
    )

    yaml_path = (
        Path(__file__).resolve().parent.parent.parent
        / "data"
        / "onderwijsinstellingen.yaml"
    )
    stats = await sync_onderwijsinstellingen(db, yaml_path)
    return {
        "sync_run_id": str(stats.sync_run_id),
        "nieuwe_universiteiten": stats.nieuwe_universiteiten,
        "nieuwe_hogescholen": stats.nieuwe_hogescholen,
        "onveranderd": stats.onveranderd,
    }


@router.post(
    "/wikidata-qid",
    summary="Vul Person.wikidata_qid via Wikidata SPARQL",
)
async def trigger_wikidata_qid(
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("org:manage")),
) -> dict:
    from bouwmeester.services.wikidata_qid_sync import sync_wikidata_qid

    stats = await sync_wikidata_qid(db)
    return {
        "sync_run_id": str(stats.sync_run_id),
        "matches": stats.matches,
        "geen_match": stats.geen_match,
        "api_fouten": stats.api_fouten,
    }


@router.post(
    "/historische-kabinetten",
    summary="Importeer historische-kabinetten YAML",
)
async def trigger_historische_kabinetten(
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("org:manage")),
) -> dict:
    from pathlib import Path

    from bouwmeester.services.historische_kabinetten_sync import (
        sync_historische_kabinetten,
    )

    yaml_path = (
        Path(__file__).resolve().parent.parent.parent
        / "data"
        / "kabinetten_historisch.yaml"
    )
    stats = await sync_historische_kabinetten(db, yaml_path)
    return {
        "sync_run_id": str(stats.sync_run_id),
        "nieuwe_personen": stats.nieuwe_personen,
        "new_placements": stats.new_placements,
        "onveranderd": stats.onveranderd,
        "fouten": stats.fouten,
    }


@router.post(
    "/abd",
    summary="Trigger ABD-benoemingen scrape (Playwright)",
)
async def trigger_abd(
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("org:manage")),
) -> dict:
    from bouwmeester.services.abd_scrape import sync_abd

    stats = await sync_abd(db)
    return {
        "sync_run_id": str(stats.sync_run_id),
        "nieuwe_personen": stats.nieuwe_personen,
        "new_placements": stats.new_placements,
        "onveranderd": stats.onveranderd,
        "geen_org_match": stats.geen_org_match,
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
        "new_placements": stats.new_placements,
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
    kab_yaml = kabinet_yaml_path()
    aantal = await write_kabinet_yaml(db, str(kab_yaml))
    stats = await sync_kabinet(db, kab_yaml)
    return {
        "scrape_aantal": aantal,
        "sync_run_id": str(stats.sync_run_id),
        "nieuwe_personen": stats.nieuwe_personen,
        "new_placements": stats.new_placements,
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
        "new_placements": s5.new_placements,
    }
    kab_yaml = kabinet_yaml_path()
    aantal = await write_kabinet_yaml(db, str(kab_yaml))
    s6 = await sync_kabinet(db, kab_yaml)
    results["kabinet"] = {
        "scrape_aantal": aantal,
        "new_placements": s6.new_placements,
        "verlopen": s6.verlopen_plaatsingen,
    }
    return results
