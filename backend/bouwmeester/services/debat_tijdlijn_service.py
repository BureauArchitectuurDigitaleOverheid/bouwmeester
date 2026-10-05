"""The timeline: who speaks when, in the channel of a debate.

On the day of a debate this finds it on Debat Direct, puts room and stream
in the channel header, and then posts one message per turn at speaking,
each with a link to that moment in the broadcast. No transcript yet; that is
added to these same messages later.

Runs as ticks from the worker. One tick looks at every debate channel whose
debate is today, and does whatever is next for it. Everything it has done
is in the database, so a restart continues where the last tick stopped.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import case, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.debat_sessie import (
    TIJDLIJN_AFGELAST,
    TIJDLIJN_AFGELOPEN,
    TIJDLIJN_GEKOPPELD,
    TIJDLIJN_LOOPT,
    DebatSessie,
    DebatSpreekbeurt,
)
from bouwmeester.services import debat_direct as dd
from bouwmeester.services.debat_kanaal_service import (
    AMSTERDAM,
    channel_header,
    format_moment,
)
from bouwmeester.services.mattermost_service import MattermostService
from bouwmeester.services.mattermost_utils import (
    escape_mattermost_prose as _escape,
)
from bouwmeester.services.tk_activiteit import (
    STATUS_CANCELLED,
    STATUS_MOVED,
    Activiteit,
    TkApiError,
    fetch_activiteit,
)

logger = logging.getLogger(__name__)

# How long before the start a debate is looked for on Debat Direct. The
# agenda of a day is there the evening before.
LOOKAHEAD = timedelta(hours=14)
# How long after the start a debate that was never found is still looked
# for. Past this it is given up on.
GIVE_UP_AFTER = timedelta(hours=16)
# How often the activiteit and the agenda are read again while waiting, and
# while a debate runs to find a second part after a break.
RECHECK_EVERY = timedelta(minutes=5)
# A debate counts as over this long after its last part ended. Debat Direct
# cuts a plenary debate in two around a break, and the second part only
# appears when it starts.
END_GRACE = timedelta(hours=3)
# Events older than this when the timeline first sees a debate are history:
# the timeline joined a debate that was already running. Posting them would
# put a hundred messages in the channel at once.
BACKLOG_AGE = timedelta(minutes=3)
# The same for a debate the timeline was already following, with more
# patience: after the worker or Debat Direct was away for a while, what was
# missed is history too. Without this half an hour of absence comes back as
# fifty messages in one burst.
GAP_AGE = timedelta(minutes=10)
# A debate is not asked for its events until this long before its planned
# start. Every poll downloads the whole debate, and a debate found the
# evening before would be polled thousands of times for nothing.
POLL_BEFORE_START = timedelta(minutes=15)

_HTTP_TIMEOUT = 15.0
_SPEAKING = (dd.EVENT_SPEAKER, dd.EVENT_INTERRUPTER)

_ACTIVE = (None, TIJDLIJN_GEKOPPELD, TIJDLIJN_LOOPT)


def _hhmm(moment: datetime) -> str:
    return moment.astimezone(AMSTERDAM).strftime("%H:%M")


def _linked_time(debat: dd.DdDebat, event: dd.DdEvent) -> str:
    """The time of an event, as a link to that moment where that is possible."""
    url = dd.moment_url(debat, event)
    tijd = _hhmm(event.start)
    return f"[{tijd}]({url})" if url else tijd


def format_event(
    event: dd.DdEvent,
    debat: dd.DdDebat,
    sprekers: dict[str, dd.Spreker],
    *,
    previous_turn: tuple[str, str] | None = None,
) -> str | None:
    """The message for one event, or ``None`` for an event that gets none.

    One message per turn at speaking. The chairman giving the floor is not
    a turn: in a debate of three hours that is seventy-five messages that
    say nothing. Someone who simply carries on after the chairman said a
    word does not get a second message either: `previous_turn` is the kind
    and the person of the last turn that did get one. The same person in
    another role does, so a speaker who answers an interruption shows up
    again after it.
    """
    if event.type in _SPEAKING:
        if previous_turn == (event.type, event.object_id):
            return None
        spreker = sprekers.get(event.object_id)
        naam = _escape(spreker.label if spreker else "Onbekende spreker")
        regel = f"**{naam}** · {_linked_time(debat, event)}"
        if event.type == dd.EVENT_INTERRUPTER:
            return f"↳ {regel} · interruptie"
        return regel
    if event.type == dd.EVENT_CHAIRMAN_CHANGE:
        spreker = sprekers.get(event.object_id)
        if spreker is None:
            return None
        naam = _escape(spreker.naam)
        return f"_Voorzitter is nu {naam}_ · {_hhmm(event.start)}"
    if event.type == dd.EVENT_DEBATE_START:
        zaal = f" in de {_escape(debat.location_name)}" if debat.location_name else ""
        return f"▶️ **Het debat is begonnen**{zaal} · {_linked_time(debat, event)}"
    if event.type == dd.EVENT_SUSPENDED:
        return f"⏸️ **Geschorst** · {_hhmm(event.start)}"
    if event.type == dd.EVENT_CONTINUED:
        return f"▶️ **Hervat** · {_linked_time(debat, event)}"
    if event.type == dd.EVENT_DEBATE_END:
        return f"⏹️ **Het debat is afgelopen** · {_hhmm(event.start)}"
    return None


@dataclass
class TickResult:
    sessies: int = 0
    gekoppeld: int = 0
    berichten: int = 0
    fouten: int = 0

    def summary(self) -> str:
        return (
            f"{self.sessies} debatten, {self.gekoppeld} gekoppeld, "
            f"{self.berichten} berichten, {self.fouten} fouten"
        )


class DebatTijdlijnService:
    def __init__(
        self, session: AsyncSession, mattermost: MattermostService | None = None
    ) -> None:
        self.session = session
        self.mattermost = mattermost or MattermostService(session)
        # Per day, for the length of one tick.
        self._sprekers: dict[str, dict[str, dd.Spreker]] = {}
        self._agenda: dict[str, list[dd.DdDebat]] = {}
        # Parts the agenda says have started, whatever the planned time.
        self._started: set[str] = set()

    async def close(self) -> None:
        await self.mattermost.close()

    async def tick(self, now: datetime | None = None) -> TickResult:
        """Do what is next for every debate that is on today."""
        now = now or datetime.now(UTC)
        result = TickResult()
        stmt = select(DebatSessie.id).where(
            DebatSessie.channel_id.is_not(None),
            DebatSessie.aanvang.is_not(None),
            DebatSessie.aanvang <= now + LOOKAHEAD,
            DebatSessie.aanvang >= now - GIVE_UP_AFTER - END_GRACE,
            DebatSessie.tijdlijn_status.is_(None)
            | DebatSessie.tijdlijn_status.in_((TIJDLIJN_GEKOPPELD, TIJDLIJN_LOOPT)),
        )
        sessie_ids = list((await self.session.execute(stmt)).scalars().all())
        if not sessie_ids:
            return result
        if not await self.mattermost.is_enabled():
            return result

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            for sessie_id in sessie_ids:
                result.sessies += 1
                try:
                    await self._advance(sessie_id, client, now, result)
                    await self.session.commit()
                except Exception:
                    # One debate that breaks must not stop the others, and
                    # must not stop the next tick from trying again.
                    await self.session.rollback()
                    result.fouten += 1
                    logger.exception("Tijdlijn van sessie %s liep vast", sessie_id)
        return result

    async def _advance(
        self,
        sessie_id: uuid.UUID,
        client: httpx.AsyncClient,
        now: datetime,
        result: TickResult,
    ) -> None:
        sessie = await self.session.get(DebatSessie, sessie_id)
        if sessie is None or sessie.channel_id is None:
            return
        due = (
            sessie.tijdlijn_gecontroleerd_at is None
            or now - sessie.tijdlijn_gecontroleerd_at >= RECHECK_EVERY
        )

        if sessie.tijdlijn_status is None:
            if not due:
                return
            sessie.tijdlijn_gecontroleerd_at = now
            if await self.mattermost.channel_is_gone(sessie.channel_id):
                # Someone archived the channel. Posting into it fails, and
                # a post that fails is retried on every tick.
                logger.info(
                    "Kanaal %s bestaat niet meer; geen tijdlijn", sessie.channel_id
                )
                sessie.tijdlijn_status = TIJDLIJN_AFGELOPEN
                return
            if await self._find_on_debat_direct(sessie, client, now):
                result.gekoppeld += 1
            elif sessie.tijdlijn_status is None and (
                sessie.aanvang and now - sessie.aanvang > GIVE_UP_AFTER
            ):
                # Never found. Say so once, instead of a channel that stays
                # silent without a reason.
                await self.mattermost.send_channel_message(
                    sessie.channel_id,
                    "Ik heb dit debat niet op Debat Direct kunnen vinden, dus "
                    "er komt geen tijdlijn in dit kanaal.",
                )
                sessie.tijdlijn_status = TIJDLIJN_AFGELOPEN
            return

        if due:
            # Look for a later part of the same debate.
            sessie.tijdlijn_gecontroleerd_at = now
            await self._find_more_parts(sessie, client, now)

        await self._post_new_events(sessie, client, now, result)

    async def _read_activiteit(
        self, sessie: DebatSessie, client: httpx.AsyncClient
    ) -> Activiteit | None:
        try:
            return await fetch_activiteit(sessie.activiteit_id, client)
        except TkApiError:
            logger.warning(
                "Activiteit %s niet opnieuw te lezen",
                sessie.activiteit_id,
                exc_info=True,
            )
            return None

    def _as_activiteit(self, sessie: DebatSessie) -> Activiteit:
        """What the sessie remembers, for when the TK API cannot be read."""
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

    async def _agenda_for(
        self, client: httpx.AsyncClient, moment: datetime
    ) -> list[dd.DdDebat]:
        day = moment.astimezone(AMSTERDAM).date()
        key = day.isoformat()
        if key not in self._agenda:
            self._agenda[key] = await dd.fetch_agenda(client, day)
        return self._agenda[key]

    async def _find_on_debat_direct(
        self, sessie: DebatSessie, client: httpx.AsyncClient, now: datetime
    ) -> bool:
        """Read the appointment again and look for it on Debat Direct.

        The appointment is read again because it changes: of 250 measured
        activiteiten 14 were cancelled and 11 moved after the convocatie.
        A cancelled debate is said so in the channel, instead of waiting
        for a stream that never comes.
        """
        activiteit = await self._read_activiteit(sessie, client)
        if activiteit is not None:
            if activiteit.status in (STATUS_CANCELLED, STATUS_MOVED):
                wat = (
                    "geannuleerd"
                    if activiteit.status == STATUS_CANCELLED
                    else "verplaatst; de nieuwe datum komt als een nieuwe vergadering"
                )
                await self.mattermost.send_channel_message(
                    sessie.channel_id, f"⚠️ Dit debat is {wat}."
                )
                sessie.tijdlijn_status = TIJDLIJN_AFGELAST
                return False
            if activiteit.aanvang and activiteit.aanvang != sessie.aanvang:
                sessie.aanvang = activiteit.aanvang
        else:
            activiteit = self._as_activiteit(sessie)

        if activiteit.aanvang is None:
            return False
        try:
            agenda = await self._agenda_for(client, activiteit.aanvang)
        except dd.DebatDirectError:
            logger.warning("Agenda van Debat Direct niet te lezen", exc_info=True)
            return False
        parts = dd.match_debates(activiteit, agenda)
        if not parts:
            return False

        sessie.debat_direct_ids = [part.id for part in parts]
        sessie.tijdlijn_status = TIJDLIJN_GEKOPPELD
        first = parts[0]
        header = channel_header(
            activiteit, zaal=first.location_name, stream_url=dd.debate_url(first)
        )
        if not await self.mattermost.update_channel(sessie.channel_id, header=header):
            logger.warning("Header van kanaal %s niet bijgewerkt", sessie.channel_id)
        logger.info(
            "Debat %s gekoppeld aan Debat Direct: %s (%s)",
            sessie.onderwerp,
            ", ".join(sessie.debat_direct_ids),
            format_moment(activiteit),
        )
        return True

    async def _find_more_parts(
        self, sessie: DebatSessie, client: httpx.AsyncClient, now: datetime
    ) -> None:
        if sessie.aanvang is None:
            return
        try:
            agenda = await self._agenda_for(client, sessie.aanvang)
        except dd.DebatDirectError:
            return
        known = list(sessie.debat_direct_ids or [])
        # A debate can start well before its planned time: plenary items
        # were measured up to 38 minutes early. The agenda says so, and it
        # is read here anyway.
        for part in agenda:
            start = dd.start_of(part)
            if part.id in known and (
                part.started_at is not None or (start is not None and start <= now)
            ):
                self._started.add(part.id)
        new = [p.id for p in dd.later_parts(sessie.onderwerp, known, agenda)]
        if new:
            # A new list, not an append: a JSON column only notices a
            # change when the value itself is replaced.
            sessie.debat_direct_ids = [*known, *new]
            logger.info("Vervolg van debat %s gevonden: %s", sessie.onderwerp, new)

    async def _sprekers_for(
        self, client: httpx.AsyncClient, debat: dd.DdDebat
    ) -> dict[str, dd.Spreker]:
        moment = debat.started_at or debat.starts_at
        if moment is None:
            return {}
        day = moment.astimezone(AMSTERDAM).date()
        key = day.isoformat()
        if key not in self._sprekers:
            try:
                self._sprekers[key] = await dd.fetch_sprekers(client, day)
            except dd.DebatDirectError:
                # Without names the timeline still says that someone spoke,
                # and when. Not cached, so the next tick tries again.
                logger.warning("Sprekers niet te lezen", exc_info=True)
                return {}
        return self._sprekers[key]

    async def _post_new_events(
        self,
        sessie: DebatSessie,
        client: httpx.AsyncClient,
        now: datetime,
        result: TickResult,
    ) -> None:
        rows = (
            await self.session.execute(
                select(
                    DebatSpreekbeurt.debat_direct_id,
                    DebatSpreekbeurt.event_type,
                    DebatSpreekbeurt.event_start,
                    DebatSpreekbeurt.object_id,
                    DebatSpreekbeurt.post_id,
                )
                .where(DebatSpreekbeurt.sessie_id == sessie.id)
                # Within one second the same order as the feed is read in:
                # a resumption comes before whoever speaks after it.
                .order_by(
                    DebatSpreekbeurt.event_start,
                    case((DebatSpreekbeurt.event_type.in_(_SPEAKING), 1), else_=0),
                )
            )
        ).all()
        seen = {(r[0], r[1], r[2], r[3]) for r in rows}
        ended = {r[0] for r in rows if r[1] == dd.EVENT_DEBATE_END}
        started_parts = {r[0] for r in rows}
        # The last turn that became a message, per part: a speaker who
        # carries on does not get a second one.
        last_turn: dict[str, tuple[str, str]] = {}
        for r in rows:
            if not r[4]:
                if r[1] in _SPEAKING and last_turn.get(r[0]) != (r[1], r[3]):
                    # Someone else spoke without a message: that only
                    # happens in a stretch the timeline missed. Who spoke
                    # before it says nothing about who speaks after it.
                    last_turn.pop(r[0], None)
                continue
            if r[1] in _SPEAKING:
                last_turn[r[0]] = (r[1], r[3])
            else:
                # A break or a new chairman was posted in between: whoever
                # speaks next is a new turn, also if it is the same person.
                last_turn.pop(r[0], None)

        last_end: datetime | None = None
        for debate_id in list(sessie.debat_direct_ids or []):
            if debate_id in ended:
                end_rows = [
                    r[2]
                    for r in rows
                    if r[0] == debate_id and r[1] == dd.EVENT_DEBATE_END
                ]
                last_end = max([last_end, *end_rows]) if last_end else max(end_rows)
                continue
            if (
                debate_id not in started_parts
                and debate_id not in self._started
                and sessie.aanvang is not None
                and now < sessie.aanvang - POLL_BEFORE_START
            ):
                continue
            try:
                debat = await dd.fetch_debate(client, debate_id)
            except dd.DebatDirectError:
                logger.warning("Debat %s niet te lezen", debate_id, exc_info=True)
                continue
            if debat is None or not debat.events:
                continue

            new = [
                e
                for e in debat.events
                if (debate_id, e.type, e.start, e.object_id) not in seen
            ]
            if not new:
                continue
            sprekers = await self._sprekers_for(client, debat)

            joining = debate_id not in started_parts
            too_old = GAP_AGE
            if joining and not await self._was_there_before(sessie.id, debat):
                too_old = BACKLOG_AGE
            old = [e for e in new if now - e.start > too_old]
            new = [e for e in new if now - e.start <= too_old]
            # Old and from before something already seen: the feed added or
            # corrected an event afterwards. Nothing was missed, so nothing
            # is said. Old and after everything seen: the timeline was away.
            last_seen = max((r[2] for r in rows if r[0] == debate_id), default=None)
            missed = [e for e in old if last_seen is None or e.start > last_seen]
            beurten = sum(1 for e in missed if e.type in _SPEAKING)
            is_over = any(e.type == dd.EVENT_DEBATE_END for e in missed)
            if missed and (beurten or is_over):
                url = dd.debate_url(debat)
                waar = f"[Debat Direct]({url})" if url else "Debat Direct"
                aantal = "1 spreekbeurt" if beurten == 1 else f"{beurten} spreekbeurten"
                if joining:
                    staan = "staat" if beurten == 1 else "staan"
                    melding = (
                        f"🎧 Ik luister mee vanaf {_hhmm(now)}. Het debat "
                        f"was toen al bezig; de {aantal} daarvoor {staan} op {waar}."
                    )
                else:
                    melding = (
                        f"⏭️ Ik was er even niet. Wat er tussen "
                        f"{_hhmm(missed[0].start)} en {_hhmm(missed[-1].start)} "
                        f"gebeurde ({aantal}) staat op {waar}."
                    )
                if is_over:
                    melding += " Het debat is inmiddels afgelopen."
                post_id = await self.mattermost.send_channel_message(
                    sessie.channel_id, melding
                )
                if not post_id:
                    # Nothing is remembered before the channel has been told.
                    # Mattermost being down looks the same as having been
                    # away: what waits grows old. Remembering it here would
                    # drop it without a word.
                    logger.warning(
                        "Melding over gemist deel voor %s niet geplaatst", debate_id
                    )
                    result.fouten += 1
                    continue
                result.berichten += 1
                # What came before the gap says nothing about who speaks
                # after it.
                last_turn.pop(debate_id, None)
            for event in old:
                await self._remember(sessie.id, debate_id, event, None)
                if event.type == dd.EVENT_DEBATE_END:
                    ended.add(debate_id)
                    last_end = max(last_end, event.start) if last_end else event.start
            if old:
                # Commit the history before going on: a crash after this
                # must not make the next tick announce it again.
                await self.session.commit()

            for event in new:
                tekst = format_event(
                    event,
                    debat,
                    sprekers,
                    previous_turn=last_turn.get(debate_id),
                )
                post_id = None
                if tekst:
                    post_id = await self.mattermost.send_channel_message(
                        sessie.channel_id, tekst
                    )
                    if not post_id:
                        # Not remembered, so the next tick tries it again.
                        # Stop here to keep the order of the debate.
                        logger.warning(
                            "Tijdlijnbericht voor %s niet geplaatst", debate_id
                        )
                        # Counted, so the heartbeat shows a timeline that
                        # is stuck instead of "ok".
                        result.fouten += 1
                        break
                    result.berichten += 1
                    if event.type in _SPEAKING:
                        last_turn[debate_id] = (event.type, event.object_id)
                    else:
                        last_turn.pop(debate_id, None)
                await self._remember(sessie.id, debate_id, event, post_id)
                # Per event: a message that is in the channel has to be in
                # the database, or a restart posts it a second time.
                await self.session.commit()
                if event.type == dd.EVENT_DEBATE_END:
                    ended.add(debate_id)
                    last_end = max(last_end, event.start) if last_end else event.start

            if sessie.tijdlijn_status == TIJDLIJN_GEKOPPELD:
                sessie.tijdlijn_status = TIJDLIJN_LOOPT

        parts = list(sessie.debat_direct_ids or [])
        if parts and all(p in ended for p in parts) and last_end is not None:
            if now - last_end > END_GRACE:
                sessie.tijdlijn_status = TIJDLIJN_AFGELOPEN

    async def _was_there_before(self, sessie_id: uuid.UUID, debat: dd.DdDebat) -> bool:
        """Whether the channel existed before this part of the debate began.

        Then the timeline did not join late: it only saw the start late,
        at most one round of reading the agenda. That gets the patience of
        a gap, not the short one for a channel made halfway through.
        """
        start = dd.start_of(debat)
        if start is None:
            return False
        created = await self.session.scalar(
            select(DebatSessie.created_at).where(DebatSessie.id == sessie_id)
        )
        return created is not None and created <= start

    async def _remember(
        self,
        sessie_id: uuid.UUID,
        debate_id: str,
        event: dd.DdEvent,
        post_id: str | None,
    ) -> None:
        stmt = (
            insert(DebatSpreekbeurt)
            .values(
                sessie_id=sessie_id,
                debat_direct_id=debate_id,
                event_type=event.type,
                event_start=event.start,
                object_id=event.object_id,
                post_id=post_id,
            )
            .on_conflict_do_nothing(constraint="uq_debat_spreekbeurt_event")
        )
        await self.session.execute(stmt)
