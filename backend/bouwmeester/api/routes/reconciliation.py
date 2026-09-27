"""Admin-endpoints voor pending_reconciliation oplossing.

Wanneer TOOI-sync een naam-conflict detecteert tussen een handmatige rij en
een nieuwe TOOI-rij komt er een PendingReconciliation. Deze endpoints
laten een super_admin (of org:manage) de duplicaten oplossen.

GET /api/admin/reconciliation - lijst open conflicten
POST /api/admin/reconciliation/{id}/merge - merge handmatige rij in TOOI-rij
POST /api/admin/reconciliation/{id}/ignore - markeer als 'no merge'
POST /api/admin/reconciliation/manual-merge - ad-hoc merge van twee eenheden
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import (
    PermissionContext,
    get_permission_context,
    require_system_permission,
)
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.pending_reconciliation import PendingReconciliation
from bouwmeester.services.merge_organisatie_eenheden import MergeResult, merge_into

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/reconciliation", tags=["reconciliation"])


class ReconciliationResponse(BaseModel):
    id: uuid.UUID
    resource_type: str
    handmatige_id: uuid.UUID
    handmatige_naam: str | None
    handmatige_afkorting: str | None
    kandidaat_id: uuid.UUID | None
    kandidaat_naam: str | None
    kandidaat_bron: str
    kandidaat_tooi_uri: str | None
    match_reden: str
    details: dict[str, Any] | None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ManualMergeRequest(BaseModel):
    # source verdwijnt, target blijft. De UI stelt standaard de gesyncte
    # rij als target voor (officiële naam + tooi_uri blijven, alle FK's
    # van de handmatige rij verhuizen mee), maar de admin mag omkeren.
    source_id: uuid.UUID
    target_id: uuid.UUID


def _merge_response(target: OrganisatieEenheid, result: MergeResult) -> dict:
    """The answer to a merge, with the trust it took away from the source."""
    return {
        "status": "merged",
        "doelrij_id": str(target.id),
        "rewritten": result.rewritten,
        "eigenaarsrechten_verwijderd": result.owner_grants_removed,
        "plaatsingen_onbevestigd": result.placements_unconfirmed,
    }


@router.get("", response_model=list[ReconciliationResponse])
async def list_reconciliations(
    status: str = "open",
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_system_permission("org:manage")),
) -> list[ReconciliationResponse]:
    """Open conflict-lijst. Pass status=resolved/ignored om historisch te zien."""
    rows = (
        (
            await db.execute(
                select(PendingReconciliation)
                .where(PendingReconciliation.status == status)
                .order_by(PendingReconciliation.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    out: list[ReconciliationResponse] = []
    for rec in rows:
        handmatig = await db.get(OrganisatieEenheid, rec.handmatige_id)
        kandidaat = (
            await db.get(OrganisatieEenheid, rec.kandidaat_id)
            if rec.kandidaat_id
            else None
        )
        out.append(
            ReconciliationResponse(
                id=rec.id,
                resource_type=rec.resource_type,
                handmatige_id=rec.handmatige_id,
                handmatige_naam=handmatig.naam if handmatig else None,
                handmatige_afkorting=handmatig.afkorting if handmatig else None,
                kandidaat_id=rec.kandidaat_id,
                kandidaat_naam=kandidaat.naam if kandidaat else None,
                kandidaat_bron=rec.kandidaat_bron,
                kandidaat_tooi_uri=kandidaat.tooi_uri if kandidaat else None,
                match_reden=rec.match_reden,
                details=rec.details,
                status=rec.status,
                created_at=rec.created_at,
            )
        )
    return out


@router.post("/{rec_id}/merge", summary="Merge handmatige rij in TOOI-kandidaat")
async def merge_reconciliation(
    rec_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
    _perm=Depends(require_system_permission("org:manage")),
) -> dict:
    """Merge: alle referenties (plaatsingen, leads, opdrachten, children,
    permissions, modules, namen, parents, polymorphic resource_id-velden)
    van de handmatige rij gaan over naar de TOOI-rij. Handmatige rij wordt
    verwijderd."""
    # Lock de reconciliation-row zodat twee gelijktijdige admins niet
    # allebei een half-merge proberen. Wachten op de lock duurt typisch
    # milliseconden; de tweede request ziet daarna status='merged' en
    # krijgt 404.
    rec = (
        await db.execute(
            select(PendingReconciliation)
            .where(PendingReconciliation.id == rec_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if rec is None or rec.status != "open":
        raise HTTPException(status_code=404, detail="Reconciliation niet gevonden")
    if rec.resource_type != "organisatie_eenheid":
        raise HTTPException(
            status_code=400, detail="Alleen organisatie_eenheid wordt ondersteund"
        )

    handmatig = await db.get(OrganisatieEenheid, rec.handmatige_id)
    kandidaat = (
        await db.get(OrganisatieEenheid, rec.kandidaat_id) if rec.kandidaat_id else None
    )
    if handmatig is None or kandidaat is None:
        raise HTTPException(
            status_code=410,
            detail="Een van beide rijen bestaat niet meer; reconciliation is stale",
        )

    result = await merge_into(db, source=handmatig, target=kandidaat)

    rec.status = "merged"
    rec.resolved_by = perm_ctx.person_id
    rec.resolved_at = datetime.now()

    await db.commit()
    log.info(
        "Reconciliation %s gemerged in kandidaat %s; FK-rewrites: %s",
        rec_id,
        kandidaat.id,
        result.rewritten,
    )
    return _merge_response(kandidaat, result)


@router.post("/{rec_id}/ignore", summary="Markeer reconciliation als no-merge")
async def ignore_reconciliation(
    rec_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
    _perm=Depends(require_system_permission("org:manage")),
) -> dict:
    """Negeer: beide rijen blijven bestaan."""
    rec = await db.get(PendingReconciliation, rec_id)
    if rec is None or rec.status != "open":
        raise HTTPException(status_code=404, detail="Reconciliation niet gevonden")

    rec.status = "ignored"
    rec.resolved_by = perm_ctx.person_id
    rec.resolved_at = datetime.now()
    await db.commit()
    return {"status": "ignored"}


@router.post("/manual-merge", summary="Ad-hoc merge van twee organisatie-eenheden")
async def manual_merge(
    body: ManualMergeRequest,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
    _perm=Depends(require_system_permission("org:manage")),
) -> dict:
    """Merge twee willekeurige eenheden zonder voorafgaande reconciliation.

    Voor duplicaten die de scan niet vangt (bv. een seed-DG naast een
    organogram-scrape-rij met net andere naam). Alle referenties van
    source verhuizen naar target via dezelfde merge_organisatie_eenheden-
    helper; source wordt daarna verwijderd. Eventuele open reconciliations
    die naar source of target wijzen worden afgesloten zodat de admin geen
    stale conflict-rij overhoudt.
    """
    if body.source_id == body.target_id:
        raise HTTPException(
            status_code=400, detail="source en target zijn dezelfde eenheid"
        )

    source = await db.get(OrganisatieEenheid, body.source_id)
    target = await db.get(OrganisatieEenheid, body.target_id)
    if source is None or target is None:
        raise HTTPException(
            status_code=404, detail="source of target eenheid bestaat niet"
        )
    # Een synthetische rij is een container ('ZBO's en agentschappen',
    # 'Marktpartijen en overige'), geen echte eenheid. FK's daarheen
    # verhuizen is vrijwel altijd fout.
    if target.bron == "synthetisch":
        raise HTTPException(
            status_code=400,
            detail="target is een synthetische groep, geen echte eenheid",
        )

    result = await merge_into(db, source=source, target=target)

    # Sluit open reconciliations die nu zinloos zijn: source is verwijderd
    # en al zijn FK's (ook PendingReconciliation.handmatige_id/kandidaat_id)
    # zijn naar target herschreven. Een open conflict tussen target en
    # zichzelf of een al-opgeloste source heeft geen betekenis meer.
    ids = [body.source_id, body.target_id]
    stale = (
        (
            await db.execute(
                select(PendingReconciliation).where(
                    PendingReconciliation.status == "open",
                    or_(
                        PendingReconciliation.handmatige_id.in_(ids),
                        PendingReconciliation.kandidaat_id.in_(ids),
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    for rec in stale:
        rec.status = "merged"
        rec.resolved_by = perm_ctx.person_id
        rec.resolved_at = datetime.now()

    await db.commit()
    log.info(
        "Manual merge: %s '%s' -> %s '%s'; FK-rewrites: %s",
        source.id,
        source.naam,
        target.id,
        target.naam,
        result.rewritten,
    )
    return _merge_response(target, result)
