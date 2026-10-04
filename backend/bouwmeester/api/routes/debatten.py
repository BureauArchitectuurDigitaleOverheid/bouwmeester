"""Debates: which meetings are coming, and setting up a channel for one.

The second way in next to the button under a convocatie in Mattermost. A
debate that never came by as an alert has no post to press a button under;
here any upcoming meeting can be started.
"""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import require_permission
from bouwmeester.models.debat_sessie import DebatSessie
from bouwmeester.repositories.mattermost_user import MattermostUserRepository
from bouwmeester.schema.debat import (
    AankomendDebat,
    AankomendeDebattenResponse,
    DebatKanaal,
    DebatStartRequest,
    DebatStartResponse,
    DebatTeam,
)
from bouwmeester.services.debat_kanaal_service import (
    DebatKanaalService,
    StartOutcome,
    activiteit_url,
)
from bouwmeester.services.mattermost_service import (
    PERMISSION_CREATE_PUBLIC_CHANNEL,
    MattermostService,
    MattermostUnavailableError,
)
from bouwmeester.services.tk_activiteit import TkApiError, list_upcoming

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/debatten", tags=["debatten"])

_TK_TIMEOUT = 20.0


def _channel_url(base_url: str, slug: str | None, channel_name: str) -> str | None:
    if not base_url or not slug:
        return None
    return f"{base_url}/{slug}/channels/{channel_name}"


async def _teams(
    mattermost: MattermostService,
) -> tuple[list[DebatTeam], dict[str, str], str | None]:
    """The bot's teams, their url names, and a message if that failed."""
    try:
        if not await mattermost.is_enabled():
            return [], {}, "Mattermost staat niet aan."
        permissions = await mattermost.team_permissions()
        names = await mattermost.team_namen()
        slugs = await mattermost.team_slugs()
    except (MattermostUnavailableError, ValueError):
        logger.warning("Teams van de bot niet op te vragen", exc_info=True)
        return [], {}, "Mattermost is nu niet bereikbaar."
    if not permissions:
        return [], slugs, "De bot is van geen enkel Mattermost-team lid."
    teams = [
        DebatTeam(
            team_id=team_id,
            team_name=names.get(team_id) or None,
            can_create_channel=PERMISSION_CREATE_PUBLIC_CHANNEL in granted,
        )
        for team_id, granted in permissions.items()
    ]
    teams.sort(key=lambda team: (team.team_name or "").lower())
    return teams, slugs, None


@router.get("/aankomend", response_model=AankomendeDebattenResponse)
async def list_aankomende_debatten(
    dagen: int = Query(21, ge=1, le=60),
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("parlementair:read")),
) -> AankomendeDebattenResponse:
    """The meetings of the coming weeks, with the channel if there is one.

    The agenda of the Tweede Kamer is the same for everyone, so this is
    not filtered on organisation.
    """
    try:
        async with httpx.AsyncClient(timeout=_TK_TIMEOUT) as client:
            activiteiten = await list_upcoming(client, days=dagen)
    except TkApiError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="De agenda van de Tweede Kamer is nu niet op te halen.",
        ) from exc

    mattermost = MattermostService(db)
    try:
        teams, slugs, melding = await _teams(mattermost)
        base_url = await mattermost.base_url()
    finally:
        await mattermost.close()

    kanalen: dict[str, list[DebatKanaal]] = {}
    ids = [a.id for a in activiteiten]
    if ids:
        stmt = select(
            DebatSessie.activiteit_id, DebatSessie.team_id, DebatSessie.channel_name
        ).where(
            DebatSessie.activiteit_id.in_(ids), DebatSessie.channel_name.is_not(None)
        )
        for activiteit_id, team_id, channel_name in (await db.execute(stmt)).all():
            kanalen.setdefault(activiteit_id, []).append(
                DebatKanaal(
                    team_id=team_id,
                    channel_name=channel_name,
                    channel_url=_channel_url(
                        base_url, slugs.get(team_id), channel_name
                    ),
                )
            )

    return AankomendeDebattenResponse(
        debatten=[
            AankomendDebat(
                activiteit_id=a.id,
                nummer=a.nummer,
                soort=a.soort,
                onderwerp=a.onderwerp,
                aanvang=a.aanvang,
                einde=a.einde,
                commissie=a.commissie,
                agenda_url=activiteit_url(a.nummer) if a.nummer else None,
                kanalen=kanalen.get(a.id, []),
            )
            for a in activiteiten
        ],
        teams=teams,
        mattermost_melding=melding,
    )


@router.post("/start", response_model=DebatStartResponse)
async def start_debat(
    body: DebatStartRequest,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("parlementair:review")),
) -> DebatStartResponse:
    """Set up a channel for one meeting, in one of the bot's teams.

    Answers 200 also when no channel was made: a cancelled meeting or a
    missing Mattermost permission is an outcome with a reason to show, not
    an error in the request.
    """
    mattermost = MattermostService(db)
    try:
        if not await mattermost.is_enabled():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Mattermost staat niet aan.",
            )
        # The team comes from the browser. Only a team the bot is in is a
        # team it may create a channel in on someone's behalf.
        try:
            permissions = await mattermost.team_permissions()
        except (MattermostUnavailableError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Mattermost is nu niet bereikbaar.",
            ) from exc
        if body.team_id not in permissions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="De bot is geen lid van dit team.",
            )

        mattermost_user_id = None
        if current_user is not None:
            mapping = await MattermostUserRepository(db).get_by_person_id(
                current_user.id
            )
            mattermost_user_id = mapping.mattermost_user_id if mapping else None

        result = await DebatKanaalService(db, mattermost).start_in_team(
            activiteit_id=str(body.activiteit_id),
            team_id=body.team_id,
            mattermost_user_id=mattermost_user_id,
        )

        kanaal = None
        if result.channel_name:
            slugs = await mattermost.team_slugs()
            kanaal = DebatKanaal(
                team_id=body.team_id,
                channel_name=result.channel_name,
                channel_url=_channel_url(
                    await mattermost.base_url(),
                    slugs.get(body.team_id),
                    result.channel_name,
                ),
            )
    finally:
        await mattermost.close()

    failed = result.outcome in (StartOutcome.REFUSED, StartOutcome.FAILED)
    return DebatStartResponse(
        outcome=result.outcome.value,
        melding=result.message if failed else None,
        kanaal=kanaal,
    )
