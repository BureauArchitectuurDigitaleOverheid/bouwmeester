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
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.query_utils import escape_like
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.tooi_sync_log import TooiSyncLog
from bouwmeester.services.sync_matching import (
    PersonMatch,
    create_sync_person,
    match_sync_person,
)

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


async def _tk_person_by_parts(session: AsyncSession, naam: str) -> Person | None:
    """The one usable TK person with *naam*'s first and last word, or None."""
    parts = naam.split()
    if len(parts) < 2:
        return None
    voornaam, achternaam = parts[0], parts[-1]
    match = await match_sync_person(
        session,
        naam,
        bronnen={"tk_odata"},
        where=and_(
            Person.naam.ilike(f"%{escape_like(achternaam)}"),
            Person.naam.ilike(f"{escape_like(voornaam)}%"),
        ),
    )
    if match.person is not None:
        log.info(
            "Kabinet: '%s' gemerged in bestaande TK-persoon '%s'",
            naam,
            match.person.naam,
        )
    return match.person


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

        # Person opzoeken.  Alleen personen die een sync zelf bracht: een
        # eerdere kabinet-run, of een TK-persoon op zijn vaste sleutel
        # (bewindspersonen zijn vaak ex-Kamerlid).  Nooit een account of een
        # contact dat zich naar de bewindspersoon heeft hernoemd.
        #   1. Exact naam
        #   2. Voor- en achternaam van een TK-persoon (bv. 'Pieter Heerma'
        #      matcht 'Pieter Enneüs Heerma')
        match = await match_sync_person(
            session, naam, bronnen={"kabinet_yaml", "tk_odata"}
        )
        if match.person is None and not match.ambiguous:
            tk = await _tk_person_by_parts(session, naam)
            if tk is not None:
                match = PersonMatch(person=tk)
        if match.person is None and not match.ambiguous:
            match = await create_sync_person(
                session,
                naam,
                bron="kabinet_yaml",
                sync_run_id=sync_run_id,
                log_bron="kabinet",
                match=match,
            )
        if match.person is None:
            stats.fouten.append(match.ambiguity(naam))
            continue
        person = match.person
        stats.nieuwe_personen += match.created

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

        eind_datum = _parse_datum(entry.get("tot"), None)

        # `huidige_keys` is op naam gekeyed, maar de insert gebeurt op id. De
        # achternaam-match hierboven kan twee YAML-namen op dezelfde Person
        # uitkomen, en dan zou de naam-check de botsing niet zien. Daarom
        # hier nog een id-check tegen uq_active_placement, dat per
        # (person, eenheid, bron) maar één open rij toestaat.
        if eind_datum is None:
            al_actief = (
                (
                    await session.execute(
                        select(PersonOrganisatieEenheid).where(
                            PersonOrganisatieEenheid.person_id == person.id,
                            PersonOrganisatieEenheid.organisatie_eenheid_id
                            == eenheid.id,
                            PersonOrganisatieEenheid.bron == "kabinet_yaml",
                            PersonOrganisatieEenheid.eind_datum.is_(None),
                        )
                    )
                )
                .scalars()
                .first()
            )
            if al_actief is not None:
                stats.onveranderd += 1
                continue

        plc = PersonOrganisatieEenheid(
            person_id=person.id,
            organisatie_eenheid_id=eenheid.id,
            dienstverband="extern",
            functietitel=entry.get("functietitel"),
            bron="kabinet_yaml",
            start_datum=_parse_datum(entry.get("van"), today) or today,
            eind_datum=eind_datum,
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
