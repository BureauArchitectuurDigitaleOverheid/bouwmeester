"""API routes for org placement requests (onboarding)."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.core.org_context import OrgContext, get_org_context
from bouwmeester.models.org_placement_request import OrgPlacementRequest
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.schema.org_placement import (
    OrgPlacementRequestCreate,
    OrgPlacementRequestResponse,
)

router = APIRouter(prefix="/org-placements", tags=["org-placements"])


def _to_response(req: OrgPlacementRequest) -> OrgPlacementRequestResponse:
    return OrgPlacementRequestResponse(
        id=req.id,
        person_id=req.person_id,
        person_naam=req.person.naam if req.person else "",
        organisatie_eenheid_id=req.organisatie_eenheid_id,
        eenheid_naam=req.organisatie_eenheid.naam if req.organisatie_eenheid else "",
        status=req.status,
        requested_at=req.requested_at,
        decided_at=req.decided_at,
        decided_by=req.decided_by,
    )


def _load_options():
    return [
        selectinload(OrgPlacementRequest.person),
        selectinload(OrgPlacementRequest.organisatie_eenheid),
    ]


@router.post(
    "/request",
    response_model=OrgPlacementRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_placement(
    data: OrgPlacementRequestCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> OrgPlacementRequestResponse:
    """Submit a placement request for the current user."""
    if current_user is None:
        raise HTTPException(status_code=401, detail="Inloggen vereist")

    req = OrgPlacementRequest(
        person_id=current_user.id,
        organisatie_eenheid_id=data.organisatie_eenheid_id,
    )
    db.add(req)
    await db.flush()
    await db.refresh(req, attribute_names=["person", "organisatie_eenheid"])
    return _to_response(req)


async def _get_managed_eenheid_ids(db: AsyncSession, person_id: UUID) -> list[UUID]:
    """Return eenheid IDs where the person is the manager."""
    stmt = select(OrganisatieEenheid.id).where(
        OrganisatieEenheid.manager_id == person_id,
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/pending", response_model=list[OrgPlacementRequestResponse])
async def list_pending(
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(get_org_context),
) -> list[OrgPlacementRequestResponse]:
    """List pending placement requests (for managers of the requested eenheid)."""
    stmt = (
        select(OrgPlacementRequest)
        .where(OrgPlacementRequest.status == "pending")
        .options(*_load_options())
        .order_by(OrgPlacementRequest.requested_at.desc())
    )
    # Non-admins only see requests for eenheden they manage
    if not org_ctx.is_admin and current_user is not None:
        managed_ids = await _get_managed_eenheid_ids(db, current_user.id)
        stmt = stmt.where(OrgPlacementRequest.organisatie_eenheid_id.in_(managed_ids))
    elif not org_ctx.is_admin:
        # Unauthenticated users see nothing
        return []
    result = await db.execute(stmt)
    requests = list(result.scalars().all())
    return [_to_response(r) for r in requests]


@router.post("/{id}/approve", response_model=OrgPlacementRequestResponse)
async def approve_placement(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(get_org_context),
) -> OrgPlacementRequestResponse:
    """Approve a placement request, creating a PersonOrganisatieEenheid record."""
    stmt = (
        select(OrgPlacementRequest)
        .where(OrgPlacementRequest.id == id)
        .options(*_load_options())
    )
    result = await db.execute(stmt)
    req = result.scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=404, detail="Verzoek niet gevonden")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail="Verzoek is al afgehandeld")

    # Only admins or managers of the requested eenheid may approve
    if not org_ctx.is_admin:
        if current_user is None:
            raise HTTPException(status_code=401, detail="Inloggen vereist")
        managed_ids = await _get_managed_eenheid_ids(db, current_user.id)
        if req.organisatie_eenheid_id not in managed_ids:
            raise HTTPException(status_code=403, detail="Geen bevoegdheid")

    req.status = "approved"
    req.decided_at = datetime.now(UTC)
    req.decided_by = current_user.id if current_user else None

    # Create the actual placement
    from datetime import date

    placement = PersonOrganisatieEenheid(
        person_id=req.person_id,
        organisatie_eenheid_id=req.organisatie_eenheid_id,
        start_datum=date.today(),
    )
    db.add(placement)
    await db.flush()

    return _to_response(req)


@router.post("/{id}/deny", response_model=OrgPlacementRequestResponse)
async def deny_placement(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(get_org_context),
) -> OrgPlacementRequestResponse:
    """Deny a placement request."""
    stmt = (
        select(OrgPlacementRequest)
        .where(OrgPlacementRequest.id == id)
        .options(*_load_options())
    )
    result = await db.execute(stmt)
    req = result.scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=404, detail="Verzoek niet gevonden")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail="Verzoek is al afgehandeld")

    # Only admins or managers of the requested eenheid may deny
    if not org_ctx.is_admin:
        if current_user is None:
            raise HTTPException(status_code=401, detail="Inloggen vereist")
        managed_ids = await _get_managed_eenheid_ids(db, current_user.id)
        if req.organisatie_eenheid_id not in managed_ids:
            raise HTTPException(status_code=403, detail="Geen bevoegdheid")

    req.status = "denied"
    req.decided_at = datetime.now(UTC)
    req.decided_by = current_user.id if current_user else None
    await db.flush()

    return _to_response(req)
