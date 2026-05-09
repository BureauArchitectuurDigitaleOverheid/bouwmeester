"""Auto-merge handmatige ministerie-rijen met TOOI-rijen.

Wordt aangeroepen aan het einde van sync_tooi(). Voor type=ministerie
auto-mergen we omdat ministerie-namen wettelijk uniek zijn — kans op
valse positief is nul. Voor andere types blijft reconciliation handmatig.

Mirror van scripts/merge_existing_with_tooi.py maar nu binnen het package
zodat tooi_sync.py er rechtstreeks aan kan.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.pending_reconciliation import PendingReconciliation

log = logging.getLogger(__name__)


def _normaliseer(naam: str) -> str:
    n = " ".join(naam.lower().split())
    if n.startswith("ministerie van "):
        n = n[len("ministerie van ") :]
    return n.strip()


async def merge_ministeries(session: AsyncSession) -> int:
    """Merge handmatige ministerie-rijen met TOOI-rijen via open reconciliations.

    Returns het aantal gemergde rijen. Idempotent: zonder open conflicten
    doet hij niks.
    """
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
        if handmatig.type != "ministerie" or kandidaat.type != "ministerie":
            continue
        if _normaliseer(handmatig.naam) != _normaliseer(kandidaat.naam):
            continue

        log.info(
            "Auto-merge ministerie: handmatig %s (%s) <- TOOI %s (%s)",
            handmatig.id,
            handmatig.naam,
            kandidaat.id,
            kandidaat.naam,
        )

        kandidaat_tooi_uri = kandidaat.tooi_uri
        kandidaat_organisatiesoort = kandidaat.tooi_organisatiesoort
        kandidaat_afkorting = kandidaat.afkorting
        kandidaat_oin = kandidaat.oin

        rec.status = "merged"
        rec.kandidaat_id = None

        await session.delete(kandidaat)
        await session.flush()

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
