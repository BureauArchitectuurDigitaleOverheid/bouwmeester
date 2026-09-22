"""Stel zoektermen voor bij een bestaande term, met gemeten trefferaantallen.

Waarom geen automatische query expansion: de tellingen per term zijn het
enige stuurmiddel dat een breed vangnet bestuurbaar houdt. Je ziet dat
`"Digitale Dienst"` zeven treffers gaf en `"machineleesbare wetgeving"`
nul, en stelt bij. Zodra het systeem zelf termen toevoegt weet je niet meer
waarom iets binnenkwam, kun je een verzonnen term niet gericht uitzetten,
en wijst de wegklik-teller naar iets wat niemand heeft gekozen.

Een meting op 22 september 2026 onderbouwt dat:

- Van elf geteste termen gaven er zeven **nul** treffers. Een model dat
  varianten verzint, verzint er veel die niets opleveren maar wel elke
  ronde een HTTP-call naar andermans server kosten.
- `"regelrechter"` is morfologisch verwant aan `"RegelRecht"` maar
  semantisch een ander begrip; hij bracht een begroting van de Raad voor
  de rechtspraak binnen.
- `"digitale overheid"` gaf acht extra documenten, maar dat is een ander
  onderwerp volgen, geen variant van dezelfde term.

Dus: het model doet een voorstel, deze module meet wat elk voorstel
oplevert, en de gebruiker kiest. Wat hij kiest wordt een gewoon abonnement
met een eigen teller.
"""

import asyncio
import logging
from dataclasses import dataclass

from bouwmeester.services.tkconv_client import TkconvClient

logger = logging.getLogger(__name__)

# Hoeveel kandidaten we hooguit meten. Elke meting is een HTTP-call naar
# tkconv, dus dit is tegelijk de bovengrens op wat één klik daar kost.
MAX_KANDIDATEN = 8


@dataclass
class Suggestie:
    """Eén voorgestelde zoekterm, met wat hij zou opleveren."""

    term: str
    reden: str
    soort: str  # "variant" | "verwant" | "afkorting"
    treffers: int = 0
    # Documenten die de huidige termen nog niet vinden. Dit is het getal
    # dat telt: een term die alleen dubbelt voegt niets toe.
    nieuwe_treffers: int = 0
    voorbeelden: list[str] | None = None

    @property
    def voegt_toe(self) -> bool:
        return self.nieuwe_treffers > 0


async def stel_voor(
    huidige_termen: list[str],
    llm_service,
    client: TkconvClient,
    onderwerp: str | None = None,
) -> list[Suggestie]:
    """Vraag de LLM om varianten en meet wat ze opleveren.

    `huidige_termen` zijn de zoekopdrachten zoals ze de bron in gaan
    (dus gequote waar dat hoort). Geeft de kandidaten terug, gesorteerd op
    wat ze toevoegen boven wat er al gevolgd wordt.
    """
    if not huidige_termen:
        return []

    kandidaten = await _vraag_kandidaten(huidige_termen, llm_service, onderwerp)
    if not kandidaten:
        return []

    # Wat vinden de huidige termen al? Dat is de referentie waartegen we
    # "nieuw" afmeten.
    huidig = await _documenten_van(huidige_termen, client)

    gemeten: list[Suggestie] = []
    for suggestie in kandidaten[:MAX_KANDIDATEN]:
        gevonden = await _documenten_van([suggestie.term], client)
        nieuw = gevonden - huidig
        suggestie.treffers = len(gevonden)
        suggestie.nieuwe_treffers = len(nieuw)
        suggestie.voorbeelden = sorted(nieuw)[:3]
        gemeten.append(suggestie)

    # Sorteer op wat het toevoegt, niet op wat het vindt: een term die
    # alles dubbelt is minder waard dan een term met één unieke treffer.
    gemeten.sort(key=lambda s: (s.nieuwe_treffers, s.treffers), reverse=True)
    return gemeten


async def _vraag_kandidaten(
    huidige_termen: list[str], llm_service, onderwerp: str | None
) -> list[Suggestie]:
    from bouwmeester.services.llm.prompts import build_zoekterm_suggestie_prompt

    prompt = build_zoekterm_suggestie_prompt(
        huidige_termen=huidige_termen, onderwerp=onderwerp
    )
    try:
        tekst = await llm_service._complete(prompt)
        data = llm_service._parse_json(tekst)
    except Exception:
        logger.exception("Kon geen zoekterm-suggesties ophalen")
        return []

    kandidaten = []
    for rij in (data or {}).get("suggesties", [])[:MAX_KANDIDATEN]:
        term = str(rij.get("term", "")).strip().strip('"')
        if len(term) < 3:
            continue
        kandidaten.append(
            Suggestie(
                term=term,
                reden=str(rij.get("reden", "")).strip(),
                soort=str(rij.get("soort", "variant")).strip(),
            )
        )
    return kandidaten


async def _documenten_van(termen: list[str], client: TkconvClient) -> set[str]:
    """Welke documentnummers vinden deze termen samen?"""
    nummers: set[str] = set()
    for index, term in enumerate(termen):
        kern = term.strip().strip('"')
        zoekopdracht = f'"{kern}"'
        for item in await client.search(zoekopdracht):
            nummers.add(item.document_nummer)
        # tkconv draait op andermans server; ga er rustig overheen.
        if index < len(termen) - 1:
            await asyncio.sleep(1.0)
    return nummers
