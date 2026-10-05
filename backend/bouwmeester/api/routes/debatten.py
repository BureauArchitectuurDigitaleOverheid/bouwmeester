"""Debates: which meetings are coming, and setting up a channel for one.

The second way in next to the button under a convocatie in Mattermost. A
debate that never came by as an alert has no post to press a button under;
here any upcoming meeting can be started.
"""

import logging
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import require_permission
from bouwmeester.models.debat_sessie import DebatSessie
from bouwmeester.models.person import Person
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

# How many recorded channels are checked against Mattermost per request. A
# three-week window holds a handful; this only bounds a pathological case.
_MAX_CHANNEL_CHECKS = 20


def _browser_base(url: str) -> str:
    """The Mattermost URL, if it is one a browser can open.

    `MATTERMOST_URL` is the address the backend calls, and in a compose
    setup that is a service name like `http://mattermost:8065`. A link
    built from that looks fine and goes nowhere, so then there is no link.
    """
    host = urlparse(url).hostname or ""
    return url.rstrip("/") if "." in host else ""


def _channel_url(base_url: str, slug: str | None, channel_name: str) -> str | None:
    if not base_url or not slug:
        return None
    return f"{base_url}/{slug}/channels/{channel_name}"


@dataclass
class _Teams:
    """What the current person may do in Mattermost through this page."""

    teams: list[DebatTeam] = field(default_factory=list)
    slugs: dict[str, str] = field(default_factory=dict)
    # Why there are no teams, to show as is.
    melding: str | None = None
    # Mattermost could not be asked: not a "no", so not a 403.
    unavailable: bool = False
    mattermost_user_id: str | None = None

    @property
    def team_ids(self) -> set[str]:
        return {team.team_id for team in self.teams}


async def _teams_for(
    mattermost: MattermostService, db: AsyncSession, person: Person | None
) -> _Teams:
    """The teams the bot is in, for a person with a linked account.

    The linked account is what the channel is made on behalf of: that
    person is added to it. Whether the person is a member of the team is
    deliberately not a condition. It was, and in production the membership
    check answered "no" for someone who is in the team, which took the
    button away from exactly the people it is for. Until it is clear why,
    the answer is only logged when a channel is started (see
    `_log_membership`).

    Without a person (local development without a login) there is no
    account to add, and every team of the bot counts as well.
    """
    try:
        if not await mattermost.is_enabled():
            return _Teams(melding="Mattermost staat niet aan.", unavailable=True)
        permissions = await mattermost.team_permissions()
        info = await mattermost.teams_info()

        result = _Teams(slugs={tid: i["slug"] for tid, i in info.items()})
        if person is not None:
            mapping = await MattermostUserRepository(db).get_by_person_id(person.id)
            if mapping is None:
                result.melding = (
                    "Koppel je Mattermost-account bij Instellingen om kanalen "
                    "op te zetten."
                )
                return result
            result.mattermost_user_id = mapping.mattermost_user_id
    except (MattermostUnavailableError, ValueError):
        logger.warning("Teams van de bot niet op te vragen", exc_info=True)
        return _Teams(melding="Mattermost is nu niet bereikbaar.", unavailable=True)

    if not permissions:
        result.melding = "De bot is van geen enkel Mattermost-team lid."
    result.teams = sorted(
        (
            DebatTeam(
                team_id=team_id,
                team_name=info.get(team_id, {}).get("display_name") or None,
                can_create_channel=PERMISSION_CREATE_PUBLIC_CHANNEL
                in permissions[team_id],
            )
            for team_id in permissions
        ),
        key=lambda team: (team.team_name or "").lower(),
    )
    return result


