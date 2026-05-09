"""Verrijk ministerie- en onderdeelrijen met OIN, FTE en organogram-link.

Bron: `https://organisaties.overheid.nl/export/Ministeries.csv` — semicolon-gescheiden,
kolommen onder andere: Officiele naam, Afkorting, TOOi URI, OIN, Aantal fte,
Link naar organogram. CC0, dagelijks ververst.

Match op TOOI-URI: rijen die we al via tooi_sync hebben krijgen `oin`,
`fte_aantal` en `website` (organogram-link) erbij. Geen nieuwe rijen
worden via deze sync aangemaakt — die taak is van tooi_sync of
organogram_scrape.
"""

from __future__ import annotations

import csv
import io
import logging
import uuid
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.tooi_sync_log import TooiSyncLog

log = logging.getLogger(__name__)

CSV_URL = "https://organisaties.overheid.nl/export/Ministeries.csv"


@dataclass
class CsvSyncStats:
    sync_run_id: uuid.UUID
    enriched: int = 0
    no_tooi_match: int = 0


def _parse_int(s: str) -> int | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return int(s.replace(".", "").replace(",", ""))
    except ValueError:
        return None


async def fetch_csv() -> list[dict[str, str]]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(CSV_URL)
        resp.raise_for_status()
    reader = csv.DictReader(io.StringIO(resp.text), delimiter=";")
    return list(reader)


async def sync_ministeries_csv(
    session: AsyncSession,
    *,
    fetcher=fetch_csv,
) -> CsvSyncStats:
    """Verrijk bestaande TOOI-rijen met OIN/FTE/organogram-link."""
    sync_run_id = uuid.uuid4()
    stats = CsvSyncStats(sync_run_id=sync_run_id)

    rows = await fetcher()
    if not rows:
        log.warning("Ministeries CSV leeg, sync afgebroken")
        return stats

    by_tooi_uri = {
        r.tooi_uri: r
        for r in (
            await session.execute(
                select(OrganisatieEenheid).where(
                    OrganisatieEenheid.tooi_uri.is_not(None)
                )
            )
        )
        .scalars()
        .all()
        if r.tooi_uri
    }

    for row in rows:
        tooi_uri = (row.get("TOOi URI") or "").strip()
        if not tooi_uri:
            continue
        eenheid = by_tooi_uri.get(tooi_uri)
        if eenheid is None:
            stats.no_tooi_match += 1
            continue

        before = {
            "oin": eenheid.oin,
            "fte_aantal": eenheid.fte_aantal,
            "website": eenheid.website,
        }
        oin = (row.get("OIN") or "").strip() or None
        fte = _parse_int(row.get("Aantal fte") or "")
        organogram = (row.get("Link naar organogram") or "").strip() or None

        changed = False
        if oin and eenheid.oin != oin:
            eenheid.oin = oin
            changed = True
        if fte is not None and eenheid.fte_aantal != fte:
            eenheid.fte_aantal = fte
            changed = True
        if organogram and not eenheid.website:
            # alleen vullen als nog leeg, om handmatige overrides te respecteren
            eenheid.website = organogram
            changed = True

        if changed:
            stats.enriched += 1
            session.add(
                TooiSyncLog(
                    sync_run_id=sync_run_id,
                    bron="ministeries_csv",
                    action="enrich",
                    tooi_uri=tooi_uri,
                    organisatie_eenheid_id=eenheid.id,
                    before=before,
                    after={
                        "oin": eenheid.oin,
                        "fte_aantal": eenheid.fte_aantal,
                        "website": eenheid.website,
                    },
                )
            )

    await session.commit()
    log.info(
        "Ministeries CSV sync run=%s: %d enriched, %d zonder TOOI-match",
        sync_run_id,
        stats.enriched,
        stats.no_tooi_match,
    )
    return stats
