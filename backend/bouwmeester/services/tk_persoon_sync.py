"""Tweede en Eerste Kamer OData personen-sync.

Twee bronnen op `gegevensmagazijn.tweedekamer.nl/OData/v4/2.0`:

1. **FractieZetelPersoon** (Tweede Kamer): levert echte Van/TotEnMet datums
   per fractie-zittingsperiode. Eén persoon kan meerdere periodes hebben.
2. **Persoon** (Eerste Kamer): geen FractieZetelPersoon-equivalent voor EK.
   Filter op `Functie='Eerste Kamerlid'` en koppel aan de 'Eerste Kamer'-
   eenheid met `start_datum=today` (of bestaande start als persoon al gekend
   is). Bij verdwijnen uit feed -> `eind_datum=today`.

CC0/public, dagelijks geüpdatet sinds 2012.

AVG: kamerleden zijn publieke functies onder art. 6.1.e — geen issue.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.tooi_sync_log import TooiSyncLog

log = logging.getLogger(__name__)

ODATA_BASE = "https://gegevensmagazijn.tweedekamer.nl/OData/v4/2.0"
PAGE_SIZE = 250

TK_EENHEID_NAAM = "Tweede Kamer"
EK_EENHEID_NAAM = "Eerste Kamer"


@dataclass
class TkSyncStats:
    sync_run_id: uuid.UUID
    nieuwe_personen: int = 0
    new_placements: int = 0
    geupdate_plaatsingen: int = 0
    verlopen_plaatsingen: int = 0
    onveranderd: int = 0
    fouten: list[str] = field(default_factory=list)


def _bouw_naam(record: dict) -> str:
    delen: list[str] = []
    if record.get("Roepnaam"):
        delen.append(record["Roepnaam"])
    elif record.get("Voornamen"):
        delen.append(record["Voornamen"])
    if record.get("Tussenvoegsel"):
        delen.append(record["Tussenvoegsel"])
    if record.get("Achternaam"):
        delen.append(record["Achternaam"])
    return " ".join(delen).strip()


def _parse_datum(s: str | None) -> date | None:
    if not s:
        return None
    return datetime.fromisoformat(s).date()


async def fetch_fractiezetel_personen(*, alleen_actief: bool = True) -> list[dict]:
    """TK FractieZetelPersoon met expand op Persoon en Fractie."""
    out: list[dict] = []
    filt = "Verwijderd eq false and Functie eq 'Lid'"
    if alleen_actief:
        filt += " and TotEnMet eq null"
    expand = "Persoon,FractieZetel($expand=Fractie)"
    url: str | None = (
        f"{ODATA_BASE}/FractieZetelPersoon"
        f"?$filter={filt}&$expand={expand}&$top={PAGE_SIZE}"
    )
    async with httpx.AsyncClient(timeout=60.0) as client:
        while url:
            resp = await client.get(url)
            resp.raise_for_status()
            payload = resp.json()
            out.extend(payload.get("value", []))
            url = payload.get("@odata.nextLink")
    return out


async def fetch_oud_kamerleden() -> list[dict]:
    """Persoon-records waar Functie='Oud Kamerlid' (voor naam-fuzzy-match).

    Wordt door kabinet_sync gebruikt om bewindspersonen-met-TK-historie
    aan een tk_persoon_id te koppelen (bv. Pieter Heerma was Tweede
    Kamerlid en is nu minister BZK).

    LET OP: dit kunnen er ~3000 zijn. Alleen ophalen wanneer expliciet
    nodig (kabinet-sync), niet als reguliere sync — anders DB-bloat.
    """
    out: list[dict] = []
    url: str | None = (
        f"{ODATA_BASE}/Persoon"
        f"?$filter=Verwijderd eq false and Functie eq 'Oud Kamerlid'"
        f"&$top={PAGE_SIZE}"
    )
    async with httpx.AsyncClient(timeout=120.0) as client:
        while url:
            resp = await client.get(url)
            resp.raise_for_status()
            payload = resp.json()
            out.extend(payload.get("value", []))
            url = payload.get("@odata.nextLink")
    return out


async def fetch_eerste_kamerleden() -> list[dict]:
    """Persoon-records waar Functie='Eerste Kamerlid' en niet-verwijderd."""
    out: list[dict] = []
    url: str | None = (
        f"{ODATA_BASE}/Persoon"
        f"?$filter=Verwijderd eq false and Functie eq 'Eerste Kamerlid'"
        f"&$top={PAGE_SIZE}"
    )
    async with httpx.AsyncClient(timeout=60.0) as client:
        while url:
            resp = await client.get(url)
            resp.raise_for_status()
            payload = resp.json()
            out.extend(payload.get("value", []))
            url = payload.get("@odata.nextLink")
    return out


async def _get_eenheid(session: AsyncSession, naam: str) -> OrganisatieEenheid | None:
    return (
        (
            await session.execute(
                select(OrganisatieEenheid).where(
                    OrganisatieEenheid.naam == naam,
                    OrganisatieEenheid.geldig_tot.is_(None),
                )
            )
        )
        .scalars()
        .first()
    )


async def _existing_persons_by_tk_id(
    session: AsyncSession,
) -> dict[str, Person]:
    return {
        p.tk_persoon_id: p
        for p in (
            await session.execute(
                select(Person).where(Person.tk_persoon_id.is_not(None))
            )
        )
        .scalars()
        .all()
        if p.tk_persoon_id
    }


async def _sync_tk(
    session: AsyncSession,
    sync_run_id: uuid.UUID,
    fractiezetel_fetcher,
    bestaande_personen: dict[str, Person],
    stats: TkSyncStats,
) -> None:
    eenheid = await _get_eenheid(session, TK_EENHEID_NAAM)
    if eenheid is None:
        stats.fouten.append(f"Geen OrganisatieEenheid '{TK_EENHEID_NAAM}'")
        return

    feed = await fractiezetel_fetcher()

    huidige_plaatsingen = (
        (
            await session.execute(
                select(PersonOrganisatieEenheid).where(
                    PersonOrganisatieEenheid.bron == "tk_odata",
                    PersonOrganisatieEenheid.organisatie_eenheid_id == eenheid.id,
                )
            )
        )
        .scalars()
        .all()
    )
    plc_per_key: dict[tuple[uuid.UUID, date], PersonOrganisatieEenheid] = {
        (p.person_id, p.start_datum): p for p in huidige_plaatsingen
    }

    for record in feed:
        persoon = record.get("Persoon") or {}
        tk_id = persoon.get("Id")
        if not tk_id:
            continue
        naam = _bouw_naam(persoon)
        if not naam:
            continue
        van = _parse_datum(record.get("Van"))
        if van is None:
            stats.fouten.append(
                f"FractieZetelPersoon zonder Van-datum (id={record.get('Id')})"
            )
            continue
        tot = _parse_datum(record.get("TotEnMet"))
        fractie = (record.get("FractieZetel") or {}).get("Fractie") or {}
        fractielabel = fractie.get("Afkorting") or fractie.get("NaamNL") or "?"
        functietitel = f"Tweede Kamerlid ({fractielabel})"

        person = bestaande_personen.get(tk_id)
        if person is None:
            person = Person(naam=naam, bron="tk_odata", tk_persoon_id=tk_id)
            session.add(person)
            await session.flush()
            bestaande_personen[tk_id] = person
            stats.nieuwe_personen += 1
        elif person.naam != naam:
            person.naam = naam

        key = (person.id, van)
        bestaand_plc = plc_per_key.get(key)
        if bestaand_plc is None:
            session.add(
                PersonOrganisatieEenheid(
                    person_id=person.id,
                    organisatie_eenheid_id=eenheid.id,
                    dienstverband="extern",
                    functietitel=functietitel,
                    bron="tk_odata",
                    start_datum=van,
                    eind_datum=tot,
                )
            )
            stats.new_placements += 1
            session.add(
                TooiSyncLog(
                    sync_run_id=sync_run_id,
                    bron="tk_odata",
                    action="add",
                    person_id=person.id,
                    organisatie_eenheid_id=eenheid.id,
                    after={
                        "naam": naam,
                        "functietitel": functietitel,
                        "van": van.isoformat(),
                        "tot": tot.isoformat() if tot else None,
                    },
                )
            )
        else:
            if (
                bestaand_plc.eind_datum != tot
                or bestaand_plc.functietitel != functietitel
            ):
                bestaand_plc.eind_datum = tot
                bestaand_plc.functietitel = functietitel
                stats.geupdate_plaatsingen += 1
            else:
                stats.onveranderd += 1


async def _sync_ek(
    session: AsyncSession,
    sync_run_id: uuid.UUID,
    ek_fetcher,
    bestaande_personen: dict[str, Person],
    stats: TkSyncStats,
) -> None:
    eenheid = await _get_eenheid(session, EK_EENHEID_NAAM)
    if eenheid is None:
        stats.fouten.append(f"Geen OrganisatieEenheid '{EK_EENHEID_NAAM}'")
        return

    feed = await ek_fetcher()
    today = date.today()

    huidige_plaatsingen = (
        (
            await session.execute(
                select(PersonOrganisatieEenheid).where(
                    PersonOrganisatieEenheid.bron == "tk_odata",
                    PersonOrganisatieEenheid.organisatie_eenheid_id == eenheid.id,
                    PersonOrganisatieEenheid.eind_datum.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    actief_per_person_id: dict[uuid.UUID, PersonOrganisatieEenheid] = {
        p.person_id: p for p in huidige_plaatsingen
    }

    feed_person_ids: set[uuid.UUID] = set()

    for record in feed:
        tk_id = record.get("Id")
        if not tk_id:
            continue
        naam = _bouw_naam(record)
        if not naam:
            continue
        fractielabel = record.get("Fractielabel") or "?"
        functietitel = f"Eerste Kamerlid ({fractielabel})"

        person = bestaande_personen.get(tk_id)
        if person is None:
            person = Person(naam=naam, bron="tk_odata", tk_persoon_id=tk_id)
            session.add(person)
            await session.flush()
            bestaande_personen[tk_id] = person
            stats.nieuwe_personen += 1
        elif person.naam != naam:
            person.naam = naam

        feed_person_ids.add(person.id)

        if person.id in actief_per_person_id:
            plc = actief_per_person_id[person.id]
            if plc.functietitel != functietitel:
                plc.functietitel = functietitel
                stats.geupdate_plaatsingen += 1
            else:
                stats.onveranderd += 1
        else:
            session.add(
                PersonOrganisatieEenheid(
                    person_id=person.id,
                    organisatie_eenheid_id=eenheid.id,
                    dienstverband="extern",
                    functietitel=functietitel,
                    bron="tk_odata",
                    start_datum=today,
                )
            )
            stats.new_placements += 1
            session.add(
                TooiSyncLog(
                    sync_run_id=sync_run_id,
                    bron="tk_odata",
                    action="add",
                    person_id=person.id,
                    organisatie_eenheid_id=eenheid.id,
                    after={"naam": naam, "functietitel": functietitel},
                )
            )

    # Verlopen: actieve plaatsingen die niet meer in EK-feed zitten
    for person_id, plc in actief_per_person_id.items():
        if person_id not in feed_person_ids:
            plc.eind_datum = today
            stats.verlopen_plaatsingen += 1
            session.add(
                TooiSyncLog(
                    sync_run_id=sync_run_id,
                    bron="tk_odata",
                    action="soft_delete",
                    person_id=person_id,
                    organisatie_eenheid_id=eenheid.id,
                    note="EK-lid niet meer in feed",
                )
            )


async def sync_tk_personen(
    session: AsyncSession,
    *,
    fractiezetel_fetcher=fetch_fractiezetel_personen,
    ek_fetcher=fetch_eerste_kamerleden,
) -> TkSyncStats:
    """Sync TK + EK in één run."""
    sync_run_id = uuid.uuid4()
    stats = TkSyncStats(sync_run_id=sync_run_id)

    bestaande_personen = await _existing_persons_by_tk_id(session)

    await _sync_tk(
        session, sync_run_id, fractiezetel_fetcher, bestaande_personen, stats
    )
    await _sync_ek(session, sync_run_id, ek_fetcher, bestaande_personen, stats)

    await session.commit()
    log.info(
        "TK+EK sync run=%s: +%d personen, +%d plaatsingen, "
        "%d geüpdatet, %d verlopen, %d onveranderd, %d fouten",
        sync_run_id,
        stats.nieuwe_personen,
        stats.new_placements,
        stats.geupdate_plaatsingen,
        stats.verlopen_plaatsingen,
        stats.onveranderd,
        len(stats.fouten),
    )
    return stats
