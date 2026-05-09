"""Scrape rijksoverheid.nl/regering/bewindspersonen voor het huidige kabinet.

Patroon op de pagina:
    <a href="/regering/bewindspersonen/SLUG">
        <h3>NAAM</h3>
        <img ...>
        <p>FUNCTIE-BESCHRIJVING</p>
    </a>

We extraheren naam + functie. De functie bevat 'Minister van X' of
'Staatssecretaris van X' wat we matchen tegen het ministerie via TOOI-naam.

Resultaat wordt naar `kabinet.yaml` geschreven (of opgegeven pad), zodat de
bestaande `kabinet_sync` het kan oppakken. Dit decoupled scrape (kan kapot)
van import (idempotent en stabiel).
"""

from __future__ import annotations

import logging
import re

import httpx
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid

log = logging.getLogger(__name__)

URL = "https://www.rijksoverheid.nl/regering/bewindspersonen"

ENTRY_RE = re.compile(
    r'<a href="/regering/bewindspersonen/[^"]+">\s*'
    r"<h3>([^<]+)</h3>\s*"
    r"<img[^>]*>\s*"
    r"<p>\s*([^<]+?)\s*</p>",
    re.IGNORECASE,
)

# Mapping van rijksoverheid.nl ministerienamen naar TOOI-namen wanneer ze niet
# 1-op-1 zijn. Cleaning: lower + trim + strippen aanduiding.
MINISTERIE_ALIAS: dict[str, str] = {
    "algemene zaken": "Algemene Zaken",
    "binnenlandse zaken en koninkrijksrelaties": "Binnenlandse Zaken en Koninkrijksrelaties",  # noqa: E501
    "buitenlandse zaken": "Buitenlandse Zaken",
    "buitenlandse handel en ontwikkelingssamenwerking": "Buitenlandse Zaken",
    "defensie": "Defensie",
    "economische zaken en klimaat": "Economische Zaken en Klimaat",
    "economische zaken": "Economische Zaken en Klimaat",
    "klimaat en groene groei": "Klimaat en Groene Groei",
    "financien": "Financiën",
    "financiën": "Financiën",
    "infrastructuur en waterstaat": "Infrastructuur en Waterstaat",
    "justitie en veiligheid": "Justitie en Veiligheid",
    "asiel en migratie": "Asiel en Migratie",
    "landbouw, visserij, voedselzekerheid en natuur": (
        "Landbouw, Visserij, Voedselzekerheid en Natuur"
    ),
    "landbouw, natuur en voedselkwaliteit": (
        "Landbouw, Visserij, Voedselzekerheid en Natuur"
    ),
    "onderwijs, cultuur en wetenschap": "Onderwijs, Cultuur en Wetenschap",
    "sociale zaken en werkgelegenheid": "Sociale Zaken en Werkgelegenheid",
    "werk en participatie": "Sociale Zaken en Werkgelegenheid",
    "volksgezondheid, welzijn en sport": "Volksgezondheid, Welzijn en Sport",
    "langdurige zorg, jeugd en sport": "Volksgezondheid, Welzijn en Sport",
    "volkshuisvesting en ruimtelijke ordening": (
        "Volkshuisvesting en Ruimtelijke Ordening"
    ),
    # Staatssecretaris-portefeuilles (niet apart ministerie maar SS bij een ministerie)
    "koninkrijksrelaties en slagvaardige overheid": (
        "Binnenlandse Zaken en Koninkrijksrelaties"
    ),
    "onderwijs en emancipatie": "Onderwijs, Cultuur en Wetenschap",
    "herstel toeslagen": "Financiën",
    "digitale economie en soevereiniteit": "Economische Zaken en Klimaat",
}


