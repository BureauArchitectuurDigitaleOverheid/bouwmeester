"""Hand every finished turn at speaking to the marking of questions.

The timeline posts a message per turn and the transcription puts the text
under it. This looks, a few times a minute, for turns that are over and
whose text is complete, and has each one read once for questions to the
bewindspersoon (`DebatVraagService.beoordeel_beurt`).

A round of its own, not part of the timeline: reading one turn takes the
model three to fourteen seconds, and the timeline has to say who speaks
within ten.

What a turn is, is not decided here. `load_turns` of the transcription says
which words belong under which message, and this reads exactly those.

A turn is read once, so it is read when its text is final. Around a change
of speaker the voices decide whose a line is, seconds to minutes later, and
a line can go to the turn before or after. A question read under one
speaker and then moved to the other would leave a thread under the wrong
message. So a turn waits for as long as a line can still move into or out
of it; see `rows_in_play`.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.config import get_settings
from bouwmeester.models.debat_sessie import (
    TIJDLIJN_LOOPT,
    DebatOndertitel,
    DebatSessie,
    DebatSpreekbeurt,
)
from bouwmeester.services import debat_direct as dd
from bouwmeester.services import debat_stem as stem
from bouwmeester.services import debat_stemmen_service as stemmen
from bouwmeester.services import tk_activiteit
from bouwmeester.services.debat_kanaal_service import AMSTERDAM
from bouwmeester.services.debat_stemmen_service import (
    AFTER,
    BEFORE,
    WAIT,
)
from bouwmeester.services.debat_tijdlijn_service import (
    END_GRACE,
    GIVE_UP_AFTER,
    LOOKAHEAD,
)
from bouwmeester.services.debat_transcript_service import (
    AFTER_END,
    ORDER,
    Turn,
    _moment,
    load_turns,
)
from bouwmeester.services.debat_vraag_service import (
    UITKOMST_GEMARKEERD,
    Beurt,
    DebatContext,
    DebatVraagService,
    is_bewindspersoon,
)
from bouwmeester.services.debat_vraag_status_service import DebatVraagStatusService
from bouwmeester.services.llm.base import BaseLLMService
from bouwmeester.services.mattermost_service import MattermostService

logger = logging.getLogger(__name__)

# How far around a change of speaker a line can be the other person's, as
# the voices have it.
REACH = max(BEFORE, AFTER)
# How far past the end of a turn the subtitles have to be read before its
# text counts as complete: far enough that every line the voices can still
# give to this turn has been read. From there on it is the lines that say
# whether the turn has to wait (`rows_in_play`), not the clock. This was
# 75 seconds for a while, to give the voices time whether they needed it or
# not; they mostly need less, and now and then minutes.
MARGIN = REACH
# How long a turn waits for a line the voices have not decided about. The
# voices keep trying for ten minutes (`RETRY_FOR`), for a voice that is
# learned late or audio that was away; a thread that comes ten minutes
# after the question is of no use to who has to answer it. Past this the
# turn is read as it is. A line of a turn that was read is not moved any
# more (see `_assign` of the voices), so a late decision cannot leave a
# thread under the wrong speaker: the line stays where the time put it.
NEVER_MOVES_AFTER = timedelta(minutes=3)
# Turns per debate per round. Normally one or two are waiting; this is for
# after the model was away, so that catching up does not hold up the other
# debates or keep the heartbeat silent for minutes.
MAX_TURNS = 10

_HTTP_TIMEOUT = 15.0
# The link to the moment, as the timeline wrote it in the first line.
_MOMENT_LINK = re.compile(r"· \[\d\d:\d\d\]\((https://[^\s()]+)\)")


@dataclass
class VraagTickResult:
    sessies: int = 0
    beoordeeld: int = 0
    vragen: int = 0
    fouten: int = 0
    # False when there was something to read and no model to read it.
    model: bool = True

    def summary(self) -> str:
        if not self.model:
            return "geen taalmodel ingesteld"
        return (
            f"{self.sessies} debatten, {self.beoordeeld} spreekbeurten gelezen, "
            f"{self.vragen} vragen, {self.fouten} fouten"
        )


@dataclass(frozen=True)
class _Waiting:
    """A finished turn that has not been read, and who had the floor."""

    turn: Turn
    floor: Turn | None
    # The first turn of its part: which day's list of speakers applies.
    first: datetime


def moment_url_from_kop(kop: str) -> str | None:
    """The link to the moment of a turn, read back from its first line.

    Building it anew takes the debate from Debat Direct, a download per
    round. The timeline had it when it wrote the message, and this way the
    thread links to exactly what the message links to.
    """
    found = _MOMENT_LINK.search(kop or "")
    return found.group(1) if found else None


def text_is_complete(
    entry: dict,
    next_message: datetime | None,
    part_end: datetime | None,
    now: datetime | None = None,
) -> bool:
    """Whether no new line will be added to a turn.

    `entry` is where the reading of the subtitles of its part stands,
    `next_message` the start of the first message after it, `part_end` the
    end of its part. Without something after it the turn is still going on.
    """
    position = _moment(entry.get("positie"))
    if position is None:
        return False
    # The reading stops as soon as it is past the end of the part, so it
    # never gets a margin beyond it. Past the end is complete.
    if part_end is not None and position > part_end:
        return True
    # And it stops by the clock. The stream ends when the debate does, so
    # the reading may never get past the end at all, and the last turns
    # would wait for a margin that does not come.
    if part_end is not None and now is not None and now > part_end + AFTER_END:
        return True
    if next_message is None:
        return False
    offset = timedelta(milliseconds=entry.get("offset_ms") or 0)
    return position >= next_message + offset + MARGIN


def voices_listen() -> bool:
    """Whether lines are being decided about by voice in this process.

    The same two things the timeline goes by. Without the model no line is
    ever marked as decided, and a turn must not wait for that. As long as
    nobody has looked for the model, at the start of the process, it
    counts as there: the lines kept from before a restart can still move
    once the voices are learned again.
    """
    settings = get_settings()
    if not settings.DEBAT_STEMMEN_ENABLED:
        return False
    return stem.available(settings.DEBAT_STEM_MODEL_PATH) is not False


def rows_in_play(
    turns: list[stemmen.Turn],
    lines: list[tuple[datetime, uuid.UUID | None]],
    now: datetime,
) -> set[uuid.UUID]:
    """The events whose text can still change by a line moving.

    `turns` are the events of one part as the voices see them, `lines` the
    lines of it that are not decided about, each with its moment and the
    event it is under now. Asked of the code that moves them:

    * A line the voices have not looked at yet, because the events around
      it may not all be in, can end up under anything it is near.
    * After that, a line near a change of speaker can go to the nearest
      turn of whoever is around that change, and can leave where it is.
    * A line that is not near a change stays where it is, and so does one
      the voices have given up on.
    """
    found: set[uuid.UUID] = set()
    for start, row_id in lines:
        if now - start > NEVER_MOVES_AFTER:
            continue
        if now - start < WAIT:
            reached = [turn for turn in turns if turn.distance(start) <= REACH]
        else:
            around = stemmen.candidates(turns, start)
            persons = dict.fromkeys(turn.person for turn in around)
            reached = [
                stemmen.nearest(turns, person, start)
                for person in persons
                if person is not None
            ]
            if not reached:
                continue
        found.update(turn.row_id for turn in reached)
        if row_id is not None:
            found.add(row_id)
    return found


class _Pause:
    """How long a debate is left alone after reading a turn failed.

    In the memory of the process: after a restart the first try is free,
    which is what a restart is for. The wait doubles with every failure in
    a row, so a model that is down costs a few calls and not four a minute.
    """

    def __init__(self) -> None:
        self._until: dict[uuid.UUID, datetime] = {}
        self._failures: dict[uuid.UUID, int] = {}

    def waiting(self, sessie_id: uuid.UUID, now: datetime) -> bool:
        until = self._until.get(sessie_id)
        return until is not None and now < until

    def failed(self, sessie_id: uuid.UUID, now: datetime) -> None:
        count = self._failures.get(sessie_id, 0) + 1
        self._failures[sessie_id] = count
        self._until[sessie_id] = now + min(PAUSE_FIRST * 2 ** (count - 1), PAUSE_MAX)

    def succeeded(self, sessie_id: uuid.UUID) -> None:
        self._until.pop(sessie_id, None)
        self._failures.pop(sessie_id, None)

    def reset(self) -> None:
        self._until.clear()
        self._failures.clear()


_pause = _Pause()
# How long one turn may take, model and all. Measured: 3 to 14 seconds.
JUDGE_TIMEOUT = 60.0
# The pauses add up to a quarter of an hour before a turn is given up on.
MAX_ATTEMPTS = 6
PAUSE_FIRST = timedelta(seconds=30)
PAUSE_MAX = timedelta(minutes=5)


class DebatVraagWorker:
    def __init__(
        self,
        session: AsyncSession,
        mattermost: MattermostService | None = None,
        llm: BaseLLMService | None = None,
        contexts: dict[uuid.UUID, DebatContext] | None = None,
    ) -> None:
        self.session = session
        self.mattermost = mattermost or MattermostService(session)
        self.llm = llm
        # What is known about each debate beforehand. Handed in by the
        # loop, so it is asked of the TK API once and not every round.
        self.contexts = contexts if contexts is not None else {}
        # Per day, for the length of one round.
        self._sprekers: dict[str, dict[str, dd.Spreker]] = {}

    async def close(self) -> None:
        await self.mattermost.close()

    async def tick(self, now: datetime | None = None) -> VraagTickResult:
        """Read the turns that have finished since the last round."""
        now = now or datetime.now(UTC)
        result = VraagTickResult()
        await self._reacties()
        # The debates the timeline is following, and for a few hours after
        # their end: that long the timeline keeps them running as well.
        stmt = select(DebatSessie.id).where(
            DebatSessie.channel_id.is_not(None),
            DebatSessie.aanvang.is_not(None),
            DebatSessie.aanvang <= now + LOOKAHEAD,
            DebatSessie.aanvang >= now - GIVE_UP_AFTER - END_GRACE,
            DebatSessie.tijdlijn_status == TIJDLIJN_LOOPT,
        )
        sessie_ids = list((await self.session.execute(stmt)).scalars().all())
        if not sessie_ids:
            return result
        if not await self.mattermost.is_enabled():
            return result

        vragen: DebatVraagService | None = None
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            for sessie_id in sessie_ids:
                result.sessies += 1
                if _pause.waiting(sessie_id, now):
                    continue
                try:
                    waiting = await self._waiting(sessie_id, now)
                    if not waiting:
                        continue
                    if vragen is None:
                        vragen = await self._service()
                    if vragen is None:
                        result.model = False
                        return result
                    await self._read(sessie_id, waiting, vragen, client, now, result)
                except Exception:
                    # One debate that breaks must not stop the others.
                    await self.session.rollback()
                    result.fouten += 1
                    logger.exception("Vragen van sessie %s liepen vast", sessie_id)
        return result

    async def _reacties(self) -> None:
        """Work in what people said became of a question, with a reaction.

        First in the round, before any turn is read: someone who clicks
        waits for this, and reading turns can take a minute. Also for a
        debate that is over, which is when most answers are ticked off; so
        not per debate that is running, but for every markering the
        websocket marked. By the real clock, like those marks.

        A round in which this breaks still reads its turns.
        """
        try:
            ronde = await DebatVraagStatusService(
                self.session, self.mattermost
            ).werk_bij()
        except Exception:
            await self.session.rollback()
            logger.exception("Reacties op vragen niet verwerkt")
            return
        if ronde.gewijzigd or ronde.mislukt:
            logger.info(
                "Reacties op vragen: %d bijgewerkt, %d gewijzigd, %d wachten",
                ronde.bijgewerkt,
                ronde.gewijzigd,
                ronde.mislukt,
            )

    async def _service(self) -> DebatVraagService | None:
        if self.llm is not None:
            return DebatVraagService(self.session, self.mattermost, self.llm)
        return await DebatVraagService.create(self.session, self.mattermost)

    async def _waiting(self, sessie_id: uuid.UUID, now: datetime) -> list[_Waiting]:
        """The turns of a debate that are over, final and not read yet."""
        sessie = (
            await self.session.execute(
                select(DebatSessie.debat_direct_ids, DebatSessie.ondertitels).where(
                    DebatSessie.id == sessie_id
                )
            )
        ).first()
        if sessie is None:
            return []
        parts, ondertitels = list(sessie[0] or []), dict(sessie[1] or {})

        # Every event of the debate in the order of the channel, and where
        # each part ended. A turn is over when a message follows it.
        marks = (
            await self.session.execute(
                select(
                    DebatSpreekbeurt.id,
                    DebatSpreekbeurt.debat_direct_id,
                    DebatSpreekbeurt.event_type,
                    DebatSpreekbeurt.event_start,
                    DebatSpreekbeurt.post_id,
                    DebatSpreekbeurt.object_id,
                )
                .where(DebatSpreekbeurt.sessie_id == sessie_id)
                .order_by(*ORDER)
            )
        ).all()
        next_message: dict[uuid.UUID, datetime] = {}
        ends: dict[str, datetime] = {}
        events: dict[str, list[tuple]] = {}
        previous: uuid.UUID | None = None
        for row_id, debate_id, kind, start, post_id, who in marks:
            events.setdefault(debate_id, []).append((row_id, kind, start, who))
            if kind == dd.EVENT_DEBATE_END:
                ends[debate_id] = start
            if post_id:
                if previous is not None:
                    next_message[previous] = start
                previous = row_id

        # The parts whose lines the voices decide about: with a model, and
        # with audio to listen to. In any other part a line stays where
        # the time put it, and nothing is waited for.
        heard = [
            debate_id
            for debate_id in parts
            if (ondertitels.get(debate_id) or {}).get("audio")
        ]
        open_lines = await self._open_lines(sessie_id, heard, now)

        waiting: list[_Waiting] = []
        for debate_id in parts:
            entry = dict(ondertitels.get(debate_id) or {})
            turns = await load_turns(self.session, sessie_id, debate_id)
            unsettled: set[uuid.UUID] = set()
            if debate_id in open_lines:
                voiced = stemmen.as_turns(events.get(debate_id, []))
                under = stemmen.message_of(voiced, {turn.row_id for turn in turns})
                unsettled = {
                    under[row_id]
                    for row_id in rows_in_play(voiced, open_lines[debate_id], now)
                    if row_id in under
                }
            floor: Turn | None = None
            for turn in turns:
                if turn.closing:
                    # A suspension or the end, with the words of the
                    # chairman under it. Nobody's turn at speaking.
                    continue
                if (
                    turn.beoordeeld_at is None
                    and turn.row_id not in unsettled
                    and text_is_complete(
                        entry, next_message.get(turn.row_id), ends.get(debate_id), now
                    )
                ):
                    waiting.append(_Waiting(turn, floor, turns[0].start))
                if turn.key[0] == dd.EVENT_SPEAKER:
                    floor = turn
        # In the order they were spoken: a question asked again has to
        # find the first time it was asked. A turn that waits for a line
        # does not hold up the ones after it, which can be minutes; a
        # question it repeats from a later turn is then filed under that
        # later one.
        waiting.sort(key=lambda w: w.turn.start)
        return waiting[:MAX_TURNS]

    async def _open_lines(
        self, sessie_id: uuid.UUID, parts: list[str], now: datetime
    ) -> dict[str, list[tuple[datetime, uuid.UUID | None]]]:
        """Per part, the lines the voices have not decided about yet.

        One question for the whole debate, and none at all when the voices
        are not listened to. Normally a handful of lines: the last half
        minute, and what waits for a voice that is not known yet.
        """
        if not parts or not voices_listen():
            return {}
        rows = await self.session.execute(
            select(
                DebatOndertitel.debat_direct_id,
                DebatOndertitel.start,
                DebatOndertitel.spreekbeurt_id,
            )
            .where(
                DebatOndertitel.sessie_id == sessie_id,
                DebatOndertitel.debat_direct_id.in_(parts),
                DebatOndertitel.stem_klaar.is_(False),
                DebatOndertitel.start >= now - NEVER_MOVES_AFTER,
            )
            .order_by(DebatOndertitel.start)
        )
        found: dict[str, list[tuple[datetime, uuid.UUID | None]]] = {}
        for debate_id, start, row_id in rows.all():
            found.setdefault(debate_id, []).append((start, row_id))
        return found

    async def _read(
        self,
        sessie_id: uuid.UUID,
        waiting: list[_Waiting],
        vragen: DebatVraagService,
        client: httpx.AsyncClient,
        now: datetime,
        result: VraagTickResult,
    ) -> None:
        channel_id, activiteit_id, onderwerp = (
            await self.session.execute(
                select(
                    DebatSessie.channel_id,
                    DebatSessie.activiteit_id,
                    DebatSessie.onderwerp,
                ).where(DebatSessie.id == sessie_id)
            )
        ).one()

        for item in waiting:
            turn = item.turn
            tekst = turn.text
            if not tekst:
                # Nothing was said, or nothing was heard. Not a reason to
                # ask the model, and not a reason to look again either.
                await self._mark(turn.row_id, now)
                continue

            sprekers = await self._sprekers_for(client, item.first)
            if sprekers is None:
                # Without the list nobody can tell a member from a
                # minister, and the answers of a minister are not
                # questions. A later round has the list again.
                result.fouten += 1
                return
            kind, who = turn.key
            spreker = sprekers.get(who)
            if spreker is None:
                # Not on the list of Debat Direct: a guest, or a minister
                # the list does not have yet. Whether this is someone who
                # asks or someone who answers cannot be told, so the model
                # is not asked to guess.
                await self._mark(turn.row_id, now)
                continue
            onderbroken = None
            if kind == dd.EVENT_INTERRUPTER and item.floor is not None:
                onderbroken = sprekers.get(item.floor.key[1])
            context = await self._context(sessie_id, activiteit_id, onderwerp, client)
            beurt = Beurt(
                sessie_id=sessie_id,
                spreekbeurt_id=turn.row_id,
                post_id=turn.post_id,
                channel_id=channel_id,
                soort=kind,
                spreker=spreker.label,
                fractie=spreker.fractie,
                start=turn.start,
                moment_url=moment_url_from_kop(turn.kop),
                tekst=tekst,
                is_bewindspersoon=is_bewindspersoon(spreker),
                onderbroken=onderbroken.label if onderbroken else None,
                onderbroken_is_bewindspersoon=bool(
                    onderbroken and is_bewindspersoon(onderbroken)
                ),
            )
            try:
                outcome = await asyncio.wait_for(
                    vragen.beoordeel_beurt(beurt, context), JUDGE_TIMEOUT
                )
                failed = outcome.opnieuw_proberen
            except Exception:
                # Also a model that hangs: the clients wait ten minutes by
                # themselves. And anything that breaks after the model
                # answered, which would otherwise ask it again every round.
                logger.exception("Spreekbeurt %s niet beoordeeld", turn.row_id)
                await self.session.rollback()
                failed = True
            if failed:
                # The turns after this one would find the same, each after
                # its own wait. The debate is left alone for a while, longer
                # each time; a turn that keeps failing is given up on, so
                # that it does not hold up every turn after it.
                result.fouten += 1
                attempts = await self._count_attempt(turn.row_id)
                if attempts >= MAX_ATTEMPTS:
                    logger.warning(
                        "Spreekbeurt %s na %d pogingen overgeslagen",
                        turn.row_id,
                        attempts,
                    )
                    await self._mark(turn.row_id, now)
                _pause.failed(sessie_id, now)
                return
            _pause.succeeded(sessie_id)
            await self._mark(turn.row_id, now)
            result.beoordeeld += 1
            if outcome.uitkomst == UITKOMST_GEMARKEERD:
                result.vragen += len(outcome.markering_ids)

    async def _count_attempt(self, row_id: uuid.UUID) -> int:
        attempts = (
            await self.session.execute(
                update(DebatSpreekbeurt)
                .where(DebatSpreekbeurt.id == row_id)
                .values(beoordeel_pogingen=DebatSpreekbeurt.beoordeel_pogingen + 1)
                .returning(DebatSpreekbeurt.beoordeel_pogingen)
            )
        ).scalar_one()
        await self.session.commit()
        return attempts

    async def _mark(self, row_id: uuid.UUID, now: datetime) -> None:
        await self.session.execute(
            update(DebatSpreekbeurt)
            .where(DebatSpreekbeurt.id == row_id)
            .values(beoordeeld_at=now)
        )
        # Per turn: one that has been read is not read again after a
        # restart halfway through a round.
        await self.session.commit()

    async def _sprekers_for(
        self, client: httpx.AsyncClient, moment: datetime
    ) -> dict[str, dd.Spreker] | None:
        day = moment.astimezone(AMSTERDAM).date()
        key = day.isoformat()
        if key not in self._sprekers:
            try:
                self._sprekers[key] = await dd.fetch_sprekers(client, day)
            except dd.DebatDirectError:
                logger.warning("Sprekers niet te lezen", exc_info=True)
                return None
        return self._sprekers[key]

    async def _context(
        self,
        sessie_id: uuid.UUID,
        activiteit_id: str,
        onderwerp: str,
        client: httpx.AsyncClient,
    ) -> DebatContext:
        if sessie_id in self.contexts:
            return self.contexts[sessie_id]
        try:
            activiteit = await tk_activiteit.fetch_activiteit(activiteit_id, client)
        except tk_activiteit.TkApiError:
            logger.warning("Activiteit %s niet te lezen", activiteit_id, exc_info=True)
            activiteit = None
        if activiteit is None:
            # The subject alone is enough to read a turn by. Not kept, so
            # the next turn asks again for who is at the table.
            return DebatContext(onderwerp=onderwerp)
        self.contexts[sessie_id] = DebatContext.from_activiteit(activiteit)
        return self.contexts[sessie_id]
