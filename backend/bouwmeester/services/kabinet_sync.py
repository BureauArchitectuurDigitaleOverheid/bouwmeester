"""Synchroniseer kabinet.yaml -> Person + PersonOrganisatieEenheid.

De YAML bevat de huidige set bewindspersonen. Bij elke run:
  - Nieuwe entries -> Person aanmaken (bron='kabinet_yaml') + plaatsing
  - Verwijderd uit YAML -> placement.eind_datum = today (Person blijft bestaan)
  - Functie-/ministerie-wijziging -> oude placement eind_datum, nieuwe placement

Hiermee verloopt 'Eddie van Marum is Staatssecretaris' automatisch zodra
zijn naam uit de YAML verdwijnt na kabinetswissel.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.tooi_sync_log import TooiSyncLog

log = logging.getLogger(__name__)


@dataclass
class KabinetSyncStats:
    sync_run_id: uuid.UUID
    nieuwe_personen: int = 0
    new_placements: int = 0
    verlopen_plaatsingen: int = 0
    onveranderd: int = 0
    fouten: list[str] = field(default_factory=list)


def _parse_datum(s: Any, fallback: date | None = None) -> date | None:
    if s is None:
        return fallback
    if isinstance(s, date):
        return s
    return datetime.fromisoformat(str(s)).date()


async def sync_kabinet(
    session: AsyncSession,
    yaml_path: Path,
) -> KabinetSyncStats:
    sync_run_id = uuid.uuid4()
    stats = KabinetSyncStats(sync_run_id=sync_run_id)
    today = date.today()

    data = yaml.safe_load(yaml_path.read_text()) or {}
    entries = data.get("bewindspersonen") or []

    # Map (naam, ministerie_tooi_uri) -> entry voor snelle lookup
    yaml_keys: set[tuple[str, str]] = set()
    for e in entries:
        if not e:
            continue
        try:
            yaml_keys.add((e["naam"].strip(), e["ministerie_tooi_uri"].strip()))
        except (KeyError, AttributeError):
            stats.fouten.append(f"Onvolledige entry: {e!r}")

    # Huidige actieve plaatsingen met bron=kabinet_yaml
    huidige_plaatsingen = (
        (
            await session.execute(
                select(PersonOrganisatieEenheid).where(
                    PersonOrganisatieEenheid.bron == "kabinet_yaml",
                    PersonOrganisatieEenheid.eind_datum.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )

    huidige_keys: dict[tuple[str, str], PersonOrganisatieEenheid] = {}
    for plc in huidige_plaatsingen:
        person = await session.get(Person, plc.person_id)
        eenheid = await session.get(OrganisatieEenheid, plc.organisatie_eenheid_id)
        if person and eenheid and eenheid.tooi_uri:
            huidige_keys[(person.naam.strip(), eenheid.tooi_uri.strip())] = plc

    # Verlopen: in DB maar niet meer in YAML
    for key, plc in huidige_keys.items():
        if key not in yaml_keys:
            plc.eind_datum = today
            stats.verlopen_plaatsingen += 1
            session.add(
                TooiSyncLog(
                    sync_run_id=sync_run_id,
                    bron="kabinet",
                    action="soft_delete",
                    person_id=plc.person_id,
                    organisatie_eenheid_id=plc.organisatie_eenheid_id,
                    note="bewindspersoon niet meer in kabinet.yaml",
                )
            )

    # Toevoegen / onveranderd
    for entry in entries:
        if not entry:
            continue
        naam = entry.get("naam", "").strip()
        tooi_uri = entry.get("ministerie_tooi_uri", "").strip()
        if not naam or not tooi_uri:
            continue
        if (naam, tooi_uri) in huidige_keys:
            stats.onveranderd += 1
            continue

        # Person opzoeken — eerst breed op naam (bewindspersonen zijn vaak
        # ex-Kamerlid en bestaan al via tk_odata). Alleen nieuw aanmaken als
        # de naam echt nog niet voorkomt; voorkomt dubbele Person-rijen.
        # Match-strategie:
        #   1. Exact naam
        #   2. Achternaam-substring (bv. 'Pieter Heerma' matcht 'Pieter
        #      Enneüs Heerma')
        person = (
            (await session.execute(select(Person).where(Person.naam == naam)))
            .scalars()
            .first()
        )
        if person is None:
            # Probeer match op laatste woord van de naam (achternaam)
            achternaam = naam.split()[-1] if naam else ""
            voornaam = naam.split()[0] if naam else ""
            if achternaam and voornaam:
                kandidaten = (
                    (
                        await session.execute(
                            select(Person).where(
                                Person.naam.ilike(f"%{achternaam}"),
                                Person.naam.ilike(f"{voornaam}%"),
                                Person.tk_persoon_id.is_not(None),
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                if len(kandidaten) == 1:
                    person = kandidaten[0]
                    log.info(
                        "Kabinet: '%s' gemerged in bestaande TK-persoon '%s'",
                        naam,
                        person.naam,
                    )
        if person is None:
            person = Person(
                naam=naam,
                email=entry.get("email"),
                bron="kabinet_yaml",
            )
            session.add(person)
            await session.flush()
            stats.nieuwe_personen += 1

        # Eenheid opzoeken
        eenheid = (
            (
                await session.execute(
                    select(OrganisatieEenheid).where(
                        OrganisatieEenheid.tooi_uri == tooi_uri,
                    )
                )
            )
            .scalars()
            .first()
        )
        if eenheid is None:
            stats.fouten.append(
                f"Geen OrganisatieEenheid gevonden voor TOOI-URI {tooi_uri} (entry {naam})"  # noqa: E501
            )
            continue

        plc = PersonOrganisatieEenheid(
            person_id=person.id,
            organisatie_eenheid_id=eenheid.id,
            dienstverband="extern",
            functietitel=entry.get("functietitel"),
            bron="kabinet_yaml",
            start_datum=_parse_datum(entry.get("van"), today) or today,
            eind_datum=_parse_datum(entry.get("tot"), None),
        )
        session.add(plc)
        stats.new_placements += 1

        session.add(
            TooiSyncLog(
                sync_run_id=sync_run_id,
                bron="kabinet",
                action="add",
                person_id=person.id,
                organisatie_eenheid_id=eenheid.id,
                after={
                    "naam": naam,
                    "functietitel": entry.get("functietitel"),
                    "ministerie": eenheid.naam,
                },
            )
        )

    await session.commit()
    log.info(
        "Kabinet sync run=%s: +%d personen, +%d plaatsingen, "
        "-%d verlopen, %d onveranderd, %d fouten",
        sync_run_id,
        stats.nieuwe_personen,
        stats.new_placements,
        stats.verlopen_plaatsingen,
        stats.onveranderd,
        len(stats.fouten),
    )
    return stats
