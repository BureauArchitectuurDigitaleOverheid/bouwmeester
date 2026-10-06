"""Debates: which meetings are coming, and setting up a channel for one.

The second way in next to the button under a convocatie in Mattermost. A
debate that never came by as an alert has no post to press a button under;
here any upcoming meeting can be started.
"""

import asyncio
import logging
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import require_permission
from bouwmeester.models.debat_sessie import (
    TIJDLIJN_AFGELAST,
    TIJDLIJN_AFGELOPEN,
    TIJDLIJN_GEKOPPELD,
    TIJDLIJN_LOOPT,
    DebatSessie,
    DebatSpreekbeurt,
)
from bouwmeester.models.person import Person
from bouwmeester.repositories.mattermost_user import MattermostUserRepository
from bouwmeester.schema.debat import (
    AankomendDebat,
    AankomendeDebattenResponse,
    DebatKanaal,
    DebatStartRequest,
    DebatStartResponse,
    DebatTeam,
    DebatVolgenResponse,
)
from bouwmeester.services import debat_direct as dd
from bouwmeester.services import debat_stand
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
from bouwmeester.services.mattermost_utils import escape_mattermost_prose
from bouwmeester.services.tk_activiteit import Activiteit, TkApiError, list_upcoming

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/debatten", tags=["debatten"])

_TK_TIMEOUT = 20.0
# How long the agenda of the Kamer is kept. The page refreshes every minute
# for what is running now, which comes from Debat Direct; the agenda of the
# coming weeks does not change by the minute, and without this every open
# tab asks the Kamer for up to four pages a minute.
UPCOMING_SECONDS = 300.0


