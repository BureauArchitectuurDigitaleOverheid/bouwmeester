"""Valideer scripts/data/externe_org_reconciliation.yaml tegen TOOI-data in DB.

Voor elke entry met actie=merge_tooi: controleer dat de target ook werkelijk
in TOOI bestaat. Voor actie=nieuw_handmatig: controleer dat parent_synth een
bestaande synthetische groep is.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import async_session
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid

YAML_PATH = Path(__file__).resolve().parent / "data" / "externe_org_reconciliation.yaml"


async def vind_tooi(
    session: AsyncSession,
    *,
    naam: str | None = None,
    afkorting: str | None = None,
    naam_substring: str | None = None,
) -> OrganisatieEenheid | None:
    stmt = select(OrganisatieEenheid).where(OrganisatieEenheid.bron == "tooi")
    if naam:
        stmt = stmt.where(OrganisatieEenheid.naam == naam)
    elif afkorting:
        stmt = stmt.where(OrganisatieEenheid.afkorting.ilike(afkorting))
    elif naam_substring:
        stmt = stmt.where(OrganisatieEenheid.naam.ilike(f"%{naam_substring}%"))
    res = (await session.execute(stmt)).scalars().first()
    return res


async def main() -> None:
    data = yaml.safe_load(YAML_PATH.read_text())
    rec_map: dict[str, dict] = data["reconciliations"]

    async with async_session() as session:
        synth_namen = {
            r.naam
            for r in (
                await session.execute(
                    select(OrganisatieEenheid).where(
                        OrganisatieEenheid.bron == "synthetisch"
                    )
                )
            )
            .scalars()
            .all()
        }

        problems = 0
        for naam, entry in rec_map.items():
            actie = entry.get("actie")
            if actie == "merge_tooi":
                target = None
                match_kind = entry.get("match")
                if match_kind == "naam_exact":
                    target = await vind_tooi(session, naam=entry["naam"])
                elif match_kind == "afkorting":
                    target = await vind_tooi(
                        session, afkorting=entry["afkorting_voor_match"]
                    )
                    if target is None and "fallback_naam_search" in entry:
                        target = await vind_tooi(
                            session,
                            naam_substring=entry["fallback_naam_search"],
                        )
                elif match_kind == "tooi_uri":
                    target = await vind_tooi(
                        session, naam=entry["tooi_uri_search_naam"]
                    )
                if target is None:
                    print(
                        f"  [PROBLEEM] {naam!r}: merge_tooi maar geen TOOI-rij gevonden"
                    )
                    problems += 1
                else:
                    print(f"  [OK] {naam!r} -> {target.naam} ({target.tooi_uri})")
            elif actie == "nieuw_handmatig":
                synth = entry.get("parent_synth")
                if synth not in synth_namen:
                    print(f"  [PROBLEEM] {naam!r}: parent_synth {synth!r} bestaat niet")
                    problems += 1
                else:
                    print(f"  [OK] {naam!r} -> nieuw_handmatig onder {synth}")
            else:
                print(f"  [PROBLEEM] {naam!r}: onbekende actie {actie!r}")
                problems += 1

        print()
        print(f"Totaal {len(rec_map)} entries, {problems} problemen")
        if problems:
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