async def _log_membership(
    mattermost: MattermostService, team_id: str, mattermost_user_id: str | None
) -> None:
    """Write down what Mattermost says about this person and this team.

    Diagnosis only; it decides nothing and must never stand in the way.
    The membership check said "not a member" in production for someone
    who is one, and it cannot be reproduced against a local Mattermost.
    One line per start shows what the real server answers.
    """
    if not mattermost_user_id:
        return
    try:
        answer = await mattermost.describe_team_membership(team_id, mattermost_user_id)
    except Exception as exc:
        answer = f"niet op te vragen ({type(exc).__name__})"
    # At warning level on purpose. The API process configures no logging,
    # so anything below warning is dropped and this line would never be
    # seen where it is needed.
    logger.warning(
        "Teamlidmaatschap volgens Mattermost: account %s in team %s: %s",
        mattermost_user_id,
        team_id,
        answer,
    )


@router.get("/aankomend", response_model=AankomendeDebattenResponse)
async def list_aankomende_debatten(
    current_user: OptionalUser,
    dagen: int = Query(21, ge=1, le=60),
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("parlementair:read")),
) -> AankomendeDebattenResponse:
    """The meetings of the coming weeks, with the channel if there is one.

    The agenda of the Tweede Kamer is the same for everyone, so this is
    not filtered on organisation. Teams and channels are those of the bot,
    for whoever has a linked Mattermost account.
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
        allowed = await _teams_for(mattermost, db, current_user)
        base_url = _browser_base(await mattermost.base_url())

        kanalen: dict[str, list[DebatKanaal]] = {}
        ids = [a.id for a in activiteiten]
        if ids and allowed.team_ids:
            stmt = select(
                DebatSessie.activiteit_id,
                DebatSessie.team_id,
                DebatSessie.channel_id,
                DebatSessie.channel_name,
            ).where(
                DebatSessie.activiteit_id.in_(ids),
                DebatSessie.team_id.in_(allowed.team_ids),
                DebatSessie.channel_id.is_not(None),
                DebatSessie.channel_name.is_not(None),
            )
            rows = (await db.execute(stmt)).all()
            for index, (activiteit_id, team_id, channel_id, name) in enumerate(rows):
                # A channel someone archived is not shown as a channel. The
                # row then offers the button again, and pressing it sets up
                # a new one. Showing a link to it instead would leave no
                # way to get there.
                if index < _MAX_CHANNEL_CHECKS and await mattermost.channel_is_gone(
                    channel_id
                ):
                    continue
                kanalen.setdefault(activiteit_id, []).append(
                    DebatKanaal(
                        team_id=team_id,
                        channel_name=name,
                        channel_url=_channel_url(
                            base_url, allowed.slugs.get(team_id), name
                        ),
                    )
                )
    finally:
        await mattermost.close()

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
        teams=allowed.teams,
        mattermost_melding=allowed.melding,
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
        allowed = await _teams_for(mattermost, db, current_user)
        # The team comes from the browser, so it is checked against the
        # same list the page was given.
        if allowed.unavailable:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=allowed.melding,
            )
        if body.team_id not in allowed.team_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=allowed.melding
                or "Je kunt in dit team geen kanaal laten opzetten.",
            )

        result = await DebatKanaalService(db, mattermost).start_in_team(
            activiteit_id=str(body.activiteit_id),
            team_id=body.team_id,
            mattermost_user_id=allowed.mattermost_user_id,
        )
        # After the start, so a slow Mattermost delays the diagnosis and
        # not the channel.
        await _log_membership(mattermost, body.team_id, allowed.mattermost_user_id)

        kanaal = None
        if result.channel_name:
            kanaal = DebatKanaal(
                team_id=body.team_id,
                channel_name=result.channel_name,
                channel_url=_channel_url(
                    _browser_base(await mattermost.base_url()),
                    allowed.slugs.get(body.team_id),
                    result.channel_name,
                ),
            )
    finally:
        await mattermost.close()

    failed = result.outcome in (StartOutcome.REFUSED, StartOutcome.FAILED)
    return DebatStartResponse(
        outcome=result.outcome.value,
        # The texts are written for Mattermost; a toast does not render
        # backticks.
        melding=result.message.replace("`", "") if failed else None,
        kanaal=kanaal,
    )
