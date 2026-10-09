"""Announce a debate in the channels of an initiatief, and remind on the day.

Two moments. When someone announces a debate, one message goes into every
channel that is linked to the initiatief. On the morning of the debate the
meeting is read again and the same channels get either a reminder or the
news that it is off: a convocatie comes a median 20.5 days ahead (measured
over 80), and of 250 measured activiteiten 25 were cancelled or moved in
between.

All linked channels, whatever their switches say. The switches are for
what the bot sends by itself; this is something a person asked for.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

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
from bouwmeester.services.debat_kanaal_service import (
    AMSTERDAM,
    DEBAT_DIRECT_URL,
    _format_start,
    activiteit_url,
    find_successor,
    format_moment,
)
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


def off_message(row: DebatAankondiging, wat: str) -> str:
    """The message that an announced debate is not happening as announced."""
    wanneer = f" van {_format_start(row.aanvang)}" if row.aanvang else ""
    return f"⚠️ Het debat **{escape_mattermost_md(row.onderwerp)}**{wanneer} {wat}"


def moved_message(row: DebatAankondiging, activiteit: Activiteit) -> str:
    """The message that an announced debate has a new moment."""
    was = f" (was {_format_start(row.aanvang)})" if row.aanvang else ""
    return (
        f"📅 Het debat **{_title(activiteit)}** is verzet naar "
        f"{format_moment(activiteit)}{was}."
    )


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
        now = now or datetime.now(UTC)
        if is_over(activiteit.aanvang, activiteit.einde, now):
            raise AnnounceRefusedError("Deze vergadering is al geweest.")

        row = DebatAankondiging(
            initiatief_id=initiatief.id,
            activiteit_id=activiteit.id,
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
            raise AlreadyAnnouncedError from exc

        gepost = await self._post(
            initiatief.id,
            activiteit.id,
            lambda kanaal: announcement_message(
                activiteit,
                initiatief_naam=initiatief.naam,
                door=door,
                reminder_follows=not is_today,
                debat_channel=kanaal,
            ),
        )
        return AnnounceResult(row=row, gepost_in=gepost)

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
            await self._follow(row, successor, result)
            return

        today = now.astimezone(AMSTERDAM).date()
        if (
            activiteit.aanvang is not None
            and activiteit.aanvang.astimezone(AMSTERDAM).date() > today
        ):
            # Same meeting, later day: the Kamer changed the time without
            # moving it to a new activiteit.
            await self._follow(row, activiteit, result)
            return

        self._take_over(row, activiteit)
        if is_over(activiteit.aanvang, activiteit.einde, now):
            row.stand = STAND_VOORBIJ
            return
        await self._deliver(
            row.initiatief_id,
            activiteit.id,
            lambda kanaal: reminder_message(activiteit, kanaal),
        )
        row.stand = STAND_HERINNERD
        result.herinnerd += 1

    async def _call_off(
        self, row: DebatAankondiging, wat: str, result: TickResult
    ) -> None:
        tekst = off_message(row, wat)
        await self._deliver(row.initiatief_id, row.activiteit_id, lambda _: tekst)
        row.stand = STAND_AFGELAST
        result.afgelast += 1

    async def _follow(
        self, row: DebatAankondiging, activiteit: Activiteit, result: TickResult
    ) -> None:
        """Move the row to the meeting as it stands now, and say so."""
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
        await self._deliver(row.initiatief_id, activiteit.id, lambda _: tekst)
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

    async def _channels(self, initiatief_id: uuid.UUID) -> list[MattermostChannelLink]:
        stmt = select(MattermostChannelLink).where(
            MattermostChannelLink.scope_type == SCOPE_INITIATIEF,
            MattermostChannelLink.scope_id == initiatief_id,
            MattermostChannelLink.disabled_at.is_(None),
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def _debat_channels(self, activiteit_id: str) -> dict[str, str]:
        """Per team, the channel in which the bot follows this debate."""
        stmt = select(DebatSessie.team_id, DebatSessie.channel_name).where(
            DebatSessie.activiteit_id == activiteit_id,
            DebatSessie.channel_id.is_not(None),
            DebatSessie.channel_name.is_not(None),
        )
        return {team: name for team, name in (await self.session.execute(stmt)).all()}

    async def _deliver(
        self, initiatief_id: uuid.UUID, activiteit_id: str, build
    ) -> None:
        """Post, and raise when there were channels and none took it.

        Without a channel there is nobody to tell, and that counts as
        told: the row moves on instead of being asked about every tick.
        """
        links = await self._channels(initiatief_id)
        if links and not await self._post(initiatief_id, activiteit_id, build, links):
            raise _NotDeliveredError

    async def _post(
        self,
        initiatief_id: uuid.UUID,
        activiteit_id: str,
        build,
        links: list[MattermostChannelLink] | None = None,
    ) -> int:
        """Post in every channel of the initiatief; returns in how many.

        `build` gets the name of the debate channel in the team of the
        channel that is written to, or ``None``: a `~channel` link only
        works within one team.
        """
        if not await self.mattermost.is_enabled():
            return 0
        if links is None:
            links = await self._channels(initiatief_id)
        if not links:
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
