"""Dedupliceer Person-rijen die per ongeluk dubbel zijn aangemaakt.

Strategie:
- Zelfde naam EN één van beide is bron='kabinet_yaml' zonder tk_persoon_id
  EN de ander heeft tk_persoon_id (= echte TK-persoon).
- Verplaats alle plaatsingen + roles + permissions van de kabinet-rij naar
  de TK-persoon, verwijder daarna de kabinet-rij.

Idempotent: tweede keer draaien doet niets.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import async_session
from bouwmeester.models.person import Person
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid

log = logging.getLogger(__name__)


async def dedupe(session: AsyncSession) -> int:
    """Geeft aantal opgeruimde duplicaten terug."""
    # Zoek namen die zowel kabinet-rij als TK-rij hebben
    result = await session.execute(
        text(
            """
            SELECT naam FROM person
            GROUP BY naam
            HAVING bool_or(bron = 'kabinet_yaml' AND tk_persoon_id IS NULL)
                AND bool_or(bron = 'tk_odata' AND tk_persoon_id IS NOT NULL)
            """
        )
    )
    namen = [row[0] for row in result.all()]

    opgeruimd = 0
    for naam in namen:
        kabinet_persoon = (
            (
                await session.execute(
                    select(Person).where(
                        Person.naam == naam,
                        Person.bron == "kabinet_yaml",
                        Person.tk_persoon_id.is_(None),
                    )
                )
            )
            .scalars()
            .first()
        )
        tk_persoon = (
            (
                await session.execute(
                    select(Person).where(
                        Person.naam == naam,
                        Person.bron == "tk_odata",
                        Person.tk_persoon_id.is_not(None),
                    )
                )
            )
            .scalars()
            .first()
        )
        if kabinet_persoon is None or tk_persoon is None:
            continue

        # Verplaats alle plaatsingen
        await session.execute(
            update(PersonOrganisatieEenheid)
            .where(PersonOrganisatieEenheid.person_id == kabinet_persoon.id)
            .values(person_id=tk_persoon.id)
        )

        # Person.email overzetten als TK geen email heeft
        if not tk_persoon.email and kabinet_persoon.email:
            tk_persoon.email = kabinet_persoon.email

        await session.delete(kabinet_persoon)
        opgeruimd += 1
        log.info(
            "Dedupe: kabinet-rij '%s' samengevoegd in tk-rij %s", naam, tk_persoon.id
        )

    await session.commit()
    return opgeruimd


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    async with async_session() as session:
        n = await dedupe(session)
    print(f"Dedupe persons: {n} duplicaten samengevoegd")


if __name__ == "__main__":
    asyncio.run(main())
