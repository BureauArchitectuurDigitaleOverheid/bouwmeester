"""API routes for org placement requests (onboarding)."""

from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.core.org_context import OrgContext, get_org_context
from bouwmeester.models.org_placement_request import OrgPlacementRequest
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.role import PersonRole
from bouwmeester.schema.notification import NotificationCreate
from bouwmeester.schema.org_placement import (
    OrgPlacementRequestCreate,
    OrgPlacementRequestResponse,
    OrgPlacementRequestUpdate,
)
from bouwmeester.services.notification_service import NotificationService

router = APIRouter(prefix="/org-placements", tags=["org-placements"])


def _to_response(req: OrgPlacementRequest) -> OrgPlacementRequestResponse:
    return OrgPlacementRequestResponse(
        id=req.id,
        person_id=req.person_id,
        person_naam=req.person.naam if req.person else "",
        organisatie_eenheid_id=req.organisatie_eenheid_id,
        eenheid_naam=req.organisatie_eenheid.naam if req.organisatie_eenheid else "",
        dienstverband=req.dienstverband,
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


async def _get_managed_eenheid_ids(db: AsyncSession, person_id: UUID) -> list[UUID]:
    """Return eenheid IDs where the person has a unit_manager role assignment."""
    today = date.today()
    stmt = select(PersonRole.organisatie_eenheid_id).where(
        PersonRole.person_id == person_id,
        PersonRole.role_id == "unit_manager",
        PersonRole.organisatie_eenheid_id.isnot(None),
        PersonRole.start_datum <= today,
        (PersonRole.eind_datum.is_(None)) | (PersonRole.eind_datum >= today),
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


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

    # Prevent duplicate pending requests for the same eenheid
    existing_stmt = select(OrgPlacementRequest).where(
        OrgPlacementRequest.person_id == current_user.id,
        OrgPlacementRequest.organisatie_eenheid_id == data.organisatie_eenheid_id,
        OrgPlacementRequest.status == "pending",
    )
    existing = (await db.execute(existing_stmt)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Er staat al een verzoek open voor deze eenheid",
        )

    req = OrgPlacementRequest(
        person_id=current_user.id,
        organisatie_eenheid_id=data.organisatie_eenheid_id,
        dienstverband=data.dienstverband,
    )
    db.add(req)
    await db.flush()
    await db.refresh(req, attribute_names=["person", "organisatie_eenheid"])

    # Notify the team manager and admins
    notif_svc = NotificationService(db)
    eenheid_naam = req.organisatie_eenheid.naam if req.organisatie_eenheid else ""
    person_naam = req.person.naam if req.person else ""
    await notif_svc.notify_placement_request(
        person_naam=person_naam,
        eenheid_id=req.organisatie_eenheid_id,
        eenheid_naam=eenheid_naam,
    )

    return _to_response(req)


@router.get("/my-requests", response_model=list[OrgPlacementRequestResponse])
async def my_requests(
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> list[OrgPlacementRequestResponse]:
    """List the current user's placement requests (all statuses)."""
    if current_user is None:
        raise HTTPException(status_code=401, detail="Inloggen vereist")
    stmt = (
        select(OrgPlacementRequest)
        .where(OrgPlacementRequest.person_id == current_user.id)
        .options(*_load_options())
        .order_by(OrgPlacementRequest.requested_at.desc())
    )
    result = await db.execute(stmt)
    return [_to_response(r) for r in result.scalars().all()]


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


@router.patch("/{id}", response_model=OrgPlacementRequestResponse)
async def update_placement_request(
    id: UUID,
    data: OrgPlacementRequestUpdate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(get_org_context),
) -> OrgPlacementRequestResponse:
    """Update the target eenheid of a pending placement request."""
    from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid

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

    # Validate target eenheid exists
    target = await db.get(OrganisatieEenheid, data.organisatie_eenheid_id)
    if target is None:
        raise HTTPException(status_code=400, detail="Eenheid niet gevonden")

    # Only admins or managers of the current eenheid may update
    if not org_ctx.is_admin:
        if current_user is None:
            raise HTTPException(status_code=401, detail="Inloggen vereist")
        managed_ids = await _get_managed_eenheid_ids(db, current_user.id)
        if req.organisatie_eenheid_id not in managed_ids:
            raise HTTPException(status_code=403, detail="Geen bevoegdheid")

    req.organisatie_eenheid_id = data.organisatie_eenheid_id
    await db.flush()
    await db.refresh(req, attribute_names=["organisatie_eenheid"])

    # If the changer doesn't manage the new eenheid, notify its manager
    should_notify = True
    if not org_ctx.is_admin and current_user is not None:
        managed_ids = await _get_managed_eenheid_ids(db, current_user.id)
        if data.organisatie_eenheid_id in managed_ids:
            should_notify = False
    elif org_ctx.is_admin:
        should_notify = False

    if should_notify:
        notif_svc = NotificationService(db)
        person_naam = req.person.naam if req.person else ""
        eenheid_naam = target.naam
        await notif_svc.notify_placement_request(
            person_naam=person_naam,
            eenheid_id=data.organisatie_eenheid_id,
            eenheid_naam=eenheid_naam,
        )

    return _to_response(req)


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
    placement = PersonOrganisatieEenheid(
        person_id=req.person_id,
        organisatie_eenheid_id=req.organisatie_eenheid_id,
        dienstverband=req.dienstverband,
        start_datum=date.today(),
    )
    db.add(placement)
    await db.flush()

    # Notify the requester
    eenheid_naam = req.organisatie_eenheid.naam if req.organisatie_eenheid else ""
    notif_svc = NotificationService(db)
    await notif_svc.send(
        NotificationCreate(
            person_id=req.person_id,
            type="placement_approved",
            title=f"Toegevoegd aan: {eenheid_naam}",
            message=f"Je bent toegevoegd aan '{eenheid_naam}'.",
        )
    )

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

    # Notify the requester
    eenheid_naam = req.organisatie_eenheid.naam if req.organisatie_eenheid else ""
    notif_svc = NotificationService(db)
    await notif_svc.send(
        NotificationCreate(
            person_id=req.person_id,
            type="placement_denied",
            title=f"Verzoek afgewezen: {eenheid_naam}",
            message=(
                f"Je verzoek om toegevoegd te worden aan '{eenheid_naam}' "
                f"is afgewezen. Je kunt een nieuw verzoek indienen."
            ),
        )
    )

    return _to_response(req)
