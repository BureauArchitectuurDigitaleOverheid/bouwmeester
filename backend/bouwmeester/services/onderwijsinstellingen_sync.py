"""Importeer onderwijsinstellingen uit handmatige YAML.

Universiteiten + hogescholen worden onder synthetische 'Onderwijsinstellingen'
gehangen. Bron='handmatig' want curated lijst.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid

log = logging.getLogger(__name__)


@dataclass
class OnderwijsSyncStats:
    sync_run_id: uuid.UUID
    nieuwe_universiteiten: int = 0
    nieuwe_hogescholen: int = 0
    onveranderd: int = 0
    fouten: list[str] = field(default_factory=list)


async def sync_onderwijsinstellingen(
    session: AsyncSession,
    yaml_path: Path,
    *,
    commit: bool = True,
) -> OnderwijsSyncStats:
    sync_run_id = uuid.uuid4()
    stats = OnderwijsSyncStats(sync_run_id=sync_run_id)

    data = yaml.safe_load(yaml_path.read_text()) or {}

    parent = (
        (
            await session.execute(
                select(OrganisatieEenheid).where(
                    OrganisatieEenheid.bron == "synthetisch",
                    OrganisatieEenheid.naam == "Onderwijsinstellingen",
                )
            )
        )
        .scalars()
        .first()
    )
    if parent is None:
        stats.fouten.append("Synthetische groep 'Onderwijsinstellingen' ontbreekt")
        return stats

    for type_, items in (
        ("universiteit", data.get("universiteiten") or []),
        ("hogeschool", data.get("hogescholen") or []),
    ):
        for item in items:
            naam = item.get("naam", "").strip()
            afkorting = item.get("afkorting", "").strip() or None
            if not naam:
                continue

            bestaand = (
                (
                    await session.execute(
                        select(OrganisatieEenheid).where(
                            OrganisatieEenheid.naam == naam,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if bestaand:
                stats.onveranderd += 1
                continue

            session.add(
                OrganisatieEenheid(
                    naam=naam,
                    afkorting=afkorting,
                    type=type_,
                    parent_id=parent.id,
                    bron="handmatig",
                )
            )
            if type_ == "universiteit":
                stats.nieuwe_universiteiten += 1
            else:
                stats.nieuwe_hogescholen += 1

    if commit:
        await session.commit()
    else:
        await session.flush()
    log.info(
        "Onderwijssync run=%s: +%d universiteiten, +%d hogescholen, %d onveranderd",
        sync_run_id,
        stats.nieuwe_universiteiten,
        stats.nieuwe_hogescholen,
        stats.onveranderd,
    )
    return stats
