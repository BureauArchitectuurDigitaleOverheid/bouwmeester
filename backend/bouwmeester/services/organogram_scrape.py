"""Scrape DG/directie-laag uit rijksoverheid.nl organogram-pagina's.

TOOI eindigt bij ministerie-niveau. De gestructureerde HTML op
`rijksoverheid.nl/ministeries/<slug>/organisatie/organogram` levert per
ministerie een lijst DG's (`<a class="wayfinder__item">`), en per DG-pagina
de directies als `<h2>`-koppen. Voor 8 van de 12 ministeries werkt dit
patroon. De 4 die het niet doen (AZ, Defensie, EZK/KGG-in-opbouw, Asiel) gaan
via `data/directies_handmatig.yaml`.

Upsert-regels:
- Match op (ministerie_id, naam) — geen TOOI-URI beschikbaar
- bron='organogram_scrape' op nieuwe rijen
- Mag NOOIT een handmatige rij overschrijven (ook niet bij naam-collision)
- Geen soft-delete: scrape mist soms door site-redesign, dus bestaande
  rijen blijven staan als ze niet meer in de scrape verschijnen
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.text import unescape_html
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.tooi_sync_log import TooiSyncLog

log = logging.getLogger(__name__)

ORGANOGRAM_BASE = "https://www.rijksoverheid.nl"
WAYFINDER_RE = re.compile(
    r'<a class="wayfinder__item"[^>]*href="(/ministeries/[^"]+)"[^>]*>([^<]+)</a>',
    re.IGNORECASE,
)
H2_RE = re.compile(r"<h2[^>]*>([^<]+)</h2>", re.IGNORECASE)

# Pagina-meta-koppen die geen directies zijn — uitsluiten van H2-scrape
H2_BLACKLIST = {
    "verantwoordelijk",
    "service",
    "over deze site",
    "contact",
    "documenten",
    "nieuws",
    "leiding",
    "u bevindt zich hier",
    "secundaire navigatie",
    "primaire navigatie",
    "verwante onderwerpen",
}

# Welke ministeries het rijksoverheid.nl/.../organisatie/organogram patroon
# volgen (op basis van eerder live-onderzoek 2026-05).
SCRAPEBARE_MINISTERIE_SLUGS = {
    "ministerie-van-binnenlandse-zaken-en-koninkrijksrelaties",
    "ministerie-van-buitenlandse-zaken",
    "ministerie-van-financien",
    "ministerie-van-justitie-en-veiligheid",
    "ministerie-van-onderwijs-cultuur-en-wetenschap",
    "ministerie-van-sociale-zaken-en-werkgelegenheid",
    "ministerie-van-volksgezondheid-welzijn-en-sport",
    "ministerie-van-landbouw-natuur-en-voedselkwaliteit",
    "ministerie-van-economische-zaken",
}

# Ministerienaam-aliassen: TOOI-naam -> rijksoverheid.nl-slug. Voor ministeries
# die op rijksoverheid.nl onder een oudere naam (kabinetwissel) staan dan TOOI
# nu hanteert.
SLUG_ALIAS: dict[str, str] = {
    "ministerie-van-economische-zaken-en-klimaat": "ministerie-van-economische-zaken",
    "ministerie-van-landbouw-visserij-voedselzekerheid-en-natuur": (
        "ministerie-van-landbouw-natuur-en-voedselkwaliteit"
    ),
}


@dataclass
class DgInfo:
    naam: str
    detail_url: str


@dataclass
class OrganogramScrapeStats:
    sync_run_id: uuid.UUID
    dgs_added: int = 0
    directies_added: int = 0
    skipped: list[str] = field(default_factory=list)


def _parse_organogram_index(html: str) -> list[DgInfo]:
    """Pak alle DG's uit de organogram-indexpagina."""
    return [
        DgInfo(naam=unescape_html(naam.strip()), detail_url=ORGANOGRAM_BASE + url)
        for url, naam in WAYFINDER_RE.findall(html)
    ]


def _parse_directies(html: str) -> list[str]:
    """Pak directies (h2-koppen) uit DG-detailpagina, exclusief metadata-koppen."""
    out: list[str] = []
    for h in H2_RE.findall(html):
        clean = unescape_html(h.strip())
        if not clean:
            continue
        if clean.lower() in H2_BLACKLIST:
            continue
        out.append(clean)
    return out


async def _scrape_ministry(
    client: httpx.AsyncClient,
    slug: str,
) -> tuple[list[DgInfo], dict[str, list[str]]]:
    """Levert (lijst DG's, mapping DG-naam -> [directie-namen])."""
    index_url = f"{ORGANOGRAM_BASE}/ministeries/{slug}/organisatie/organogram"
    resp = await client.get(index_url)
    if resp.status_code != 200:
        log.warning("Geen organogram-pagina voor %s (HTTP %d)", slug, resp.status_code)
        return ([], {})
    dgs = _parse_organogram_index(resp.text)
    directies: dict[str, list[str]] = {}
    for dg in dgs:
        sub = await client.get(dg.detail_url)
        if sub.status_code != 200:
            continue
        directies[dg.naam] = _parse_directies(sub.text)
    return (dgs, directies)


def _slug_van_url(website: str | None) -> str | None:
    if not website:
        return None
    m = re.search(r"/ministeries/([a-z0-9-]+)/", website)
    return m.group(1) if m else None