class UpcomingCache:
    """The meetings of the coming weeks, read at most once per five minutes.

    Per number of days asked for. A failure is not kept: the next request
    tries again, and the caller answers that the agenda cannot be had.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._kept: dict[int, tuple[float, list[Activiteit]]] = {}

    def clear(self) -> None:
        self._kept.clear()

    def _fresh(self, dagen: int) -> list[Activiteit] | None:
        kept = self._kept.get(dagen)
        if kept is not None and time.monotonic() - kept[0] < UPCOMING_SECONDS:
            return kept[1]
        return None

    async def get(self, client: httpx.AsyncClient, dagen: int) -> list[Activiteit]:
        found = self._fresh(dagen)
        if found is not None:
            return found
        async with self._lock:
            # Whoever waited for the lock finds what the first one read.
            found = self._fresh(dagen)
            if found is not None:
                return found
            # With what is over by its planned end: a debate that runs late
            # is still on, and is dropped by the caller only if it really
            # is over.
            activiteiten = await list_upcoming(client, days=dagen, include_ended=True)
            self._kept[dagen] = (time.monotonic(), activiteiten)
            return activiteiten


UPCOMING = UpcomingCache()

# How many recorded channels are checked against Mattermost per request. A
# three-week window holds a handful; this only bounds a pathological case.
_MAX_CHANNEL_CHECKS = 20

# The statuses in which the timeline still looks at a sessie. The same three
# its tick selects on; anything else it leaves alone.
_FOLLOWED = (None, TIJDLIJN_GEKOPPELD, TIJDLIJN_LOOPT)

# What says whether a debate is in a break: the last of these to happen.
_BREAK_EVENTS = (
    dd.EVENT_SUSPENDED,
    dd.EVENT_CONTINUED,
    dd.EVENT_SPEAKER,
    dd.EVENT_INTERRUPTER,
    dd.EVENT_DEBATE_START,
    dd.EVENT_DEBATE_END,
)


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


def _kanaal(
    *,
    sessie_id: uuid.UUID | None,
    team_id: str,
    channel_name: str,
    tijdlijn_status: str | None,
    base_url: str,
    slug: str | None,
) -> DebatKanaal:
    return DebatKanaal(
        team_id=team_id,
        channel_name=channel_name,
        channel_url=_channel_url(base_url, slug, channel_name),
        sessie_id=sessie_id,
        tijdlijn_status=tijdlijn_status,
        wordt_gevolgd=sessie_id is not None and tijdlijn_status in _FOLLOWED,
    )


async def _in_a_break(db: AsyncSession, sessie_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """The sessies whose debate is suspended, going by the timeline.

    The agenda of Debat Direct does not say a debate is in a break; the
    events do, and the timeline keeps those for a debate it follows. The
    last thing that happened is what counts. Within one second a break
    loses from whatever else happened: saying "geschorst" about a debate
    that runs is worse than missing a break for a tick.
    """
    if not sessie_ids:
        return set()
    stmt = (
        select(DebatSpreekbeurt.sessie_id, DebatSpreekbeurt.event_type)
        .where(
            DebatSpreekbeurt.sessie_id.in_(sessie_ids),
            DebatSpreekbeurt.event_type.in_(_BREAK_EVENTS),
        )
        .distinct(DebatSpreekbeurt.sessie_id)
        .order_by(
            DebatSpreekbeurt.sessie_id,
            DebatSpreekbeurt.event_start.desc(),
            case((DebatSpreekbeurt.event_type == dd.EVENT_SUSPENDED, 1), else_=0),
        )
    )
    rows = (await db.execute(stmt)).all()
    return {sessie_id for sessie_id, kind in rows if kind == dd.EVENT_SUSPENDED}


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
    """The teams the bot is in and this person is a member of.

    Both halves matter. The bot creates the channel, so it has to be in the
    team; and it does so on behalf of this person, who is added to it and
    therefore has to be in the team too. Without the second half the list
    offers teams the person has nothing to do with, and a debate channel
    once landed in one of those.

    If the membership question leaves no team at all, every team of the
    bot is offered instead, with a warning in the log. That is deliberate.
    This check has been wrong once, in a way that could not be reproduced
    locally, and it took the button away from the person the page is for.
    A list that is too long is a nuisance; an empty one is a dead page.

    Without a person (local development without a login) there is no
    account to ask about, and every team of the bot counts.
    """
    try:
        if not await mattermost.is_enabled():
            return _Teams(melding="Mattermost staat niet aan.", unavailable=True)
        permissions = await mattermost.team_permissions()
        info = await mattermost.teams_info()

        result = _Teams(slugs={tid: i["slug"] for tid, i in info.items()})
        team_ids = list(permissions)
        if person is not None:
            mapping = await MattermostUserRepository(db).get_by_person_id(person.id)
            if mapping is None:
                result.melding = (
                    "Koppel je Mattermost-account bij Instellingen om kanalen "
                    "op te zetten."
                )
                return result
            result.mattermost_user_id = mapping.mattermost_user_id
            team_ids = [
                team_id
                for team_id in permissions
                if await mattermost.is_team_member(team_id, mapping.mattermost_user_id)
            ]
            if permissions and not team_ids:
                logger.warning(
                    "Account %s is volgens Mattermost lid van geen enkel team van "
                    "de bot (%s); alle teams worden aangeboden",
                    mapping.mattermost_user_id,
                    ", ".join(sorted(permissions)),
                )
                team_ids = list(permissions)
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
            for team_id in team_ids
        ),
        key=lambda team: (team.team_name or "").lower(),
    )
    return result


@router.get("/aankomend", response_model=AankomendeDebattenResponse)
async def list_aankomende_debatten(
    current_user: OptionalUser,
    dagen: int = Query(21, ge=1, le=60),
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("parlementair:read")),
) -> AankomendeDebattenResponse:
    """The meetings of the coming weeks, with the channel if there is one.

    The agenda of the Tweede Kamer is the same for everyone, so this is
    not filtered on organisation. Teams and channels are those of teams
    this person is in.
    """
    now = datetime.now(UTC)
    try:
        async with httpx.AsyncClient(timeout=_TK_TIMEOUT) as client:
            # With what is over by its planned end: a debate that runs late
            # is still on, and is dropped below only if it really is over.
            activiteiten = await UPCOMING.get(client, dagen)
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
        # Per activiteit: the Debat Direct debates the timeline found for
        # it, and the sessies in which it is running.
        known: dict[str, set[str]] = {}
        running: dict[str, list[uuid.UUID]] = {}
        ids = [a.id for a in activiteiten]
        if ids and allowed.team_ids:
            stmt = select(
                DebatSessie.activiteit_id,
                DebatSessie.team_id,
                DebatSessie.channel_id,
                DebatSessie.channel_name,
                DebatSessie.id,
                DebatSessie.tijdlijn_status,
                DebatSessie.debat_direct_ids,
            ).where(
                DebatSessie.activiteit_id.in_(ids),
                DebatSessie.team_id.in_(allowed.team_ids),
                DebatSessie.channel_id.is_not(None),
                DebatSessie.channel_name.is_not(None),
            )
            rows = (await db.execute(stmt)).all()
            for index, row in enumerate(rows):
                activiteit_id, team_id, channel_id, name = row[:4]
                sessie_id, tijdlijn, parts = row[4:]
                known.setdefault(activiteit_id, set()).update(parts or [])
                if tijdlijn == TIJDLIJN_LOOPT:
                    running.setdefault(activiteit_id, []).append(sessie_id)
                # A channel someone archived is not shown as a channel. The
                # row then offers the button again, and pressing it sets up
                # a new one. Showing a link to it instead would leave no
                # way to get there.
                if index < _MAX_CHANNEL_CHECKS and await mattermost.channel_is_gone(
                    channel_id
                ):
                    continue
                kanalen.setdefault(activiteit_id, []).append(
                    _kanaal(
                        sessie_id=sessie_id,
                        team_id=team_id,
                        channel_name=name,
                        tijdlijn_status=tijdlijn,
                        base_url=base_url,
                        slug=allowed.slugs.get(team_id),
                    )
                )
    finally:
        await mattermost.close()

    # Where each debate stands, from one reading of today's agenda. Without
    # Debat Direct the list comes back as it always did, without the marks.
    standen: dict[str, debat_stand.Stand] = {}
    agenda = await debat_stand.AGENDA.today(now)
    for a in activiteiten if agenda else []:
        stand = debat_stand.stand_of(
            debat_stand.parts_of(a, agenda or [], known.get(a.id, ()))
        )
        if stand is not None:
            standen[a.id] = stand
    in_a_break = await _in_a_break(
        db,
        [
            sessie_id
            for activiteit_id, sessie_ids in running.items()
            if activiteit_id in standen
            and standen[activiteit_id].stand == debat_stand.STAND_BEZIG
            for sessie_id in sessie_ids
        ],
    )
    for activiteit_id, sessie_ids in running.items():
        if in_a_break.intersection(sessie_ids):
            standen[activiteit_id] = debat_stand.Stand(
                debat_stand.STAND_GESCHORST, standen[activiteit_id].begonnen_om
            )

    def on_the_list(a: Activiteit) -> bool:
        # Past its planned end: only while Debat Direct says it is still on.
        if a.einde is None or a.einde >= now:
            return True
        stand = standen.get(a.id)
        return stand is not None and stand.stand in debat_stand.STAND_NU

    activiteiten = [a for a in activiteiten if on_the_list(a)]

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
                stand=standen[a.id].stand if a.id in standen else None,
                begonnen_om=standen[a.id].begonnen_om if a.id in standen else None,
            )
            for a in activiteiten
        ],
        teams=allowed.teams,
        mattermost_melding=allowed.melding,
    )


def _require_team(allowed: _Teams, team_id: str) -> None:
    """Refuse a team this person cannot have a channel in.

    One rule for starting, stopping and resuming: whoever may set a channel
    up in a team may also say what the bot does in it.
    """
    if allowed.unavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=allowed.melding,
        )
    if team_id not in allowed.team_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=allowed.melding or "Je kunt in dit team geen kanaal laten opzetten.",
        )


@router.post("/start", response_model=DebatStartResponse)
async def start_debat(
    body: DebatStartRequest,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("parlementair:review")),
) -> DebatStartResponse:
    """Set up a channel for one meeting, in a team this person is in.

    Answers 200 also when no channel was made: a cancelled meeting or a
    missing Mattermost permission is an outcome with a reason to show, not
    an error in the request.
    """
    mattermost = MattermostService(db)
    try:
        allowed = await _teams_for(mattermost, db, current_user)
        # The team comes from the browser, so it is checked against the
        # same list the page was given.
        _require_team(allowed, body.team_id)

        result = await DebatKanaalService(db, mattermost).start_in_team(
            activiteit_id=str(body.activiteit_id),
            team_id=body.team_id,
            mattermost_user_id=allowed.mattermost_user_id,
        )

        kanaal = None
        if result.channel_name:
            sessie = None
            if result.channel_id:
                sessie = (
                    await db.execute(
                        select(DebatSessie.id, DebatSessie.tijdlijn_status).where(
                            DebatSessie.channel_id == result.channel_id
                        )
                    )
                ).first()
            kanaal = _kanaal(
                sessie_id=sessie[0] if sessie else None,
                team_id=body.team_id,
                channel_name=result.channel_name,
                tijdlijn_status=sessie[1] if sessie else None,
                base_url=_browser_base(await mattermost.base_url()),
                slug=allowed.slugs.get(body.team_id),
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


async def _sessie_of(
    db: AsyncSession,
    mattermost: MattermostService,
    person: Person | None,
    sessie_id: uuid.UUID,
) -> DebatSessie:
    """The sessie with a channel, if this person may act on its team."""
    allowed = await _teams_for(mattermost, db, person)
    if allowed.unavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=allowed.melding,
        )
    sessie = await db.get(DebatSessie, sessie_id)
    # A claim without a channel is a start that is still running, or one
    # that broke off: there is nothing to follow yet.
    if sessie is None or sessie.channel_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voor dit debat is geen kanaal bekend.",
        )
    _require_team(allowed, sessie.team_id)
    return sessie


def _door(person: Person | None) -> str:
    """` door Persoon A`, or nothing without a login (local development)."""
    if person is None or not person.naam:
        return ""
    return f" door {escape_mattermost_prose(person.naam)}"


async def _volgen_response(
    db: AsyncSession, sessie_id: uuid.UUID
) -> DebatVolgenResponse:
    # Read back, not taken from what this request meant to write: someone
    # else may have pressed the other button in the meantime.
    tijdlijn = await db.scalar(
        select(DebatSessie.tijdlijn_status).where(DebatSessie.id == sessie_id)
    )
    return DebatVolgenResponse(
        sessie_id=sessie_id,
        tijdlijn_status=tijdlijn,
        wordt_gevolgd=tijdlijn in _FOLLOWED,
    )


def _forget_voices(sessie_id: uuid.UUID) -> None:
    """Drop the voices of a debate that is no longer followed.

    They live in the memory of the process that listens, which is the
    worker. Its tick forgets every sessie it no longer selects, so there
    they are gone within one tick. Here they are dropped at once if this
    process is the one holding them; the module is not loaded for it, since
    that would bring the audio stack into the API to forget nothing.
    """
    stem = sys.modules.get("bouwmeester.services.debat_stem")
    if stem is not None:
        stem.VOICES.forget(sessie_id)


@router.post("/{sessie_id}/stop", response_model=DebatVolgenResponse)
async def stop_debat(
    sessie_id: uuid.UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("parlementair:review")),
) -> DebatVolgenResponse:
    """Stop following a debate. The channel stays as it is.

    The timeline, the transcript and the question marking all select on the
    status, so setting it is what stops them. Stopping what is not followed
    answers the same and says nothing in the channel.
    """
    mattermost = MattermostService(db)
    try:
        sessie = await _sessie_of(db, mattermost, current_user, sessie_id)
        channel_id = sessie.channel_id
        door = _door(current_user)
        # One statement that only hits a sessie that is followed: of two
        # people pressing at once, one stops it and one finds it stopped.
        stopped = (
            await db.execute(
                update(DebatSessie)
                .where(
                    DebatSessie.id == sessie_id,
                    DebatSessie.tijdlijn_status.is_(None)
                    | DebatSessie.tijdlijn_status.in_(
                        (TIJDLIJN_GEKOPPELD, TIJDLIJN_LOOPT)
                    ),
                )
                .values(tijdlijn_status=TIJDLIJN_AFGELOPEN)
                .returning(DebatSessie.id)
            )
        ).first() is not None
        await db.commit()
        if stopped:
            _forget_voices(sessie_id)
            posted = await mattermost.send_channel_message(
                channel_id, f"⏹️ Het meeluisteren is gestopt{door}."
            )
            if not posted:
                logger.warning(
                    "Melding van het stoppen niet geplaatst in %s", channel_id
                )
        return await _volgen_response(db, sessie_id)
    finally:
        await mattermost.close()


@router.post("/{sessie_id}/hervat", response_model=DebatVolgenResponse)
async def hervat_debat(
    sessie_id: uuid.UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_permission("parlementair:review")),
) -> DebatVolgenResponse:
    """Follow a debate again after it was stopped.

    The timeline picks it up on its next tick and deals with what happened
    in between the way it deals with any absence: it says what it missed
    and where that is to be found, and goes on from now.
    """
    mattermost = MattermostService(db)
    try:
        sessie = await _sessie_of(db, mattermost, current_user, sessie_id)
        channel_id = sessie.channel_id
        door = _door(current_user)
        if sessie.tijdlijn_status == TIJDLIJN_AFGELAST:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Dit debat is afgelast.",
            )
        parts = list(sessie.debat_direct_ids or [])
        if sessie.tijdlijn_status == TIJDLIJN_AFGELOPEN:
            agenda = await debat_stand.AGENDA.today()
            stand = debat_stand.stand_of(
                debat_stand.parts_of(_as_activiteit(sessie), agenda or [], parts)
            )
            if stand is not None and stand.stand == debat_stand.STAND_AFGELOPEN:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Dit debat is afgelopen; er valt niets meer te volgen.",
                )
        # Running again at once if it was running: the text and the
        # questions only look at a debate that runs, and the timeline
        # itself only says so at the next event, which in a long speech
        # can be a quarter of an hour away.
        was_running = (
            parts
            and (
                await db.execute(
                    select(DebatSpreekbeurt.id)
                    .where(DebatSpreekbeurt.sessie_id == sessie_id)
                    .limit(1)
                )
            ).first()
        )
        if was_running:
            status_after_resume: str | None = TIJDLIJN_LOOPT
        else:
            status_after_resume = TIJDLIJN_GEKOPPELD if parts else None
        resumed = (
            await db.execute(
                update(DebatSessie)
                .where(
                    DebatSessie.id == sessie_id,
                    DebatSessie.tijdlijn_status == TIJDLIJN_AFGELOPEN,
                )
                .values(
                    # With the parts it had: looking them up again compares
                    # with the planned start, and a debate that began late
                    # would not be found a second time. Without parts it was
                    # never found, and is looked for as from the start.
                    tijdlijn_status=status_after_resume,
                    # Due at once, not after what is left of five minutes.
                    tijdlijn_gecontroleerd_at=None,
                )
                .returning(DebatSessie.id)
            )
        ).first() is not None
        await db.commit()
        if resumed:
            posted = await mattermost.send_channel_message(
                channel_id, f"▶️ Het meeluisteren is hervat{door}."
            )
            if not posted:
                logger.warning(
                    "Melding van het hervatten niet geplaatst in %s", channel_id
                )
        return await _volgen_response(db, sessie_id)
    finally:
        await mattermost.close()


def _as_activiteit(sessie: DebatSessie) -> Activiteit:
    """What the sessie remembers of its activiteit, to match on."""
    return Activiteit(
        id=sessie.activiteit_id,
        nummer=sessie.activiteit_nummer,
        soort=None,
        onderwerp=sessie.onderwerp,
        aanvang=sessie.aanvang,
        einde=None,
        status=None,
        commissie=None,
        bewindspersonen=(),
        agendapunten=(),
    )
