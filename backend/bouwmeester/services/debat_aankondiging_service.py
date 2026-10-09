"""Announce a debate in the channels of an initiatief, and remind on the day.

Two moments. When someone announces a debate, one message goes into the
channels of the initiatief that follow the Kamer. On the morning of the debate the
meeting is read again and the same channels get either a reminder or the
news that it is off: a convocatie comes a median 20.5 days ahead (measured
over 80), and of 250 measured activiteiten 25 were cancelled or moved in
between.

Only channels where "Kamerstuk-alerts" is on. The first version posted in
every linked channel, on the reasoning that the switches are for what the
bot sends by itself and this is something a person asked for. That put two
debates in a channel that was linked for news from the press: the switch
says what a channel is for, not only what the bot may start by itself.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.debat_aankondiging import (
    STAND_AANGEKONDIGD,
    STAND_AFGELAST,
    STAND_HERINNERD,
    STAND_VOORBIJ,
    DebatAankondiging,
)
from bouwmeester.models.debat_sessie import DebatSessie
from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.mattermost_channel_link import (
    SCOPE_INITIATIEF,
    MattermostChannelLink,
)
from bouwmeester.repositories.mattermost_user import MattermostUserRepository
from bouwmeester.services.debat_kanaal_service import (
    AMSTERDAM,
    DEBAT_DIRECT_URL,
    RETRY_HINT_REACTION,
    _format_start,
    activiteit_url,
    find_successor,
    format_moment,
)
from bouwmeester.services.kamerstuk_soort import CAT_VERGADERING_VOORUIT
from bouwmeester.services.mattermost_service import MattermostService
from bouwmeester.services.mattermost_utils import (
    escape_mattermost_md,
    escape_mattermost_prose,
)
from bouwmeester.services.tk_activiteit import (
    STATUS_CANCELLED,
    STATUS_MOVED,
    Activiteit,
    TkApiError,
    fetch_activiteit,
)

logger = logging.getLogger(__name__)

_TK_TIMEOUT = 15.0

# From when on the day the reminder goes out, in Dutch local time. Early
# enough for a debate at ten, late enough that someone reads it.
REMINDER_FROM_HOUR = 7

# The reaction under an alert that puts its meeting on the list.
REACTIE_AANKONDIGEN = "mega"

# A convocatie for written input announces a deadline, not a meeting: there
# is nothing to watch on the day.
_SOORT_ZONDER_VERGADERING = "Convocatie inbreng"

# How long a planned meeting is taken to last when the API gives no end.
_ASSUMED_DURATION = timedelta(hours=4)


class AnnounceRefusedError(Exception):
    """This debate cannot be announced. The message says why, in Dutch."""


class AlreadyAnnouncedError(Exception):
    """This debate was already announced for this initiatief."""


class _NotDeliveredError(Exception):
    """There are channels, and Mattermost took the message in none of them."""


def is_over(
    aanvang: datetime | None, einde: datetime | None, now: datetime | None = None
) -> bool:
    """Whether a meeting has ended, going by its planned times."""
    now = now or datetime.now(UTC)
    if einde is not None:
        return einde < now
    return aanvang is not None and aanvang + _ASSUMED_DURATION < now


def is_announceable(extra: dict | None, today: date | None = None) -> bool:
    """Should this alert get the reaction that puts its meeting on the list?

    Decided on what the import stored, without a call to the TK API: this
    runs for every alert that is posted. Pressing reads the current state,
    so a meeting that was cancelled afterwards is caught there.
    """
    extra = extra or {}
    if not extra.get("activiteit_id"):
        return False
    if extra.get("categorie") != CAT_VERGADERING_VOORUIT:
        return False
    if extra.get("soort") == _SOORT_ZONDER_VERGADERING:
        return False
    if extra.get("activiteit_status") in (STATUS_CANCELLED, STATUS_MOVED):
        return False
    raw = extra.get("activiteit_datum")
    if raw:
        try:
            datum = date.fromisoformat(str(raw)[:10])
        except ValueError:
            return True
        if datum < (today or datetime.now(AMSTERDAM).date()):
            return False
    return True


def _title(activiteit: Activiteit) -> str:
    onderwerp = escape_mattermost_md(activiteit.onderwerp)
    if activiteit.nummer:
        return f"[{onderwerp}]({activiteit_url(activiteit.nummer)})"
    return onderwerp


def _context_line(activiteit: Activiteit, *, with_moment: bool) -> str:
    delen = [
        activiteit.soort,
        format_moment(activiteit) if with_moment else None,
        activiteit.commissie,
    ]
    return " · ".join(escape_mattermost_prose(deel) for deel in delen if deel)


def _channel_line(debat_channel: str | None) -> str | None:
    if not debat_channel:
        return None
    return f"De bot luistert mee in ~{debat_channel}."


def announcement_message(
    activiteit: Activiteit,
    *,
    initiatief_naam: str,
    door: str | None,
    reminder_follows: bool = True,
    debat_channel: str | None = None,
) -> str:
    """The message that says a debate is coming."""
    wie = f" door {escape_mattermost_prose(door)}" if door else ""
    slot = " Op de dag zelf volgt hier een herinnering." if reminder_follows else ""
    regels = [
        f"📣 **Debat aangekondigd: {_title(activiteit)}**",
        _context_line(activiteit, with_moment=True),
        f"Aangekondigd{wie} voor **{escape_mattermost_md(initiatief_naam)}**.{slot}",
        _channel_line(debat_channel),
    ]
    return "\n".join(regel for regel in regels if regel)


def reminder_message(activiteit: Activiteit, debat_channel: str | None = None) -> str:
    """The message of the day itself."""
    wanneer = "Vandaag"
    if activiteit.aanvang is not None:
        start = activiteit.aanvang.astimezone(AMSTERDAM)
        wanneer = f"Vandaag om {start:%H:%M}"
    regels = [
        f"🔔 **{wanneer}: {_title(activiteit)}**",
        " · ".join(
            deel
            for deel in (
                _context_line(activiteit, with_moment=False),
                f"[Live via Debat Direct]({DEBAT_DIRECT_URL})",
            )
            if deel
        ),
        _channel_line(debat_channel),
    ]
    return "\n".join(regel for regel in regels if regel)


def listed_message(
    activiteit: Activiteit, initiatief_naam: str, *, reminder_follows: bool
) -> str:
    """The reply under an alert whose meeting was put on the list."""
    naam = escape_mattermost_md(initiatief_naam)
    if not reminder_follows or activiteit.aanvang is None:
        return f"📣 Deze vergadering staat op de lijst van **{naam}**."
    start = activiteit.aanvang.astimezone(AMSTERDAM)
    dag = _format_start(activiteit.aanvang).split(",")[0]
    return (
        f"📣 Deze vergadering staat op de lijst van **{naam}**. Op de ochtend "
        f"van {dag} volgt in dit kanaal een herinnering; ze begint om "
        f"{start:%H:%M}."
    )


def off_message(row: DebatAankondiging, wat: str) -> str:
    """The message that an announced debate is not happening as announced."""
    wanneer = f" van {_format_start(row.aanvang)}" if row.aanvang else ""
    return f"⚠️ De vergadering **{escape_mattermost_md(row.onderwerp)}**{wanneer} {wat}"


def moved_message(row: DebatAankondiging, activiteit: Activiteit) -> str:
    """The message that an announced debate has a new moment."""
    was = f" (was {_format_start(row.aanvang)})" if row.aanvang else ""
    return (
        f"📅 De vergadering **{_title(activiteit)}** is verzet naar "
        f"{format_moment(activiteit)}{was}."
    )


@dataclass
class _Recorded:
    row: DebatAankondiging
    # The meeting as the Kamer has it now.
    activiteit: Activiteit
    is_today: bool
    # Set when the meeting was on the list already, for one channel only,
    # and now reaches further: the channel it was limited to.
    widened_from: str | None = None


@dataclass
class AnnounceResult:
    row: DebatAankondiging
    # In how many channels the announcement was posted. Zero is a valid
    # outcome: an initiatief without a channel still lists the debate.
    gepost_in: int


@dataclass
class TickResult:
    herinnerd: int = 0
    afgelast: int = 0
    verzet: int = 0
    fouten: int = 0

    def summary(self) -> str:
        return (
            f"{self.herinnerd} herinnerd, {self.afgelast} afgelast, "
            f"{self.verzet} verzet, {self.fouten} fouten"
        )


class DebatAankondigingService:
    def __init__(
        self, session: AsyncSession, mattermost: MattermostService | None = None
    ) -> None:
        self.session = session
        self.mattermost = mattermost or MattermostService(session)

    async def close(self) -> None:
        await self.mattermost.close()

    async def announce(
        self,
        initiatief: Initiatief,
        activiteit_id: str,
        *,
        person_id: uuid.UUID | None,
        door: str | None,
        now: datetime | None = None,
    ) -> AnnounceResult:
        """Record the debate for this initiatief and tell its channels.

        Raises `TkApiError` when the agenda cannot be read,
        `AnnounceRefusedError` when this meeting is not one to announce and
        `AlreadyAnnouncedError` when it was announced before.
        """
        recorded = await self._record(initiatief.id, activiteit_id, person_id, now)
        activiteit = recorded.activiteit
        links = await self._channels(initiatief.id)
        if recorded.widened_from:
            # The channel where someone pressed the megaphone has the alert
            # and the answer under it; it does not need the news again.
            links = [link for link in links if link.channel_id != recorded.widened_from]
        gepost = await self._post(
            activiteit.id,
            lambda kanaal: announcement_message(
                activiteit,
                initiatief_naam=initiatief.naam,
                door=door,
                reminder_follows=not recorded.is_today,
                debat_channel=kanaal,
            ),
            links,
        )
        return AnnounceResult(row=recorded.row, gepost_in=gepost)

    async def announce_from_alert(
        self,
        *,
        extra: dict | None,
        channel_id: str,
        post_id: str,
        mattermost_user_id: str | None,
        now: datetime | None = None,
    ) -> str:
        """Put the meeting of an alert on the list of the initiatief.

        For the reaction under an alert. The alert is the announcement, so
        nothing new goes into the channel: the answer is a reply in the
        thread, also when nothing was done, and the reminder follows on the
        day, in this channel only. Anyone in the channel may press, like
        the start button: all it brings about is one more message in a
        channel they are already in. A press in a second channel of the
        same initiatief widens the reminder to all its channels.

        Returns what happened: listed, exists, refused or failed.
        """

        async def reply(tekst: str) -> None:
            await self.mattermost.send_channel_message(
                channel_id, tekst, root_id=post_id
            )

        link = (
            await self.session.execute(
                select(MattermostChannelLink).where(
                    MattermostChannelLink.channel_id == channel_id
                )
            )
        ).scalar_one_or_none()
        initiatief = (
            await self.session.get(Initiatief, link.scope_id)
            if link is not None and link.scope_type == SCOPE_INITIATIEF
            else None
        )
        if initiatief is None:
            await reply(
                "Dit kanaal hangt niet aan een initiatief, dus er is geen lijst "
                "om deze vergadering op te zetten."
            )
            return "refused"
        activiteit_id = (extra or {}).get("activiteit_id")
        if not activiteit_id:
            await reply("Bij dit stuk is geen vergadering bekend.")
            return "refused"

        person_id = None
        if mattermost_user_id:
            mapping = await MattermostUserRepository(
                self.session
            ).get_by_mattermost_user_id(mattermost_user_id)
            person_id = mapping.person_id if mapping else None

        naam = initiatief.naam
        # None of the refusals below leaves anything to roll back: the
        # meeting is only read, and a lost insert undoes its own savepoint.
        try:
            recorded = await self._record(
                initiatief.id, str(activiteit_id), person_id, now, channel_id
            )
            await self.session.commit()
        except TkApiError:
            await reply(
                "De agenda van de Tweede Kamer is nu niet op te halen. "
                f"{RETRY_HINT_REACTION}"
            )
            return "failed"
        except AnnounceRefusedError as exc:
            await reply(str(exc))
            return "refused"
        except AlreadyAnnouncedError:
            await reply(
                "Deze vergadering staat al op de lijst van "
                f"**{escape_mattermost_md(naam)}**."
            )
            return "exists"

        await reply(
            listed_message(
                recorded.activiteit, naam, reminder_follows=not recorded.is_today
            )
        )
        return "listed"

    async def _record(
        self,
        initiatief_id: uuid.UUID,
        activiteit_id: str,
        person_id: uuid.UUID | None,
        now: datetime | None,
        channel_id: str | None = None,
    ) -> _Recorded:
        """Read the meeting and put it on the list; posts nothing.

        `channel_id` limits the reminder to that channel; without it every
        channel of the initiatief gets it. A meeting that is on the list
        for one channel and is asked for again from elsewhere is widened
        to all channels instead of refused.
        """
        async with httpx.AsyncClient(timeout=_TK_TIMEOUT) as client:
            activiteit = await fetch_activiteit(activiteit_id, client)
        if activiteit is None:
            raise AnnounceRefusedError(
                "Deze vergadering staat niet meer op de agenda van de Kamer."
            )
        if activiteit.status == STATUS_CANCELLED:
            raise AnnounceRefusedError("Deze vergadering is geannuleerd.")
        if activiteit.status == STATUS_MOVED:
            raise AnnounceRefusedError(
                "Deze vergadering is verplaatst. Kies de nieuwe datum in de lijst."
            )
        if activiteit.aanvang is None:
            # The round of the day goes by the date. A row without one
            # would promise a reminder and never be looked at again.
            raise AnnounceRefusedError(
                "Deze vergadering heeft nog geen datum. Probeer het opnieuw "
                "als de Kamer haar heeft ingepland."
            )
        now = now or datetime.now(UTC)
        if is_over(activiteit.aanvang, activiteit.einde, now):
            raise AnnounceRefusedError("Deze vergadering is al geweest.")

        row = DebatAankondiging(
            initiatief_id=initiatief_id,
            activiteit_id=activiteit.id,
            channel_id=channel_id,
            created_by_id=person_id,
        )
        self._take_over(row, activiteit)
        # A debate of today is not reminded of minutes after it was
        # announced: the announcement is the reminder.
        today = now.astimezone(AMSTERDAM).date()
        is_today = (
            activiteit.aanvang is not None
            and activiteit.aanvang.astimezone(AMSTERDAM).date() <= today
        )
        if is_today:
            row.stand = STAND_HERINNERD
        try:
            # A savepoint, so a second press that loses the race leaves the
            # session of the caller usable.
            async with self.session.begin_nested():
                self.session.add(row)
        except IntegrityError as exc:
            existing = (
                await self.session.execute(
                    select(DebatAankondiging).where(
                        DebatAankondiging.initiatief_id == initiatief_id,
                        DebatAankondiging.activiteit_id == activiteit.id,
                    )
                )
            ).scalar_one_or_none()
            if (
                existing is None
                or existing.channel_id is None
                or existing.channel_id == channel_id
            ):
                raise AlreadyAnnouncedError from exc
            widened_from = existing.channel_id
            existing.channel_id = None
            return _Recorded(existing, activiteit, is_today, widened_from)
        return _Recorded(row, activiteit, is_today)

    async def tick(self, now: datetime | None = None) -> TickResult:
        """Remind of what is on today, and say what is off."""
        now = now or datetime.now(UTC)
        result = TickResult()
        local = now.astimezone(AMSTERDAM)
        if local.hour < REMINDER_FROM_HOUR:
            return result
        if not await self.mattermost.is_enabled():
            return result

        end_of_day = (local + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        # Ids, and each row read again inside the loop: a commit or a
        # rollback expires what was loaded before it.
        ids = (
            (
                await self.session.execute(
                    select(DebatAankondiging.id)
                    .where(
                        DebatAankondiging.stand == STAND_AANGEKONDIGD,
                        DebatAankondiging.aanvang.is_not(None),
                        DebatAankondiging.aanvang < end_of_day,
                    )
                    .order_by(DebatAankondiging.aanvang)
                )
            )
            .scalars()
            .all()
        )
        if not ids:
            return result

        async with httpx.AsyncClient(timeout=_TK_TIMEOUT) as client:
            # A commit after each row: a message that went out must not go
            # out again because a later row failed.
            for row_id in ids:
                try:
                    row = await self.session.get(DebatAankondiging, row_id)
                    if row is None or row.stand != STAND_AANGEKONDIGD:
                        continue
                    await self._handle(row, client, now, result)
                    await self.session.commit()
                except (TkApiError, _NotDeliveredError) as exc:
                    # Not a reason to say anything; the next tick tries
                    # again, with the row as it was.
                    await self.session.rollback()
                    result.fouten += 1
                    logger.warning(
                        "Aankondiging %s blijft staan: %s",
                        row_id,
                        type(exc).__name__,
                    )
                except Exception:
                    await self.session.rollback()
                    result.fouten += 1
                    logger.exception("Herinnering voor aankondiging %s mislukt", row_id)
        return result

    async def _handle(
        self,
        row: DebatAankondiging,
        client: httpx.AsyncClient,
        now: datetime,
        result: TickResult,
    ) -> None:
        if is_over(row.aanvang, row.einde, now):
            row.stand = STAND_VOORBIJ
            return

        activiteit = await fetch_activiteit(row.activiteit_id, client)
        if activiteit is None:
            await self._call_off(
                row, "staat niet meer op de agenda van de Kamer.", result
            )
            return
        if activiteit.status == STATUS_CANCELLED:
            await self._call_off(row, "is geannuleerd.", result)
            return
        if activiteit.status == STATUS_MOVED:
            successor = await find_successor(activiteit, client)
            if successor is None or successor.status in (
                STATUS_CANCELLED,
                STATUS_MOVED,
            ):
                await self._call_off(
                    row, "is verplaatst. Een nieuwe datum is er nog niet.", result
                )
                return
            await self._follow(row, successor, now, result)
            return
        if activiteit.aanvang is None:
            await self._call_off(row, "heeft geen datum meer.", result)
            return

        today = now.astimezone(AMSTERDAM).date()
        if (
            activiteit.aanvang is not None
            and activiteit.aanvang.astimezone(AMSTERDAM).date() > today
        ):
            # Same meeting, later day: the Kamer changed the time without
            # moving it to a new activiteit.
            await self._follow(row, activiteit, now, result)
            return

        self._take_over(row, activiteit)
        if is_over(activiteit.aanvang, activiteit.einde, now):
            row.stand = STAND_VOORBIJ
            return
        await self._deliver(
            row, activiteit.id, lambda kanaal: reminder_message(activiteit, kanaal)
        )
        row.stand = STAND_HERINNERD
        result.herinnerd += 1

    async def _call_off(
        self, row: DebatAankondiging, wat: str, result: TickResult
    ) -> None:
        tekst = off_message(row, wat)
        await self._deliver(row, row.activiteit_id, lambda _: tekst)
        row.stand = STAND_AFGELAST
        result.afgelast += 1

    async def _follow(
        self,
        row: DebatAankondiging,
        activiteit: Activiteit,
        now: datetime,
        result: TickResult,
    ) -> None:
        """Move the row to the meeting as it stands now, and say so."""
        if is_over(activiteit.aanvang, activiteit.einde, now):
            # Moved to a date that has gone by: the row is only read on the
            # morning of the date it knew. "Moved to last Tuesday" is news
            # nobody can use.
            row.stand = STAND_VOORBIJ
            return
        tekst = moved_message(row, activiteit)
        if activiteit.id != row.activiteit_id:
            already = (
                await self.session.execute(
                    select(DebatAankondiging.id).where(
                        DebatAankondiging.initiatief_id == row.initiatief_id,
                        DebatAankondiging.activiteit_id == activiteit.id,
                    )
                )
            ).first()
            if already is not None:
                # Someone announced the new date as well. That row carries
                # on; this one is done, and nothing needs saying twice.
                row.stand = STAND_AFGELAST
                return
            row.activiteit_id = activiteit.id
        await self._deliver(row, activiteit.id, lambda _: tekst)
        self._take_over(row, activiteit)
        result.verzet += 1

    @staticmethod
    def _take_over(row: DebatAankondiging, activiteit: Activiteit) -> None:
        row.activiteit_nummer = activiteit.nummer
        row.soort = activiteit.soort
        row.onderwerp = activiteit.onderwerp
        row.commissie = activiteit.commissie
        row.aanvang = activiteit.aanvang
        row.einde = activiteit.einde

    async def _channels(
        self, initiatief_id: uuid.UUID, only: str | None = None
    ) -> list[MattermostChannelLink]:
        """The channels of the initiatief that are about the Kamer."""
        stmt = select(MattermostChannelLink).where(
            MattermostChannelLink.scope_type == SCOPE_INITIATIEF,
            MattermostChannelLink.scope_id == initiatief_id,
            MattermostChannelLink.disabled_at.is_(None),
            MattermostChannelLink.parlementaire_alerts_enabled.is_(True),
        )
        if only is not None:
            stmt = stmt.where(MattermostChannelLink.channel_id == only)
        return list((await self.session.execute(stmt)).scalars().all())

    async def _debat_channels(self, activiteit_id: str) -> dict[str, str]:
        """Per team, the channel in which the bot follows this debate."""
        stmt = select(DebatSessie.team_id, DebatSessie.channel_name).where(
            DebatSessie.activiteit_id == activiteit_id,
            DebatSessie.channel_id.is_not(None),
            DebatSessie.channel_name.is_not(None),
        )
        return {team: name for team, name in (await self.session.execute(stmt)).all()}

    async def _deliver(self, row: DebatAankondiging, activiteit_id: str, build) -> None:
        """Post where this row is to be told, and raise when nowhere took it.

        Without a channel there is nobody to tell, and that counts as
        told: the row moves on instead of being asked about every tick.

        One channel that took it is enough. A channel that failed while
        another succeeded does not get the message later: trying again
        would post it a second time where it did arrive, and a message
        that comes twice is worse than one that is missed in one of
        several channels.
        """
        links = await self._channels(row.initiatief_id, only=row.channel_id)
        if links and not await self._post(activiteit_id, build, links):
            raise _NotDeliveredError

    async def _post(
        self, activiteit_id: str, build, links: list[MattermostChannelLink]
    ) -> int:
        """Post in each of these channels; returns in how many.

        `build` gets the name of the debate channel in the team of the
        channel that is written to, or ``None``: a `~channel` link only
        works within one team.
        """
        if not links or not await self.mattermost.is_enabled():
            return 0
        debat_channels = await self._debat_channels(activiteit_id)
        gepost = 0
        for link in links:
            kanaal = debat_channels.get(link.team_id) if link.team_id else None
            if await self.mattermost.send_channel_message(
                link.channel_id, build(kanaal)
            ):
                gepost += 1
        return gepost
