"""Admin-endpoints voor pending_reconciliation oplossing.

Wanneer TOOI-sync een naam-conflict detecteert tussen een handmatige rij en
een nieuwe TOOI-rij komt er een PendingReconciliation. Deze endpoints
laten een super_admin (of org:manage) de duplicaten oplossen.

GET /api/admin/reconciliation - lijst open conflicten
POST /api/admin/reconciliation/{id}/merge - merge handmatige rij in TOOI-rij
POST /api/admin/reconciliation/{id}/ignore - markeer als 'no merge'
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import (
    PermissionContext,
    get_permission_context,
    require_permission,
)
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.pending_reconciliation import PendingReconciliation
from bouwmeester.services.merge_organisatie_eenheden import (
    merge_organisatie_eenheden,
)

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


@router.get("", response_model=list[ReconciliationResponse])
async def list_reconciliations(
    status: str = "open",
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("org:manage")),
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
    _perm=Depends(require_permission("org:manage")),
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

    # Vul ontbrekende velden op kandidaat met handmatige data vóór de
    # source-rij wordt verwijderd. afkorting/website/kvk/beschrijving zijn
    # de velden die TOOI niet levert maar handmatig vaak wel.
    if not kandidaat.afkorting and handmatig.afkorting:
        kandidaat.afkorting = handmatig.afkorting
    if not kandidaat.website and handmatig.website:
        kandidaat.website = handmatig.website
    if not kandidaat.kvk_nummer and handmatig.kvk_nummer:
        kandidaat.kvk_nummer = handmatig.kvk_nummer
    if not kandidaat.beschrijving and handmatig.beschrijving:
        kandidaat.beschrijving = handmatig.beschrijving
    await db.flush()

    rewritten = await merge_organisatie_eenheden(db, handmatig.id, kandidaat.id)

    rec.status = "merged"
    rec.resolved_by = perm_ctx.person_id
    rec.resolved_at = datetime.now()

    await db.commit()
    log.info(
        "Reconciliation %s gemerged in kandidaat %s; FK-rewrites: %s",
        rec_id,
        kandidaat.id,
        rewritten,
    )
    return {
        "status": "merged",
        "doelrij_id": str(kandidaat.id),
        "rewritten": rewritten,
    }


@router.post("/{rec_id}/ignore", summary="Markeer reconciliation als no-merge")
async def ignore_reconciliation(
    rec_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
    _perm=Depends(require_permission("org:manage")),
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
