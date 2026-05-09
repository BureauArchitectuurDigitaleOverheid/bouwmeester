"""Eerste-run merge tussen bestaande handmatige rijen en TOOI-import.

Voor `type='ministerie'` doen we een veilige auto-merge: bestaande handmatige
rij krijgt het TOOI-veld toegekend, de TOOI-duplicaat wordt verwijderd, en de
bestaande sub-boom (DG/directie/afdeling/team) blijft intact.

Voor andere types (ZBO, agentschap, koepel, marktpartij) doen we GEEN auto-merge
maar laten we de pending_reconciliation rij staan zodat een mens kan beslissen.

Aannames:
- TOOI-sync is al gedraaid en heeft `tooi_uri` op nieuwe rijen geschreven.
- Reconciliatie-rijen zijn aangemaakt voor naam-conflicten.
- Ministerie-namen zijn wettelijk uniek dus kans op valse-positief is nul.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import async_session
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.pending_reconciliation import PendingReconciliation

log = logging.getLogger(__name__)


def _normaliseer(naam: str) -> str:
    n = " ".join(naam.lower().split())
    if n.startswith("ministerie van "):
        n = n[len("ministerie van ") :]
    return n.strip()


async def merge_ministeries(session: AsyncSession) -> int:
    """Merge handmatige ministerie-rijen met TOOI-rijen.

    Returns het aantal succesvol gemerged rijen.
    """
    # Open reconciliations voor ministeries
    rows = (
        (
            await session.execute(
                select(PendingReconciliation).where(
                    PendingReconciliation.resource_type == "organisatie_eenheid",
                    PendingReconciliation.status == "open",
                    PendingReconciliation.kandidaat_bron == "tooi",
                )
            )
        )
        .scalars()
        .all()
    )

    merged_count = 0
    for rec in rows:
        handmatig = await session.get(OrganisatieEenheid, rec.handmatige_id)
        kandidaat = await session.get(OrganisatieEenheid, rec.kandidaat_id)
        if handmatig is None or kandidaat is None:
            continue
        # Alleen ministerie-naar-ministerie auto-merge
        if handmatig.type != "ministerie" or kandidaat.type != "ministerie":
            continue
        # Genormaliseerde naam moet matchen
        if _normaliseer(handmatig.naam) != _normaliseer(kandidaat.naam):
            continue

        log.info(
            "Merge ministerie: handmatig %s (%s) <- TOOI %s (%s)",
            handmatig.id,
            handmatig.naam,
            kandidaat.id,
            kandidaat.naam,
        )

        # Memo TOOI-velden voordat we kandidaat verwijderen
        kandidaat_tooi_uri = kandidaat.tooi_uri
        kandidaat_organisatiesoort = kandidaat.tooi_organisatiesoort
        kandidaat_afkorting = kandidaat.afkorting
        kandidaat_oin = kandidaat.oin

        # Reconciliation oplossen (kandidaat_id loskoppelen vóór delete)
        rec.status = "merged"
        rec.kandidaat_id = None

        # TOOI-duplicaat eerst verwijderen + flushen, anders schendt
        # de tooi_uri-update straks de unique-constraint.
        await session.delete(kandidaat)
        await session.flush()

        # Schrijf TOOI-velden op handmatige rij
        handmatig.tooi_uri = kandidaat_tooi_uri
        handmatig.tooi_organisatiesoort = kandidaat_organisatiesoort
        if not handmatig.afkorting and kandidaat_afkorting:
            handmatig.afkorting = kandidaat_afkorting
        if not handmatig.oin and kandidaat_oin:
            handmatig.oin = kandidaat_oin
        if handmatig.bron == "handmatig":
            handmatig.bron = "tooi"
        merged_count += 1

    await session.commit()
    return merged_count


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    async with async_session() as session:
        n = await merge_ministeries(session)
    print(f"Merge ministeries: {n} rijen gemerged")


if __name__ == "__main__":
    asyncio.run(main())
