"""Importeer historische kabinetten met van/tot-data per bewindspersoon.

Bron: handmatig gecureerde YAML in `bouwmeester/data/kabinetten_historisch.yaml`.
Per kabinet staan de bewindspersonen + functies. De van/tot van het kabinet
geeft default voor de plaatsing, individuele afwijkingen kunnen later via
extra YAML-velden.

Idempotent: bestaande plaatsingen met dezelfde (person_naam, eenheid_id,
start_datum) worden overgeslagen.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.tooi_sync_log import TooiSyncLog

log = logging.getLogger(__name__)


@dataclass
class HistorischKabinetStats:
    sync_run_id: uuid.UUID
    nieuwe_personen: int = 0
    nieuwe_plaatsingen: int = 0
    onveranderd: int = 0
    fouten: list[str] = field(default_factory=list)


def _parse_datum(s) -> date | None:
    if s is None:
        return None
    if isinstance(s, date):
        return s
    return datetime.fromisoformat(str(s)).date()


async def sync_historische_kabinetten(
    session: AsyncSession,
    yaml_path: Path,
    *,
    commit: bool = True,
) -> HistorischKabinetStats:
    sync_run_id = uuid.uuid4()
    stats = HistorischKabinetStats(sync_run_id=sync_run_id)

    data = yaml.safe_load(yaml_path.read_text()) or {}

    for kabinet_key, kabinet in data.items():
        if not isinstance(kabinet, dict) or "bewindspersonen" not in kabinet:
            continue
        van = _parse_datum(kabinet.get("van"))
        tot = _parse_datum(kabinet.get("tot"))
        for entry in kabinet["bewindspersonen"]:
            naam = entry.get("naam", "").strip()
            tooi_uri = entry.get("ministerie_tooi_uri", "").strip()
            if not naam or not tooi_uri:
                continue

            eenheid = (
                (
                    await session.execute(
                        select(OrganisatieEenheid).where(
                            OrganisatieEenheid.tooi_uri == tooi_uri
                        )
                    )
                )
                .scalars()
                .first()
            )
            if eenheid is None:
                stats.fouten.append(
                    f"Geen OrganisatieEenheid voor {tooi_uri} (entry {naam} "
                    f"in {kabinet_key})"
                )
                continue

            # Person opzoeken (breed match op naam)
            person = (
                (await session.execute(select(Person).where(Person.naam == naam)))
                .scalars()
                .first()
            )
            if person is None:
                person = Person(naam=naam, bron="kabinet_yaml")
                session.add(person)
                await session.flush()
                stats.nieuwe_personen += 1

            entry_van = _parse_datum(entry.get("van")) or van
            entry_tot = _parse_datum(entry.get("tot")) or tot
            if entry_van is None:
                stats.fouten.append(f"Geen van-datum voor {naam} in {kabinet_key}")
                continue

            # Bestaande plaatsing op (person_id, eenheid_id, start_datum)
            bestaand = (
                (
                    await session.execute(
                        select(PersonOrganisatieEenheid).where(
                            PersonOrganisatieEenheid.person_id == person.id,
                            PersonOrganisatieEenheid.organisatie_eenheid_id
                            == eenheid.id,
                            PersonOrganisatieEenheid.start_datum == entry_van,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if bestaand is not None:
                stats.onveranderd += 1
                continue

            session.add(
                PersonOrganisatieEenheid(
                    person_id=person.id,
                    organisatie_eenheid_id=eenheid.id,
                    dienstverband="extern",
                    functietitel=entry.get("functietitel"),
                    bron="kabinet_yaml",
                    start_datum=entry_van,
                    eind_datum=entry_tot,
                )
            )
            stats.nieuwe_plaatsingen += 1
            session.add(
                TooiSyncLog(
                    sync_run_id=sync_run_id,
                    bron="kabinet",
                    action="add",
                    person_id=person.id,
                    organisatie_eenheid_id=eenheid.id,
                    after={
                        "kabinet": kabinet_key,
                        "naam": naam,
                        "van": entry_van.isoformat(),
                        "tot": entry_tot.isoformat() if entry_tot else None,
                    },
                )
            )

    if commit:
        await session.commit()
    else:
        await session.flush()
    log.info(
        "Historische kabinetten sync run=%s: +%d personen, +%d plaatsingen, "
        "%d onveranderd, %d fouten",
        sync_run_id,
        stats.nieuwe_personen,
        stats.nieuwe_plaatsingen,
        stats.onveranderd,
        len(stats.fouten),
    )
    return stats
