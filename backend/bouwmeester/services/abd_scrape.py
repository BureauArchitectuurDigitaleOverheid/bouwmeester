"""Scrape ABD-benoemingen-nieuws via Playwright.

De algemenebestuursdienst.nl/actueel/nieuws/-pagina's bevatten een continue
feed van top-ambtenaar-benoemingen ("Esther Pijs directeur-generaal Migratie
bij JenV"). De pagina is een Next.js SPA dus we gebruiken Playwright om
te wachten tot de hydratie klaar is.

Per benoeming extraheren we:
- naam (uit titel)
- functie (uit titel)
- ministerie/organisatie-afkorting (uit titel: "bij {ORG}")
- ingangsdatum + (optioneel) eind-vorige-functie (uit body)

Sync-resultaat: PersonOrganisatieEenheid-rijen met bron='abd_scrape',
gekoppeld aan de TOOI-rij van het ministerie of agentschap.

CC0/openbaar; geen licentie-issue. AVG: ABD-functies zijn publiek
(art. 6.1.e) — namen + functies zijn al openbaar gepubliceerd op
abd.nl als nieuwsbericht.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.tooi_sync_log import TooiSyncLog

log = logging.getLogger(__name__)

NIEUWS_URL = "https://www.algemenebestuursdienst.nl/actueel/nieuws"

# Mapping van afkortingen die in ABD-titels voorkomen naar TOOI-namen
# (zonder 'ministerie van '-prefix). Onbekende afkortingen worden in een
# 'andere overheid'-vangnet gezet.
AFKORTING_NAAR_MINISTERIE: dict[str, str] = {
    "AZ": "Algemene Zaken",
    "BZK": "Binnenlandse Zaken en Koninkrijksrelaties",
    "BuZa": "Buitenlandse Zaken",
    "Defensie": "Defensie",
    "EZK": "Economische Zaken en Klimaat",
    "FIN": "Financiën",
    "Financien": "Financiën",
    "Financiën": "Financiën",
    "IenW": "Infrastructuur en Waterstaat",
    "JenV": "Justitie en Veiligheid",
    "OCW": "Onderwijs, Cultuur en Wetenschap",
    "SZW": "Sociale Zaken en Werkgelegenheid",
    "VWS": "Volksgezondheid, Welzijn en Sport",
    "LNV": "Landbouw, Visserij, Voedselzekerheid en Natuur",
    "LVVN": "Landbouw, Visserij, Voedselzekerheid en Natuur",
    "KGG": "Klimaat en Groene Groei",
    "VRO": "Volkshuisvesting en Ruimtelijke Ordening",
    "AenM": "Asiel en Migratie",
}

# Functies/diensten die in de titel kunnen staan ipv ministerie-afkorting.
# Wijzen naar specifieke uitvoerders/agentschappen.
DIENST_NAAR_NAAM_HINT: dict[str, str] = {
    "Belastingdienst": "Belastingdienst",
    "Justis": "Dienst Justis",
    "DUO": "Dienst Uitvoering Onderwijs",
    "RVO": "Rijksdienst voor Ondernemend Nederland",
    "RDW": "RDW",
    "RvIG": "Rijksdienst voor Identiteitsgegevens",
    "NCTV": "Nationaal Coördinator Terrorismebestrijding en Veiligheid",
}


@dataclass
class AbdBenoeming:
    naam: str
    functietitel: str
    organisatie_hint: str  # raw afkorting/dienstnaam uit titel
    nieuws_url: str
    publicatiedatum: date
    ingangsdatum: date | None = None


@dataclass
class AbdSyncStats:
    sync_run_id: uuid.UUID
    nieuwe_personen: int = 0
    nieuwe_plaatsingen: int = 0
    onveranderd: int = 0
    geen_org_match: int = 0
    fouten: list[str] = field(default_factory=list)


# Regex om de titel te splitsen: "Naam functie-zin bij ORG"
TITEL_SPLITTER = re.compile(
    r"^(?P<naam>[A-Z][\w\.\-' ]+?)\s+"
    r"(?P<functie>(?:waarnemend\s+|kwartiermaker[\-/]\s*|kwartiermaker\s+)?"
    r"(?:directeur(?:-generaal)?|hoofd(?:\s+afdeling)?|afdelingshoofd|"
    r"plaatsvervangend\s+\w+|(?:secretaris|inspecteur|chief|raadadviseur|"
    r"ambassadeur)\s+\S+|secretaris-generaal|directeur-generaal)"
    r"\s+[\w\s,&\-]+?)\s+bij\s+(?P<org>[\w\s\-]+?)$",
    re.IGNORECASE,
)

# Datum-patroon in body: "met ingang van DD MAAND YYYY"
INGANGSDATUM_RE = re.compile(
    r"(?:met\s+ingang\s+van|per|start(?:\s+op)?)\s+"
    r"(?P<dag>\d{1,2})\s+"
    r"(?P<maand>januari|februari|maart|april|mei|juni|juli|augustus|"
    r"september|oktober|november|december)\s+"
    r"(?P<jaar>\d{4})",
    re.IGNORECASE,
)
MAAND_NAAR_NUMMER = {
    "januari": 1,
    "februari": 2,
    "maart": 3,
    "april": 4,
    "mei": 5,
    "juni": 6,
    "juli": 7,
    "augustus": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "december": 12,
}


def _parse_ingangsdatum(body: str) -> date | None:
    m = INGANGSDATUM_RE.search(body)
    if not m:
        return None
    try:
        return date(
            int(m.group("jaar")),
            MAAND_NAAR_NUMMER[m.group("maand").lower()],
            int(m.group("dag")),
        )
    except (KeyError, ValueError):
        return None


def _split_titel(volledige_titel: str) -> tuple[str, str, str] | None:
    """Splits 'X is Y bij Z' in (naam, functie, org_hint).

    Falt back op een ruwe split als de regex niet matcht.
    """
    titel = volledige_titel.strip()
    # 'bij ORG' aan het einde
    m = re.match(r"^(.+?)\s+bij\s+([^,]+?)$", titel)
    if not m:
        return None
    voor_bij = m.group(1).strip()
    org_hint = m.group(2).strip()

    # Splits voor_bij in naam en functie. Strategie: zoek de eerste
    # functie-trigger (directeur, hoofd, generaal, etc.) en alles vóór is naam.
    triggers = [
        "directeur-generaal",
        "secretaris-generaal",
        "plaatsvervangend",
        "kwartiermaker",
        "directeur",
        "hoofd",
        "afdelingshoofd",
        "inspecteur",
        "chief",
        "ambassadeur",
        "raadadviseur",
        "concerndirecteur",
    ]
    voor_bij_lower = voor_bij.lower()
    pos = -1
    for t in triggers:
        idx = voor_bij_lower.find(t)
        if idx >= 0 and (pos < 0 or idx < pos):
            pos = idx
    if pos <= 0:
        return None
    naam = voor_bij[:pos].strip()
    functie = voor_bij[pos:].strip()
    return naam, functie, org_hint


async def fetch_recente_benoemingen(
    *, max_pages: int = 3, headless: bool = True
) -> list[AbdBenoeming]:
    """Pak ABD-benoemingsnieuws via Playwright.

    Pas zoveel pagina's als opgegeven (default 3 ~= 30 nieuwste benoemingen).
    """
    from playwright.async_api import async_playwright

    out: list[AbdBenoeming] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page()
        for pagina_nr in range(1, max_pages + 1):
            url = f"{NIEUWS_URL}?page={pagina_nr}" if pagina_nr > 1 else NIEUWS_URL
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(1500)
                items = await page.eval_on_selector_all(
                    'a[href*="/actueel/nieuws/2"]',
                    "els => els.map(e => ({href: e.href, txt: (e.textContent||'').trim()}))",  # noqa: E501
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("ABD-scrape pagina %s failed: %s", pagina_nr, exc)
                continue

            for item in items:
                href = item["href"]
                txt = item["txt"]
                # URL-pattern: /actueel/nieuws/YYYY/MM/DD/slug
                m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/([^/]+)$", href)
                if not m:
                    continue
                pub_jaar, pub_maand, pub_dag, _slug = m.groups()

                # ABD news-cards renderen titel + body zonder spatie ertussen.
                # We zoeken de eerste "bij {Org}" en knippen daarna af zodra
                # we body-tekst tegenkomen. Body begint typisch met
                # "{Voornaam} {Achternaam} (wordt|start|begint)..." — dus
                # gewoon alles vóór de tweede keer dat we de naam zien.
                #
                # Alternatief en eenvoudiger: pak " bij {ORG}" maar ORG kan
                # met opvolgende body-tekst aan elkaar plakken
                # ('JenVEsther'). Detect dat door op een hoofdletter na een
                # andere hoofdletter te splitten — zolang het ORG zelf niet
                # bestaat uit twee hoofdletter-woorden ('Hoge Raad', etc).
                eerste_zin = re.split(r"[.\n]", txt, 1)[0].strip()
                # Probeer 'bij {ORG}' waarbij ORG tot maximaal 30 chars na 'bij'
                # gaat tot de body begint (eerste lowercase woord). De body
                # start altijd met een naam (hoofdletter) gevolgd door een
                # werkwoord ('wordt', 'is', 'start', etc).
                m2 = re.search(
                    r"\bbij\s+([A-Z][\w\-&\s]*?)"
                    r"(?=[A-Z][a-z]+\s+(?:wordt|is|start|begint|krijgt|"
                    r"verlaat|gaat|treedt|werkt|volgt))",
                    eerste_zin,
                )
                if m2:
                    org_end = m2.end(1)
                    eerste_zin = eerste_zin[:org_end].strip()
                else:
                    # Fallback: knip op de eerste 'naar X' of na 80 chars
                    eerste_zin = eerste_zin[:120]

                parts = _split_titel(eerste_zin)
                if not parts:
                    continue
                naam, functie, org_hint = parts
                # Trim org_hint van body-pollutie. Bekende afkortingen
                # (JenV, IenW, OCW, BZK, etc.) zijn 2-5 chars met
                # hoofdletter/kleine-letter mix; daarna begint vaak een
                # voornaam ('Esther', 'Niels') van de body. Probeer eerst:
                # exact bekende afkorting prefix matchen.
                bekend = sorted(
                    list(AFKORTING_NAAR_MINISTERIE.keys())
                    + list(DIENST_NAAR_NAAM_HINT.keys()),
                    key=len,
                    reverse=True,
                )
                for afk in bekend:
                    if org_hint.startswith(afk):
                        org_hint = afk
                        break
                else:
                    # Knip op eerste 'na hoofdletter komt body-Voornaam'
                    # patroon. ABD-body begint met capitalized voornaam
                    # gevolgd door 'wordt/start/is/etc' werkwoord.
                    m_split = re.search(
                        r"([A-Z][a-z]+)\s+(?:wordt|is|start|begint|krijgt|"
                        r"verlaat|gaat|treedt|werkt|volgt)",
                        org_hint,
                    )
                    if m_split:
                        org_hint = org_hint[: m_split.start(1)].strip()

                # Body fetch voor ingangsdatum is optioneel (extra HTTP-call)
                ingangsdatum: date | None = None
                m_in = INGANGSDATUM_RE.search(txt)
                if m_in:
                    try:
                        ingangsdatum = date(
                            int(m_in.group("jaar")),
                            MAAND_NAAR_NUMMER[m_in.group("maand").lower()],
                            int(m_in.group("dag")),
                        )
                    except (KeyError, ValueError):
                        ingangsdatum = None

                try:
                    publicatiedatum = date(int(pub_jaar), int(pub_maand), int(pub_dag))
                except ValueError:
                    publicatiedatum = date.today()

                out.append(
                    AbdBenoeming(
                        naam=naam,
                        functietitel=functie,
                        organisatie_hint=org_hint,
                        nieuws_url=href,
                        publicatiedatum=publicatiedatum,
                        ingangsdatum=ingangsdatum,
                    )
                )

        await browser.close()

    # Dedupe op (naam, functie, org_hint) — paginatie kan dubbele leveren
    seen: set[tuple[str, str, str]] = set()
    deduped: list[AbdBenoeming] = []
    for b in out:
        key = (b.naam, b.functietitel, b.organisatie_hint)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(b)
    return deduped


async def _resolveer_organisatie(
    session: AsyncSession, hint: str
) -> OrganisatieEenheid | None:
    """Vind OrganisatieEenheid op basis van afkorting/dienstnaam-hint.

    Strategie:
    1. Strip 'de '/'het ' prefix.
    2. Match op ministerie-afkorting (AFKORTING_NAAR_MINISTERIE).
    3. Match op specifieke dienst-naam (DIENST_NAAR_NAAM_HINT).
    4. Direct naam-zoek case-insensitive (substring).
    5. Voor onbekende diensten zoals Belastingdienst zonder TOOI-rij:
       fallback naar ministerie-rij van het overkoepelende ministerie als
       de hint vaak voorkomt (Belastingdienst -> Financiën).
    """
    hint_clean = hint.strip()
    # Strip 'de '/'het ' prefix
    hint_clean = re.sub(r"^(?:de|het)\s+", "", hint_clean, flags=re.IGNORECASE)

    # 1. Ministerie-afkorting
    if hint_clean in AFKORTING_NAAR_MINISTERIE:
        target = AFKORTING_NAAR_MINISTERIE[hint_clean]
        row = (
            (
                await session.execute(
                    select(OrganisatieEenheid).where(
                        OrganisatieEenheid.naam.ilike(f"%{target}"),
                        OrganisatieEenheid.type == "ministerie",
                        OrganisatieEenheid.geldig_tot.is_(None),
                    )
                )
            )
            .scalars()
            .first()
        )
        if row:
            return row
    # 2. Specifieke dienst
    if hint_clean in DIENST_NAAR_NAAM_HINT:
        target = DIENST_NAAR_NAAM_HINT[hint_clean]
        row = (
            (
                await session.execute(
                    select(OrganisatieEenheid)
                    .where(
                        OrganisatieEenheid.naam.ilike(f"%{target}%"),
                        OrganisatieEenheid.geldig_tot.is_(None),
                    )
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if row:
            return row
    # 3. Direct naam-zoek (case-insensitive substring)
    row = (
        (
            await session.execute(
                select(OrganisatieEenheid)
                .where(
                    OrganisatieEenheid.naam.ilike(f"%{hint_clean}%"),
                    OrganisatieEenheid.geldig_tot.is_(None),
                )
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if row:
        return row
    # 4. Fallback: koppel diensten zonder eigen TOOI-rij aan hun
    # overkoepelende ministerie.
    _dienst_fallback_ministerie = {
        "Belastingdienst": "Financiën",
        "Douane": "Financiën",
        "FIOD": "Financiën",
        "NCTV": "Justitie en Veiligheid",
        "Politie": "Justitie en Veiligheid",
        "DJI": "Justitie en Veiligheid",
        "IND": "Asiel en Migratie",
        "Rijkswaterstaat": "Infrastructuur en Waterstaat",
    }
    if hint_clean in _dienst_fallback_ministerie:
        target = _dienst_fallback_ministerie[hint_clean]
        row = (
            (
                await session.execute(
                    select(OrganisatieEenheid).where(
                        OrganisatieEenheid.naam.ilike(f"%{target}"),
                        OrganisatieEenheid.type == "ministerie",
                        OrganisatieEenheid.geldig_tot.is_(None),
                    )
                )
            )
            .scalars()
            .first()
        )
        if row:
            return row
    return None


async def sync_abd(
    session: AsyncSession,
    *,
    fetcher=fetch_recente_benoemingen,
    commit: bool = True,
) -> AbdSyncStats:
    """Scrape ABD-benoemingen en koppel ze aan personen + organisaties.

    Idempotent: bij elk record wordt op (Person.naam + functietitel + eenheid)
    gecheckt of de plaatsing al bestaat. Bestaat hij: niets doen.
    """
    sync_run_id = uuid.uuid4()
    stats = AbdSyncStats(sync_run_id=sync_run_id)
    date.today()

    benoemingen = await fetcher()
    if not benoemingen:
        log.warning("ABD-scrape leverde 0 benoemingen op")
        return stats

    for b in benoemingen:
        eenheid = await _resolveer_organisatie(session, b.organisatie_hint)
        if eenheid is None:
            stats.geen_org_match += 1
            stats.fouten.append(
                f"Geen organisatie-match voor '{b.organisatie_hint}' "
                f"(persoon: {b.naam})"
            )
            continue

        # Person opzoeken op exact naam
        person = (
            (await session.execute(select(Person).where(Person.naam == b.naam)))
            .scalars()
            .first()
        )
        if person is None:
            person = Person(naam=b.naam, bron="abd_scrape")
            session.add(person)
            await session.flush()
            stats.nieuwe_personen += 1

        # Bestaat plaatsing al?
        bestaand = (
            (
                await session.execute(
                    select(PersonOrganisatieEenheid).where(
                        PersonOrganisatieEenheid.person_id == person.id,
                        PersonOrganisatieEenheid.organisatie_eenheid_id == eenheid.id,
                        PersonOrganisatieEenheid.functietitel == b.functietitel,
                        PersonOrganisatieEenheid.bron == "abd_scrape",
                    )
                )
            )
            .scalars()
            .first()
        )
        if bestaand is not None:
            stats.onveranderd += 1
            continue

        plc = PersonOrganisatieEenheid(
            person_id=person.id,
            organisatie_eenheid_id=eenheid.id,
            dienstverband="extern",
            functietitel=b.functietitel,
            bron="abd_scrape",
            start_datum=b.ingangsdatum or b.publicatiedatum,
        )
        session.add(plc)
        stats.nieuwe_plaatsingen += 1
        session.add(
            TooiSyncLog(
                sync_run_id=sync_run_id,
                bron="abd_scrape",
                action="add",
                person_id=person.id,
                organisatie_eenheid_id=eenheid.id,
                after={
                    "naam": b.naam,
                    "functietitel": b.functietitel,
                    "ingangsdatum": (
                        b.ingangsdatum.isoformat() if b.ingangsdatum else None
                    ),
                    "nieuws_url": b.nieuws_url,
                },
            )
        )

    if commit:
        await session.commit()
    else:
        await session.flush()
    log.info(
        "ABD-scrape run=%s: +%d personen, +%d plaatsingen, "
        "%d onveranderd, %d zonder org-match",
        sync_run_id,
        stats.nieuwe_personen,
        stats.nieuwe_plaatsingen,
        stats.onveranderd,
        stats.geen_org_match,
    )
    return stats