def _detecteer_ministerie(functie_tekst: str) -> str | None:
    """Pak het ministerie uit een functie-string als 'Minister van BZK'.

    Strategie:
    1. Zoek 'Minister/Staatssecretaris van/voor X' tot komma-met-functie-erna
       (bv. ', 1e viceminister-president') of einde regel.
    2. Test eerst de hele match tegen MINISTERIE_ALIAS, daarna progressief
       kortere varianten.
    """
    m = re.search(
        r"(?:Minister|Staatssecretaris)(?:\s+van|\s+voor)?\s+(?:de\s+)?(.+?)$",
        functie_tekst,
        re.IGNORECASE,
    )
    if not m:
        return None
    raw = m.group(1).strip()
    # Strip postfix-rollen (bv. ', 1e viceminister-president')
    raw = re.split(
        r",\s*(?:1e|2e|3e|vice|viceminister|minister-president)\s", raw, maxsplit=1
    )[0]
    # Probeer hele string + steeds meer kop afkappen op komma's
    parts = [raw] + [p.strip() for p in raw.split(",")]
    for kandidaat in parts:
        key = kandidaat.lower().strip()
        if key in MINISTERIE_ALIAS:
            return MINISTERIE_ALIAS[key]
    return None


def _detecteer_functie(functie_tekst: str) -> str:
    """Bepaal of dit een minister of staatssecretaris is."""
    t = functie_tekst.lower()
    # MP staat altijd voorop in de string (komma-gescheiden 'Minister-president, ...')
    if t.startswith("minister-president") or t.startswith("minister president"):
        return "minister_president"
    if "staatssecretaris" in t:
        return "staatssecretaris"
    if "minister" in t:
        return "minister"
    return "overig"


async def scrape_bewindspersonen() -> list[tuple[str, str]]:
    """Pak de huidige bewindspersonen-pagina en parse naam + functie."""
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(URL)
        resp.raise_for_status()
    return [
        (naam.strip(), funct.strip()) for naam, funct in ENTRY_RE.findall(resp.text)
    ]


async def bouw_kabinet_yaml_data(session: AsyncSession) -> dict:
    """Bouw een dict in het kabinet.yaml-formaat op basis van de scrape.

    Levert {'bewindspersonen': [...]} dat kabinet_sync direct kan inlezen.
    """
    items = await scrape_bewindspersonen()
    if not items:
        log.warning("rijksoverheid.nl/regering/bewindspersonen leverde 0 entries")
        return {"bewindspersonen": []}

    # Map TOOI-namen -> tooi_uri
    tooi_rows = (
        (
            await session.execute(
                select(OrganisatieEenheid).where(
                    OrganisatieEenheid.type == "ministerie",
                    OrganisatieEenheid.tooi_uri.is_not(None),
                    OrganisatieEenheid.geldig_tot.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    uri_per_tooi_naam: dict[str, str] = {}
    for row in tooi_rows:
        naam = row.naam
        if naam.lower().startswith("ministerie van "):
            naam = naam[len("ministerie van ") :]
        uri_per_tooi_naam[naam] = row.tooi_uri

    bewindspersonen: list[dict] = []
    onbekend: list[str] = []
    for naam, functie_tekst in items:
        ministerie_naam = _detecteer_ministerie(functie_tekst)
        if ministerie_naam is None or ministerie_naam not in uri_per_tooi_naam:
            onbekend.append(f"{naam} ({functie_tekst})")
            continue
        bewindspersonen.append(
            {
                "naam": naam,
                "functie": _detecteer_functie(functie_tekst),
                "ministerie_tooi_uri": uri_per_tooi_naam[ministerie_naam],
                "functietitel": functie_tekst,
            }
        )

    if onbekend:
        log.info(
            "Kabinet-scrape: %d bewindspersonen waarvan ministerie niet matchde:\n%s",
            len(onbekend),
            "\n".join(f"  - {x}" for x in onbekend),
        )
    return {"bewindspersonen": bewindspersonen}


async def schrijf_kabinet_yaml(session: AsyncSession, pad: str) -> int:
    """Scrape en schrijf naar de opgegeven YAML-locatie. Geeft aantal entries."""
    data = await bouw_kabinet_yaml_data(session)
    n = len(data["bewindspersonen"])
    header = (
        "# Auto-gegenereerd door kabinet_scrape.py uit\n"
        "# https://www.rijksoverheid.nl/regering/bewindspersonen\n"
        "# Handmatige bewerkingen worden bij volgende scrape overschreven.\n"
        "# Voor handmatige overrides: maak een aparte YAML en voeg die toe\n"
        "# aan de sync-runner.\n"
    )
    with open(pad, "w") as f:
        f.write(header)
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)
    return n
