"""Tweede Kamer OData personen-sync met echte start/eind-datums.

Bron: `https://gegevensmagazijn.tweedekamer.nl/OData/v4/2.0/FractieZetelPersoon`
— levert per kamerlid de fractie-zittingsperiode met `Van` en `TotEnMet`-velden.
Daaruit halen we de echte start/eind-datum van een lidmaatschap. CC0/public,
dagelijks geüpdatet.

Sync-logica:
- Pak alle FractieZetelPersoon-records met expand op Persoon en
  FractieZetel/Fractie
- Filter op `Verwijderd=false` en `Functie='Lid'`
- Voor elk record:
  * Person (op tk_persoon_id) opzoeken/aanmaken
  * PersonOrganisatieEenheid op (person, eenheid, start_datum) als unique key
  * Eenheid is 'Tweede Kamer' onder HCvS
  * `start_datum=Van.date()`, `eind_datum=TotEnMet.date()` (None = nog actief)
  * `functietitel='Kamerlid (FRACTIE)'`
- Bij hernieuwde sync: bestaande plaatsingen worden geüpdatet als TotEnMet
  veranderde (kamerlid is vertrokken). Geen duplicaten.

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

# TK OData gaat alleen over de Tweede Kamer — Eerste Kamer heeft eigen
# (beperktere) bron. Voor nu mappen we alle TK FractieZetelPersoon naar de
# 'Tweede Kamer' synthetische eenheid.
EENHEID_NAAM = "Tweede Kamer"


@dataclass
class TkSyncStats:
    sync_run_id: uuid.UUID
    nieuwe_personen: int = 0
    nieuwe_plaatsingen: int = 0
    geupdate_plaatsingen: int = 0
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
    """Pak FractieZetelPersoon-records met expand op Persoon en Fractie.

    Met alleen_actief=True (default): alleen records waar TotEnMet null is.
    Voor historische zittingsperiodes zet je dit op False.
    """
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


async def sync_tk_personen(
    session: AsyncSession,
    *,
    fetcher=fetch_fractiezetel_personen,
) -> TkSyncStats:
    sync_run_id = uuid.uuid4()
    stats = TkSyncStats(sync_run_id=sync_run_id)

    feed = await fetcher()
    if not feed:
        log.warning("TK OData feed leeg, sync afgebroken")
        return stats

    eenheid = (
        (
            await session.execute(
                select(OrganisatieEenheid).where(
                    OrganisatieEenheid.naam == EENHEID_NAAM,
                    OrganisatieEenheid.geldig_tot.is_(None),
                )
            )
        )
        .scalars()
        .first()
    )
    if eenheid is None:
        stats.fouten.append(
            f"Geen OrganisatieEenheid '{EENHEID_NAAM}' gevonden — seed_synthetic_groups draaien"  # noqa: E501
        )
        return stats

    bestaande_personen = {
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

    # Bestaande plaatsingen op (person_id, eenheid_id, start_datum) als unieke
    # key — meerdere periodes per persoon zijn mogelijk.
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
        tot = _parse_datum(record.get("TotEnMet"))
        if van is None:
            stats.fouten.append(
                f"FractieZetelPersoon zonder Van-datum overgeslagen (id={record.get('Id')})"  # noqa: E501
            )
            continue
        fractie = (record.get("FractieZetel") or {}).get("Fractie") or {}
        fractielabel = fractie.get("Afkorting") or fractie.get("NaamNL") or "?"
        functietitel = f"Tweede Kamerlid ({fractielabel})"

        person = bestaande_personen.get(tk_id)
        if person is None:
            person = Person(
                naam=naam,
                bron="tk_odata",
                tk_persoon_id=tk_id,
            )
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
            stats.nieuwe_plaatsingen += 1
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
            # Update eind_datum/functietitel als die wijzigde
            if (
                bestaand_plc.eind_datum != tot
                or bestaand_plc.functietitel != functietitel
            ):
                bestaand_plc.eind_datum = tot
                bestaand_plc.functietitel = functietitel
                stats.geupdate_plaatsingen += 1
            else:
                stats.onveranderd += 1

    await session.commit()
    log.info(
        "TK OData sync run=%s: +%d personen, +%d plaatsingen, "
        "%d geüpdatet, %d onveranderd, %d fouten",
        sync_run_id,
        stats.nieuwe_personen,
        stats.nieuwe_plaatsingen,
        stats.geupdate_plaatsingen,
        stats.onveranderd,
        len(stats.fouten),
    )
    return stats
