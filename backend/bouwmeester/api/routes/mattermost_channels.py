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

from bouwmeester.api.deps import on_initiatief, on_lead, require_found
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.authz import requires
from bouwmeester.core.database import get_db
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
from bouwmeester.services.mattermost_slash_service import channel_link_refusal

logger = logging.getLogger(__name__)

router = APIRouter(tags=["mattermost-channels"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Initiatief-scope endpoints
# ---------------------------------------------------------------------------


async def _require_may_link(db, channel_id: str, current_user) -> None:
    """403 when the caller may not link this channel (a private one they are
    not a member of: its posts would be ingested)."""
    refusal = await channel_link_refusal(
        db, channel_id, current_user.id if current_user else None
    )
    if refusal:
        raise HTTPException(status.HTTP_403_FORBIDDEN, refusal)


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
    _authz=Depends(on_initiatief("initiatief:read")),
) -> list[MattermostChannelLinkResponse]:
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
    _authz=Depends(on_initiatief("mattermost_channel_link:create")),
) -> MattermostChannelLinkResponse:
    await _require_may_link(db, data.channel_id, current_user)
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
    _authz=Depends(on_lead("lead:read")),
) -> list[MattermostChannelLinkResponse]:
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
    _authz=Depends(on_lead("mattermost_channel_link:create")),
) -> MattermostChannelLinkResponse:
    await _require_may_link(db, data.channel_id, current_user)
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
    """Zoek MM-kanalen via de bot, private alleen waar de caller lid van is."""
    if not perm_ctx.is_authenticated or perm_ctx.person_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    from bouwmeester.repositories.mattermost_user import MattermostUserRepository
    from bouwmeester.services.mattermost_service import MattermostService

    service = MattermostService(db)
    if not await service.is_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mattermost is niet geconfigureerd",
        )
    mapping = await MattermostUserRepository(db).get_by_person_id(perm_ctx.person_id)
    results = await service.search_channels(
        q, member_user_id=mapping.mattermost_user_id if mapping else None
    )
    return [MattermostChannelSearchResult.model_validate(r) for r in results]


@router.patch(
    "/mattermost-channels/{link_id}",
    response_model=MattermostChannelLinkResponse,
)
async def update_channel_link(
    link_id: UUID,
    data: MattermostChannelLinkUpdate,
    current_user: OptionalUser,
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
    link = require_found(await repo.get(link_id), "Koppeling")

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

    # Switching on what reads the channel's posts (notes, lead suggestions)
    # or reviving the link is linking it anew: the same membership check as
    # creating it, whoever made the link.
    starts_ingest = (
        data.reenable
        or (data.auto_note_enabled and not link.auto_note_enabled)
        or (data.suggest_leads_enabled and not link.suggest_leads_enabled)
    )
    if starts_ingest:
        await _require_may_link(db, link.channel_id, current_user)

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
    link = require_found(await repo.get(link_id), "Koppeling")
    await repo.delete(link)