def _classificeer_dg_type(naam: str) -> str:
    """Bepaal type op basis van de DG-pagina-naam.

    Niet alle wayfinder-items op een organogram-pagina zijn echte DG's:
    politieke leiding, clusters, secretaris-generaal, agentschappen,
    inspecties en commissies komen óók voor onder dezelfde lijst.
    """
    n = naam.lower()
    if "politieke leiding" in n or n.startswith("ambtelijke leiding"):
        return "cluster"
    if n.startswith("cluster ") or " cluster" in n:
        return "cluster"
    if n.startswith("inspectie ") or " inspectie" in n:
        return "agentschap"
    if "agentschap" in n or n.startswith("dienst "):
        return "agentschap"
    if "commissie" in n or "raad voor" in n:
        return "overig"
    if "regeringscommissaris" in n or "secretariaat" in n:
        return "overig"
    if n.startswith("dg ") or n.startswith("directoraat-generaal"):
        return "directoraat_generaal"
    if n.startswith("nationaal coordinator") or n.startswith("nationaal coördinator"):
        return "overig"
    return "directoraat_generaal"


def _slug_van_naam(naam: str) -> str:
    """Construeer rijksoverheid.nl-slug uit een TOOI-ministerienaam.

    'ministerie van Justitie en Veiligheid' -> 'ministerie-van-justitie-en-veiligheid'
    """
    n = naam.lower().strip()
    # Diakritieken weg en spaties naar streepjes
    n = (
        n.replace("ë", "e")
        .replace("ï", "i")
        .replace("ö", "o")
        .replace("ü", "u")
        .replace("é", "e")
        .replace("ê", "e")
    )
    n = re.sub(r"\s+", "-", n)
    n = re.sub(r"[^a-z0-9-]", "", n)
    return n


async def sync_organogram(
    session: AsyncSession,
    *,
    fetcher=None,
) -> OrganogramScrapeStats:
    sync_run_id = uuid.uuid4()
    stats = OrganogramScrapeStats(sync_run_id=sync_run_id)

    # Pak ministeries uit DB
    ministeries = (
        (
            await session.execute(
                select(OrganisatieEenheid).where(
                    OrganisatieEenheid.type == "ministerie",
                    OrganisatieEenheid.geldig_tot.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )

    async def _real_fetcher(slug: str):
        async with httpx.AsyncClient(timeout=30.0) as client:
            return await _scrape_ministry(client, slug)

    fetch = fetcher or _real_fetcher

    for ministerie in ministeries:
        slug = _slug_van_url(ministerie.website) or _slug_van_naam(ministerie.naam)
        slug = SLUG_ALIAS.get(slug, slug)
        if slug not in SCRAPEBARE_MINISTERIE_SLUGS:
            stats.skipped.append(ministerie.naam)
            continue
        # LVVN/EZK kunnen via alias mappen naar slugs die WEL scrapebaar zijn
        if slug in {
            "ministerie-van-economische-zaken",
            "ministerie-van-landbouw-natuur-en-voedselkwaliteit",
        }:
            pass  # impliciet scrapebaar

        dgs, directies_per_dg = await fetch(slug)
        if not dgs:
            stats.skipped.append(ministerie.naam)
            continue

        # Bestaande children van dit ministerie
        bestaande_children = {
            r.naam: r
            for r in (
                await session.execute(
                    select(OrganisatieEenheid).where(
                        OrganisatieEenheid.parent_id == ministerie.id,
                        OrganisatieEenheid.geldig_tot.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        }

        for dg in dgs:
            # Skip als handmatig al bestaat met dezelfde naam
            if dg.naam in bestaande_children:
                continue
            dg_type = _classificeer_dg_type(dg.naam)
            dg_row = OrganisatieEenheid(
                naam=dg.naam,
                type=dg_type,
                parent_id=ministerie.id,
                bron="organogram_scrape",
            )
            session.add(dg_row)
            await session.flush()
            stats.dgs_added += 1
            session.add(
                TooiSyncLog(
                    sync_run_id=sync_run_id,
                    bron="organogram",
                    action="add",
                    organisatie_eenheid_id=dg_row.id,
                    after={"naam": dg.naam, "type": "directoraat_generaal"},
                )
            )

            # Directies onder DG
            for d_naam in directies_per_dg.get(dg.naam, []):
                # Check niet handmatig
                bestaand = (
                    (
                        await session.execute(
                            select(OrganisatieEenheid).where(
                                OrganisatieEenheid.naam == d_naam,
                                OrganisatieEenheid.parent_id == dg_row.id,
                                OrganisatieEenheid.geldig_tot.is_(None),
                            )
                        )
                    )
                    .scalars()
                    .first()
                )
                if bestaand:
                    continue
                dir_row = OrganisatieEenheid(
                    naam=d_naam,
                    type="directie",
                    parent_id=dg_row.id,
                    bron="organogram_scrape",
                )
                session.add(dir_row)
                stats.directies_added += 1

    await session.commit()
    log.info(
        "Organogram scrape run=%s: +%d DGs, +%d directies, %d ministeries skipped",
        sync_run_id,
        stats.dgs_added,
        stats.directies_added,
        len(stats.skipped),
    )
    return stats
