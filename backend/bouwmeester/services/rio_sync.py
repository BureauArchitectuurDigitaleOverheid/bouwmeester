"""Register Internetdomeinen Overheid (RIO) sync.

Bron: `https://organisaties.overheid.nl/archive/exportRIO.xml` — XML met per
overheidsorganisatie een lijst geregistreerde domeinen. Per organisatie staat
een `resourceIdentifierTOOI` (TOOI URI) waarop we matchen tegen onze
OrganisatieEenheid-rijen.

Sync vult `OrganisatieEmailDomein` met de geregistreerde namen. Dit wordt
vervolgens gebruikt voor email-domein-suggestie bij persoon-edit
(`@cjib.nl` -> "Wil je deze persoon koppelen aan CJIB?").

CC0, dagelijks ververst.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

import httpx
from defusedxml.ElementTree import fromstring as xml_fromstring
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.org_email_domein import OrganisatieEmailDomein
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.tooi_sync_log import TooiSyncLog

log = logging.getLogger(__name__)

RIO_URL = "https://organisaties.overheid.nl/archive/exportRIO.xml"
NS = {"p": "https://organisaties.overheid.nl/static/schema/oo/export/0.0.3"}


@dataclass
class RioSyncStats:
    sync_run_id: uuid.UUID
    domeinen_added: int = 0
    domeinen_skipped_no_match: int = 0
    organisaties_zonder_match: list[str] = field(default_factory=list)


def _parse_rio(xml_text: str) -> dict[str, set[str]]:
    """Parse RIO XML naar {tooi_uri: {domein, ...}}."""
    # RIO XML is fetched over HTTP from an external source; the defusedxml
    # parser rejects entity-expansion / XXE that stdlib ElementTree allows.
    root = xml_fromstring(xml_text)
    out: dict[str, set[str]] = {}
    for org in root.findall("p:organisatie", NS):
        tooi_uri = org.get(
            "{https://organisaties.overheid.nl/static/schema/oo/export/0.0.3}"
            "resourceIdentifierTOOI"
        )
        if not tooi_uri:
            continue
        domeinen: set[str] = set()
        for reg in org.iter(
            "{https://organisaties.overheid.nl/static/"
            "schema/oo/export/0.0.3}domeinnaamregistratie"
        ):
            naam_el = reg.find("p:naam", NS)
            if naam_el is not None and naam_el.text:
                domeinen.add(naam_el.text.strip().lower())
        if domeinen:
            out.setdefault(tooi_uri, set()).update(domeinen)
    return out


async def fetch_rio_xml() -> str:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(RIO_URL)
        resp.raise_for_status()
    return resp.text


async def sync_rio(
    session: AsyncSession,
    *,
    fetcher=fetch_rio_xml,
) -> RioSyncStats:
    sync_run_id = uuid.uuid4()
    stats = RioSyncStats(sync_run_id=sync_run_id)

    xml_text = await fetcher()
    feed = _parse_rio(xml_text)
    if not feed:
        log.warning("RIO XML levert geen organisaties met domeinen")
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

    bestaande_domeinen = {
        d.domein.lower(): d.organisatie_eenheid_id
        for d in (await session.execute(select(OrganisatieEmailDomein))).scalars().all()
    }

    for tooi_uri, domeinen in feed.items():
        eenheid = by_tooi_uri.get(tooi_uri)
        if eenheid is None:
            stats.organisaties_zonder_match.append(tooi_uri)
            stats.domeinen_skipped_no_match += len(domeinen)
            continue
        for domein in domeinen:
            if domein in bestaande_domeinen:
                continue
            session.add(
                OrganisatieEmailDomein(
                    organisatie_eenheid_id=eenheid.id,
                    domein=domein,
                    bron="rio",
                )
            )
            bestaande_domeinen[domein] = eenheid.id
            stats.domeinen_added += 1

    if stats.domeinen_added:
        session.add(
            TooiSyncLog(
                sync_run_id=sync_run_id,
                bron="rio",
                action="enrich",
                note=f"+{stats.domeinen_added} domeinen toegevoegd",
            )
        )
    await session.commit()
    log.info(
        "RIO sync run=%s: +%d domeinen, %d skipped (geen TOOI-match)",
        sync_run_id,
        stats.domeinen_added,
        stats.domeinen_skipped_no_match,
    )
    return stats
