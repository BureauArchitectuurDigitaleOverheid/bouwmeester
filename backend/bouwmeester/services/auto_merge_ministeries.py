"""Merge manual ministerie rows into their TOOI rows automatically.

Called at the end of ``sync_tooi()``.  For type ministerie a name match is
safe (ministerie names are unique by law); other types are reconciled by
hand.

Only an official-looking manual row is merged: a top-level one (no parent)
that is not a user's own external root (no eenheid eigenaar).  A ministerie
someone hung below their own organisation is left alone, so it cannot take
over the TOOI row.  The TOOI row always survives: the manual row's
children, placements and grants move onto it (``merge_into``).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.pending_reconciliation import PendingReconciliation
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.services.merge_organisatie_eenheden import merge_into

log = logging.getLogger(__name__)


def _normalize(naam: str) -> str:
    n = " ".join(naam.lower().split())
    if n.startswith("ministerie van "):
        n = n[len("ministerie van ") :]
    return n.strip()


async def _is_official_candidate(
    session: AsyncSession, handmatig: OrganisatieEenheid
) -> bool:
    """A top-level manual ministerie that is not someone's own root."""
    if handmatig.parent_id is not None:
        return False
    owner = await session.scalar(
        select(ResourcePermission.id)
        .where(
            ResourcePermission.resource_type == "organisatie_eenheid",
            ResourcePermission.resource_id == handmatig.id,
            ResourcePermission.rol == "eigenaar",
        )
        .limit(1)
    )
    return owner is None


async def merge_ministries(session: AsyncSession) -> int:
    """Merge manual ministerie rows into TOOI rows via open reconciliations.

    Returns the number of merged rows.  Idempotent: without open conflicts
    it does nothing.
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
        if _normalize(handmatig.naam) != _normalize(kandidaat.naam):
            continue
        if not await _is_official_candidate(session, handmatig):
            log.warning(
                "Auto-merge ministerie skipped: %s (%s) is not a top-level "
                "manual ministerie; left for manual reconciliation",
                handmatig.id,
                handmatig.naam,
            )
            continue

        # One savepoint per row, so an unexpected FK or unique violation
        # does not roll back the whole sync; the open row stays visible in
        # Beheer > Reconciliatie for a manual merge.
        naam = handmatig.naam
        try:
            async with session.begin_nested():
                log.info(
                    "Auto-merge ministerie: handmatig %s (%s) -> TOOI %s (%s)",
                    handmatig.id,
                    naam,
                    kandidaat.id,
                    kandidaat.naam,
                )
                await merge_into(session, source=handmatig, target=kandidaat)
                rec.status = "merged"
                merged_count += 1
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "Auto-merge failed for reconciliation %s (%s): %s; skipped",
                rec.id,
                naam,
                exc,
            )

    await session.commit()
    return merged_count
