"""Mattermost-kanaalkoppelingen aan initiatieven en leads.

Routes:
  GET  /api/initiatieven/{id}/mattermost-channels
  POST /api/initiatieven/{id}/mattermost-channels
  GET  /api/leads/{id}/mattermost-channels
  POST /api/leads/{id}/mattermost-channels
  GET  /api/mattermost-channels/search?q=...
  PATCH /api/mattermost-channels/{link_id}
  DELETE /api/mattermost-channels/{link_id}

Reading the links follows reading the initiatief or lead; managing them is
writing to it (``core.authz`` delegates ``mattermost_channel_link:*`` to
``<scope>:update``).
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.authz import requires
from bouwmeester.core.database import get_db
from bouwmeester.core.initiatief_context import (
    require_initiatief_read,
    require_lead_read,
)
from bouwmeester.core.permissions import PermissionContext, get_permission_context
from bouwmeester.models.mattermost_channel_link import (
    SCOPE_INITIATIEF,
    SCOPE_LEAD,
)
from bouwmeester.repositories.mattermost_channel_link import (
    MattermostChannelLinkRepository,
)
from bouwmeester.schema.mattermost_channel_link import (
    MattermostChannelLinkCreate,
    MattermostChannelLinkResponse,
    MattermostChannelLinkUpdate,
    MattermostChannelSearchResult,
)
from bouwmeester.services.mattermost_service import vul_teamnaam_aan

logger = logging.getLogger(__name__)

router = APIRouter(tags=["mattermost-channels"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Niet gevonden")


# ---------------------------------------------------------------------------
# Initiatief-scope endpoints
# ---------------------------------------------------------------------------


async def _met_teamnaam(db, links: list) -> list[MattermostChannelLinkResponse]:
    """Vul de teamnaam aan, zodat twee gelijknamige kanalen te scheiden zijn.

    De invulling zelf staat in `vul_teamnaam_aan`, want het beheeroverzicht
    toont dezelfde kanalen met een eigen antwoordmodel en hoort niet een
    tweede keer op te halen waarom de naam niet opgeslagen wordt.
    """
    antwoorden = [MattermostChannelLinkResponse.model_validate(x) for x in links]
    return await vul_teamnaam_aan(db, antwoorden)


@router.get(
    "/initiatieven/{initiatief_id}/mattermost-channels",
    response_model=list[MattermostChannelLinkResponse],
)
async def list_initiatief_channels(
    initiatief_id: UUID,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> list[MattermostChannelLinkResponse]:
    await require_initiatief_read(db, perm_ctx, initiatief_id)
    repo = MattermostChannelLinkRepository(db)
    links = await repo.list_for_scope(SCOPE_INITIATIEF, initiatief_id)
    return await _met_teamnaam(db, links)


@router.post(
    "/initiatieven/{initiatief_id}/mattermost-channels",
    response_model=MattermostChannelLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_initiatief_channel(
    initiatief_id: UUID,
    data: MattermostChannelLinkCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _authz=Depends(
        requires(
            "mattermost_channel_link:create", "initiatief", path_param="initiatief_id"
        )
    ),
) -> MattermostChannelLinkResponse:
    repo = MattermostChannelLinkRepository(db)
    existing = await repo.get_by_channel_id(data.channel_id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dit kanaal is al gekoppeld",
        )
    try:
        link = await repo.create(
            channel_id=data.channel_id,
            channel_name=data.channel_name,
            channel_display_name=data.channel_display_name,
            team_id=data.team_id,
            scope_type=SCOPE_INITIATIEF,
            scope_id=initiatief_id,
            auto_note_enabled=data.auto_note_enabled
            if data.auto_note_enabled is not None
            else False,
            suggest_leads_enabled=data.suggest_leads_enabled
            if data.suggest_leads_enabled is not None
            else True,
            # Standaard uit: een kanaal dat voor leads wordt gekoppeld
            # hoort niet ongevraagd elk kamerstuk te krijgen. Aanzetten
            # gebeurt bewust, met het vinkje in het beheerpaneel.
            parlementaire_alerts_enabled=data.parlementaire_alerts_enabled
            if data.parlementaire_alerts_enabled is not None
            else False,
            # Idem voor de vakpers, en apart aan te zetten: dat zijn
            # andere stukken voor een ander gesprek.
            nieuws_alerts_enabled=data.nieuws_alerts_enabled
            if data.nieuws_alerts_enabled is not None
            else False,
            created_by_id=current_user.id if current_user else None,
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dit kanaal is al gekoppeld",
        )
    return MattermostChannelLinkResponse.model_validate(link)


# ---------------------------------------------------------------------------
# Lead-scope endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/leads/{lead_id}/mattermost-channels",
    response_model=list[MattermostChannelLinkResponse],
)
async def list_lead_channels(
    lead_id: UUID,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> list[MattermostChannelLinkResponse]:
    await require_lead_read(db, perm_ctx, lead_id)
    repo = MattermostChannelLinkRepository(db)
    links = await repo.list_for_scope(SCOPE_LEAD, lead_id)
    return await _met_teamnaam(db, links)


@router.post(
    "/leads/{lead_id}/mattermost-channels",
    response_model=MattermostChannelLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_lead_channel(
    lead_id: UUID,
    data: MattermostChannelLinkCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _authz=Depends(
        requires("mattermost_channel_link:create", "lead", path_param="lead_id")
    ),
) -> MattermostChannelLinkResponse:
    repo = MattermostChannelLinkRepository(db)
    existing = await repo.get_by_channel_id(data.channel_id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dit kanaal is al gekoppeld",
        )
    try:
        link = await repo.create(
            channel_id=data.channel_id,
            channel_name=data.channel_name,
            channel_display_name=data.channel_display_name,
            team_id=data.team_id,
            scope_type=SCOPE_LEAD,
            scope_id=lead_id,
            auto_note_enabled=data.auto_note_enabled
            if data.auto_note_enabled is not None
            else True,
            suggest_leads_enabled=data.suggest_leads_enabled
            if data.suggest_leads_enabled is not None
            else False,
            created_by_id=current_user.id if current_user else None,
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dit kanaal is al gekoppeld",
        )
    return MattermostChannelLinkResponse.model_validate(link)


# ---------------------------------------------------------------------------
# Cross-cutting endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/mattermost-channels/search",
    response_model=list[MattermostChannelSearchResult],
)
async def search_channels(
    q: str = Query(..., min_length=2, max_length=64),
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> list[MattermostChannelSearchResult]:
    """Zoek MM-kanalen via de bot. Vereist authenticated user."""
    if not perm_ctx.is_authenticated:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    from bouwmeester.services.mattermost_service import MattermostService

    service = MattermostService(db)
    if not await service.is_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mattermost is niet geconfigureerd",
        )
    results = await service.search_channels(q)
    return [MattermostChannelSearchResult.model_validate(r) for r in results]


@router.patch(
    "/mattermost-channels/{link_id}",
    response_model=MattermostChannelLinkResponse,
)
async def update_channel_link(
    link_id: UUID,
    data: MattermostChannelLinkUpdate,
    db: AsyncSession = Depends(get_db),
    _authz=Depends(
        requires(
            "mattermost_channel_link:update",
            "mattermost_channel_link",
            path_param="link_id",
        )
    ),
) -> MattermostChannelLinkResponse:
    repo = MattermostChannelLinkRepository(db)
    link = await repo.get(link_id)
    if link is None:
        raise _not_found()

    # Reenable mag alleen als de bot daadwerkelijk weer in het kanaal zit
    # — anders zet je `disabled_at=None` op een dode koppeling en raakt de
    # UI uit sync met Mattermost.
    if data.reenable:
        from bouwmeester.services.mattermost_service import (
            MattermostService,
            MattermostUnavailableError,
        )

        service = MattermostService(db)
        try:
            if not await service.is_enabled():
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Mattermost is niet geconfigureerd",
                )
            try:
                is_member = await service.is_bot_member_of_channel(link.channel_id)
            except MattermostUnavailableError:
                # Tijdelijke MM-storing — niet interpreteren als "geen lid".
                # 503 zodat de UI de gebruiker kan vragen het later te
                # proberen, in plaats van ten onrechte 409 te tonen.
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=(
                        "Mattermost is tijdelijk niet bereikbaar. "
                        "Probeer het zo opnieuw."
                    ),
                )
            if not is_member:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Bot is geen lid van dit kanaal. "
                        "Voeg de bot eerst toe in Mattermost en probeer opnieuw."
                    ),
                )
        finally:
            await service.close()

    updated = await repo.update_settings(
        link,
        auto_note_enabled=data.auto_note_enabled,
        suggest_leads_enabled=data.suggest_leads_enabled,
        parlementaire_alerts_enabled=data.parlementaire_alerts_enabled,
        nieuws_alerts_enabled=data.nieuws_alerts_enabled,
        reenable=data.reenable,
    )
    return MattermostChannelLinkResponse.model_validate(updated)


@router.delete(
    "/mattermost-channels/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_channel_link(
    link_id: UUID,
    db: AsyncSession = Depends(get_db),
    _authz=Depends(
        requires(
            "mattermost_channel_link:delete",
            "mattermost_channel_link",
            path_param="link_id",
        )
    ),
) -> None:
    repo = MattermostChannelLinkRepository(db)
    link = await repo.get(link_id)
    if link is None:
        raise _not_found()
    await repo.delete(link)
