"""Debates announced for an initiatief: list them, announce one, take one off.

Whoever may see the initiatief may see the list. Announcing and taking off
need contributor: an announcement makes the bot post in every channel of
the initiatief, and that is not something a viewer does. A search term on
the same tab is open to viewers because it posts nothing by itself.
"""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.routes.initiatief import _require_access
from bouwmeester.api.routes.parlementair_abonnement import (
    _require_initiatief_toegang,
)
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.core.initiatief_context import (
    InitiatiefContext,
    get_initiatief_context,
)
from bouwmeester.core.permissions import PermissionContext, get_permission_context
from bouwmeester.models.debat_aankondiging import DebatAankondiging
from bouwmeester.repositories.initiatief import InitiatiefRepository
from bouwmeester.schema.debat import (
    DebatAankondigingCreate,
    DebatAankondigingResponse,
)
from bouwmeester.services.activity_service import log_activity
from bouwmeester.services.debat_aankondiging_service import (
    AlreadyAnnouncedError,
    AnnounceRefusedError,
    DebatAankondigingService,
)
from bouwmeester.services.debat_kanaal_service import activiteit_url
from bouwmeester.services.tk_activiteit import TkApiError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/initiatieven", tags=["debat-aankondiging"])

# How long a debate stays on the list after it started. Long enough to see
# today what was on yesterday, short enough that the list is about what is
# coming.
_KEPT_AFTER_START = timedelta(days=1)


def _response(
    row: DebatAankondiging, gepost_in: int | None = None
) -> DebatAankondigingResponse:
    return DebatAankondigingResponse(
        id=row.id,
        activiteit_id=row.activiteit_id,
        nummer=row.activiteit_nummer,
        soort=row.soort,
        onderwerp=row.onderwerp,
        commissie=row.commissie,
        aanvang=row.aanvang,
        einde=row.einde,
        agenda_url=(
            activiteit_url(row.activiteit_nummer) if row.activiteit_nummer else None
        ),
        stand=row.stand,
        created_at=row.created_at,
        gepost_in=gepost_in,
    )


@router.get(
    "/{initiatief_id}/debatten",
    response_model=list[DebatAankondigingResponse],
)
async def list_debat_aankondigingen(
    initiatief_id: UUID,
    db: AsyncSession = Depends(get_db),
    ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> list[DebatAankondigingResponse]:
    """The debates announced for this initiatief that are still to come."""
    await _require_initiatief_toegang(db, ctx, initiatief_id)

    stmt = (
        select(DebatAankondiging)
        .where(
            DebatAankondiging.initiatief_id == initiatief_id,
            or_(
                DebatAankondiging.aanvang.is_(None),
                DebatAankondiging.aanvang >= datetime.now(UTC) - _KEPT_AFTER_START,
            ),
        )
        .order_by(DebatAankondiging.aanvang.asc().nulls_last(), DebatAankondiging.id)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_response(row) for row in rows]


@router.post(
    "/{initiatief_id}/debatten",
    response_model=DebatAankondigingResponse,
    status_code=201,
)
async def create_debat_aankondiging(
    initiatief_id: UUID,
    payload: DebatAankondigingCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    ctx: InitiatiefContext = Depends(get_initiatief_context),
    perm_ctx: PermissionContext = Depends(get_permission_context),
    actor_id: UUID | None = None,
) -> DebatAankondigingResponse:
    """Announce a debate in the channels of this initiatief."""
    # First whether it may be seen at all, so an initiatief someone has no
    # business with answers 404 and not 403.
    initiatief = await _require_initiatief_toegang(db, ctx, initiatief_id)
    await _require_access(
        InitiatiefRepository(db), initiatief_id, current_user, perm_ctx, "contributor"
    )

    service = DebatAankondigingService(db)
    try:
        result = await service.announce(
            initiatief,
            str(payload.activiteit_id),
            person_id=current_user.id if current_user else None,
            door=current_user.naam if current_user else None,
        )
    except TkApiError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="De agenda van de Tweede Kamer is nu niet op te halen.",
        ) from exc
    except AnnounceRefusedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AlreadyAnnouncedError as exc:
        raise HTTPException(
            status_code=409, detail="Dit debat is al aangekondigd."
        ) from exc
    finally:
        await service.close()

    await log_activity(
        db,
        current_user,
        actor_id,
        "debat.aangekondigd",
        details={
            "initiatief_id": str(initiatief_id),
            "activiteit_id": result.row.activiteit_id,
            "onderwerp": result.row.onderwerp,
        },
    )
    await db.commit()
    await db.refresh(result.row)
    return _response(result.row, gepost_in=result.gepost_in)


@router.delete("/{initiatief_id}/debatten/{aankondiging_id}", status_code=204)
async def delete_debat_aankondiging(
    initiatief_id: UUID,
    aankondiging_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    ctx: InitiatiefContext = Depends(get_initiatief_context),
    perm_ctx: PermissionContext = Depends(get_permission_context),
    actor_id: UUID | None = None,
) -> Response:
    """Take a debate off the list, so no reminder follows.

    What was posted stays where it is: the channel is a record of what was
    said, and a message that vanishes is harder to explain than one that
    was not followed up.
    """
    await _require_initiatief_toegang(db, ctx, initiatief_id)
    await _require_access(
        InitiatiefRepository(db), initiatief_id, current_user, perm_ctx, "contributor"
    )

    row = await db.get(DebatAankondiging, aankondiging_id)
    if row is None or row.initiatief_id != initiatief_id:
        raise HTTPException(status_code=404, detail="Aankondiging niet gevonden")

    await log_activity(
        db,
        current_user,
        actor_id,
        "debat.aankondiging_verwijderd",
        details={
            "initiatief_id": str(initiatief_id),
            "activiteit_id": row.activiteit_id,
            "onderwerp": row.onderwerp,
        },
    )
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)
