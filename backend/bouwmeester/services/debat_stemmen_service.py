"""Put the lines around a change of speaker with whose voice they are.

A line of subtitle is first filed under the last event that began before
it. The events of Debat Direct are seconds off from the moment someone
starts to speak (measured on 5 October 2026: up to 13 seconds late and 7
seconds early, never corrected afterwards), so the first sentences of an
answer end up under the interruption before it.

Here the audio decides. Every round, for one part of a debate:

1. Learn. The voice of a person is learned from the debate itself: from
   the lines well inside their own turns, away from the edges where the
   events cannot be trusted.
2. Decide. A line near a change of speaker is compared with the voices of
   the people around that change, and goes to the turn of who it sounds
   like. A line far from any change is left alone and never listened to.

A line that moves takes its text along: the text of both turns is made
anew from their lines, and the transcript writes both messages again.

Everything here is bounded per round and may fail. A line the voices did
not decide about stays where the time put it.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx
import numpy as np
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.debat_sessie import (
    TOEWIJZING_STEM,
    DebatOndertitel,
    DebatSpreekbeurt,
)
from bouwmeester.services import debat_audio as audio
from bouwmeester.services import debat_direct as dd
from bouwmeester.services.debat_stem import (
    VOICES,
    Embedder,
    SessieVoices,
    VoiceCache,
    choose,
)
from bouwmeester.services.debat_transcript_service import (
    AFTER_END,
    ORDER,
    derive_text,
    load_turns,
)

logger = logging.getLogger(__name__)

# The events that say a person has the floor, and whose voice can be heard.
_VOICED = (dd.EVENT_SPEAKER, dd.EVENT_INTERRUPTER, dd.EVENT_CHAIRMAN)

# How far around the event of a change of speaker a line can be the other
# person's. The events were measured up to 13 seconds late and up to 7
# seconds early; a second or two more on either side, for a line that
# begins just before.
BEFORE = timedelta(seconds=14)
AFTER = timedelta(seconds=9)
# A voice is learned from inside a turn, this far from its start and from
# the next event: outside it, the other person may be the one speaking.
EDGE_IN = timedelta(seconds=6)
EDGE_OUT = timedelta(seconds=14)
# For a turn that is still going on, the next event is taken to be this
# long ago at the latest: the feed shows a change within nine seconds, and
# this leaves room for a round that took long.
OPEN_SLACK = timedelta(seconds=20)
# A voice is learned from pieces of this length: lines that follow each
# other. Shorter says little, longer adds little and costs more.
CLIP_MIN = timedelta(seconds=4)
CLIP_MAX = timedelta(seconds=8)
CLIP_GAP = timedelta(seconds=1.5)
# Pieces per person per debate. The mean hardly moves after this many, and
# it bounds the work for someone who speaks for an hour.
MAX_CLIPS = 8
# An event followed this soon by another one of the same person was a slip
# of whoever enters them: measured twice in fifteen events, one and two
# seconds apart.
SUPERSEDED = timedelta(seconds=5)
# What is listened to for one line: the line with a little air around it,
# and at least this long, because one word says too little.
LINE_PAD = timedelta(seconds=0.2)
LINE_MIN = timedelta(seconds=1.6)
# A line is not judged before the events around it can be in: an event up
# to 14 seconds after it, shown by the feed up to 9 seconds later.
WAIT = timedelta(seconds=30)
# How long a line waits for a voice that is not known yet. After this it
# stays where the time put it.
RETRY_FOR = timedelta(minutes=10)
# After audio that could not be read, how long it is left alone. A
# server that is down takes its time to say so, and the timeline waits
# for every request that is made: with a few debates at once, a shorter
# pause than this is over before the round is.
AUDIO_RETRY = timedelta(minutes=5)
# The server keeps audio for about fifty minutes.
AUDIO_KEEPS = timedelta(minutes=45)
# Per round, over all debates: how many seconds of sound are turned into
# vectors. A second of sound takes about 55 ms on one core (measured: 114
# ms for 2 seconds, 651 ms for 12), so this is under three seconds of work
# at worst, and only while catching up: a debate that is being followed
# needs a few lines per round. A debate gets its share, with a floor so
# that many debates at once still each make progress.
SOUND_PER_TICK = 48.0
SOUND_PER_SESSIE_MIN = 12.0


@dataclass
class Budget:
    """What one debate may still spend this round."""

    # Seconds of sound to turn into vectors.
    seconds: float
    # Audio segments to ask the server for. A segment is 3.84 seconds;
    # twice what the sound needs, for pieces that straddle two.
    segments: int

    @classmethod
    def share(cls, sessies: int) -> Budget:
        seconds = max(SOUND_PER_SESSIE_MIN, SOUND_PER_TICK / max(sessies, 1))
        return cls(seconds, 2 * round(seconds / audio.SEGMENT_SECONDS) + 2)


@dataclass(frozen=True)
class Turn:
    """An event of the timeline, as far as the voices are concerned."""

    row_id: uuid.UUID
    start: datetime
    # The moment of the event after it; None for the last one.
    end: datetime | None
    # Who has the floor, or None for an event that is not a person
    # speaking: a suspension, a resumption, the start.
    person: str | None
    # Whether this is the end of the part.
    closes: bool = False

    def distance(self, moment: datetime) -> timedelta:
        """How far a moment is from this turn; zero inside it."""
        if moment < self.start:
            return self.start - moment
        if self.end is not None and moment >= self.end:
            return moment - self.end
        return timedelta(0)


@dataclass(frozen=True)
class Line:
    id: uuid.UUID
    start: datetime
    end: datetime
    row_id: uuid.UUID | None
    done: bool


def as_turns(rows: Sequence[tuple[uuid.UUID, str, datetime, str | None]]) -> list[Turn]:
    """The events of one part as the voices see them.

    `rows` are (id, kind, moment, who) in the order of the timeline. Also
    for whoever wants to know where a line can still go: asked of the same
    turns, `candidates` and `nearest` give the answer the voices will give.
    """
    return [
        Turn(
            row_id,
            start,
            rows[index + 1][2] if index + 1 < len(rows) else None,
            (who or None) if kind in _VOICED else None,
            kind == dd.EVENT_DEBATE_END,
        )
        for index, (row_id, kind, start, who) in enumerate(rows)
    ]


def message_of(
    turns: Sequence[Turn], messages: Collection[uuid.UUID]
) -> dict[uuid.UUID, uuid.UUID]:
    """Per event, the message its lines are shown under.

    `messages` are the events that are a message, as `load_turns` names
    them. What follows a message belongs under it until the next one: the
    chairman saying a word, the same speaker carrying on. An event before
    the first message is under none.
    """
    found: dict[uuid.UUID, uuid.UUID] = {}
    current: uuid.UUID | None = None
    for turn in turns:
        if turn.row_id in messages:
            current = turn.row_id
        if current is not None:
            found[turn.row_id] = current
    return found


def candidates(turns: list[Turn], moment: datetime) -> list[Turn]:
    """The turns a line at `moment` can belong to, going by the voices.

    Those on either side of every change of speaker the line is near. A
    change is two turns after each other of two different persons. Empty
    for a line that is not near one.
    """
    found: list[Turn] = []
    for before, after in zip(turns, turns[1:], strict=False):
        if before.person is None or after.person is None:
            continue
        if before.person == after.person:
            continue
        if after.start - BEFORE <= moment <= after.start + AFTER:
            for turn in (before, after):
                if turn not in found:
                    found.append(turn)
    return found


def nearest(turns: list[Turn], person: str, moment: datetime) -> Turn:
    """The turn of this person a line at `moment` goes to: the nearest.

    Of all their turns, not only the ones next to the change: who is given
    the floor often gets two events a second apart, an interruption and
    then a turn, and a line well inside the second one belongs there. The
    first of such a pair is passed over. It lasts too short to hold a line,
    and what was said just before it belongs with what follows.
    """
    own = [
        turn
        for index, turn in enumerate(turns)
        if turn.person == person and not _superseded(turns, index)
    ]
    return min(own, key=lambda turn: (turn.distance(moment), turn.start))


def _superseded(turns: list[Turn], index: int) -> bool:
    turn = turns[index]
    return (
        index + 1 < len(turns)
        and turns[index + 1].person == turn.person
        and turns[index + 1].start - turn.start < SUPERSEDED
    )


def clips(
    lines: list[Line], start: datetime, end: datetime
) -> list[tuple[datetime, datetime]]:
    """Pieces to learn a voice from: runs of lines between two moments."""
    found: list[tuple[datetime, datetime]] = []
    current: tuple[datetime, datetime] | None = None
    for line in lines:
        if line.start < start or line.end > end:
            continue
        if (
            current is not None
            and line.start - current[1] <= CLIP_GAP
            and line.end - current[0] <= CLIP_MAX
        ):
            current = (current[0], line.end)
            continue
        if current is not None and current[1] - current[0] >= CLIP_MIN:
            found.append(current)
        current = (line.start, min(line.end, line.start + CLIP_MAX))
    if current is not None and current[1] - current[0] >= CLIP_MIN:
        found.append(current)
    return found


class DebatStemmen:
    def __init__(
        self,
        session: AsyncSession,
        embedder: Embedder,
        budget: Budget,
        cache: VoiceCache = VOICES,
    ) -> None:
        self.session = session
        self.embedder = embedder
        self.budget = budget
        self.cache = cache
        # How many lines went to another turn in the part being done.
        self.moved = 0
        # The part being done, and the events of it whose message has been
        # read for questions. Looked up when a line is about to move.
        self._part: tuple[uuid.UUID, str] | None = None
        self._read: set[uuid.UUID] | None = None

    async def update(
        self,
        sessie_id: uuid.UUID,
        debate_id: str,
        audio_url: str,
        client: httpx.AsyncClient,
        now: datetime,
    ) -> None:
        """Learn and decide for one part of a debate."""
        self._part, self._read = (sessie_id, debate_id), None
        lines = await self._lines(sessie_id, debate_id, now)
        # A line that waited long enough stays where it is, also when the
        # voices cannot be used at all.
        expired = [
            line for line in lines if not line.done and now - line.start > RETRY_FOR
        ]
        await self._settle([line.id for line in expired])
        # When nothing was said lately the voices are not counted as used,
        # so that they are forgotten when that goes on.
        lately = any(now - line.start <= RETRY_FOR for line in lines)
        turns = await self._turns(sessie_id, debate_id) if lately else []
        # A part that has ended gets no new lines. Once the ones it has
        # are decided about there is nothing to learn a voice for, and no
        # audio is asked for any more.
        waiting = any(not line.done and now - line.start <= RETRY_FOR for line in lines)
        ended = [turn.start for turn in turns if turn.closes]
        busy = lately and (waiting or not ended or now <= max(ended) + AFTER_END)
        held = self.cache.of(sessie_id, now) if busy else self.cache.peek(sessie_id)
        if held is not None:
            for line in expired:
                held.lines.pop(line.id, None)
            # And what was kept for a line somebody else marked as decided
            # in the meantime: the marking does, for the lines of an
            # answer it reads while it goes on. Nobody asks for it again.
            waits = {line.id for line in lines if not line.done}
            for line_id in [kept for kept in held.lines if kept not in waits]:
                del held.lines[line_id]
        if held is None or not busy:
            return
        if held.retry_at is not None and now < held.retry_at:
            return
        known = held.segments.setdefault(audio_url, set())
        oldest = audio.datetime_to_ticks(now - AUDIO_KEEPS)
        known.difference_update({name for name in known if name < oldest})
        reach = audio.Reach(client, audio_url, known, max_segments=self.budget.segments)
        self.moved = 0
        try:
            await self._learn(held, reach, turns, lines, now)
            await self._decide(held, reach, turns, lines, now)
        except audio.AudioError as exc:
            # Said once and then left alone for a while. Only what kind of
            # error: nothing of what was fetched goes into a log.
            held.retry_at = now + AUDIO_RETRY
            logger.warning(
                "Audio van %s niet te lezen (%s); regels blijven op tijd bij "
                "een spreker",
                debate_id,
                type(exc).__name__,
            )
        finally:
            self.budget.segments = reach.left
            if self.moved:
                logger.info(
                    "%d regels van %s op stem bij een andere spreekbeurt gezet",
                    self.moved,
                    debate_id,
                )

    async def _hear(
        self, reach: audio.Reach, start: datetime, end: datetime
    ) -> np.ndarray | None:
        """The sound between two moments; ``None`` when it is not there."""
        if self.budget.seconds <= 0:
            raise audio.BudgetError("Genoeg geluisterd voor deze ronde")
        return await reach.samples(start, end)

    async def _lines(
        self, sessie_id: uuid.UUID, debate_id: str, now: datetime
    ) -> list[Line]:
        """The lines that can still matter: not done, or still to be heard."""
        rows = await self.session.execute(
            select(
                DebatOndertitel.id,
                DebatOndertitel.start,
                DebatOndertitel.einde,
                DebatOndertitel.spreekbeurt_id,
                DebatOndertitel.stem_klaar,
            )
            .where(
                DebatOndertitel.sessie_id == sessie_id,
                DebatOndertitel.debat_direct_id == debate_id,
                or_(
                    DebatOndertitel.stem_klaar.is_(False),
                    DebatOndertitel.start >= now - AUDIO_KEEPS,
                ),
            )
            .order_by(DebatOndertitel.start)
        )
        return [Line(*row) for row in rows.all()]

    async def _turns(self, sessie_id: uuid.UUID, debate_id: str) -> list[Turn]:
        rows = (
            await self.session.execute(
                select(
                    DebatSpreekbeurt.id,
                    DebatSpreekbeurt.event_type,
                    DebatSpreekbeurt.event_start,
                    DebatSpreekbeurt.object_id,
                )
                .where(
                    DebatSpreekbeurt.sessie_id == sessie_id,
                    DebatSpreekbeurt.debat_direct_id == debate_id,
                )
                .order_by(*ORDER)
            )
        ).all()
        return as_turns([tuple(row) for row in rows])

    async def _was_read(self, turns: list[Turn], row_ids: set[uuid.UUID]) -> bool:
        """Whether one of these events is under a message that was read.

        A turn is read for questions once, and each question is a thread
        under its message with the words as they stood. The marking waits
        for the lines around a turn to be decided about, so this is only
        true when the two disagreed: audio that appeared after the turn was
        read, or a second worker during a deploy.
        """
        if self._read is None:
            assert self._part is not None
            messages = await load_turns(self.session, *self._part)
            under = message_of(turns, {m.row_id for m in messages})
            read = {m.row_id for m in messages if m.beoordeeld_at is not None}
            self._read = {row for row, message in under.items() if message in read}
        return not self._read.isdisjoint(row_ids)

    async def _embed(self, samples: np.ndarray) -> np.ndarray | None:
        self.budget.seconds -= len(samples) / audio.SAMPLE_RATE
        return await asyncio.to_thread(self.embedder.embed, samples)

    async def _learn(
        self,
        held: SessieVoices,
        reach: audio.Reach,
        turns: list[Turn],
        lines: list[Line],
        now: datetime,
    ) -> None:
        # A third of the round at most, so that deciding is not kept
        # waiting by someone who has a lot to be learned from.
        quota = self.budget.seconds / 3
        by_row: dict[uuid.UUID, list[Line]] = {}
        for line in lines:
            if line.row_id is not None and now - line.start <= AUDIO_KEEPS:
                by_row.setdefault(line.row_id, []).append(line)
        # The newest turns first: those are the people speaking now.
        for turn in reversed(turns):
            if turn.person is None or turn.row_id not in by_row:
                continue
            inside = (
                turn.start + EDGE_IN,
                (turn.end or now - OPEN_SLACK) - EDGE_OUT,
            )
            for start, end in clips(by_row[turn.row_id], *inside):
                voice = held.voices.get(turn.person)
                if voice is not None and voice.count >= MAX_CLIPS:
                    break
                if start in held.gone or (voice is not None and start in voice.clips):
                    continue
                if quota <= 0:
                    return
                if not await reach.has(end):
                    continue
                try:
                    samples = await self._hear(reach, start, end)
                except audio.BudgetError:
                    # The rest is for the next round.
                    return
                if samples is None:
                    held.gone.add(start)
                    continue
                quota -= len(samples) / audio.SAMPLE_RATE
                vector = await self._embed(samples)
                if vector is None:
                    held.gone.add(start)
                    continue
                held.learn(turn.person, vector, start)

    async def _decide(
        self,
        held: SessieVoices,
        reach: audio.Reach,
        turns: list[Turn],
        lines: list[Line],
        now: datetime,
    ) -> None:
        for line in lines:
            if line.done or now - line.start > RETRY_FOR:
                continue
            if now - line.start < WAIT:
                # And every line after it is younger still.
                break
            around = candidates(turns, line.start)
            if not around:
                await self._settle([line.id])
                continue
            persons = list(dict.fromkeys(turn.person for turn in around))
            voices = {p: held.voices[p] for p in persons if p in held.voices}
            if not voices:
                continue
            vector = held.lines.get(line.id)
            if vector is None:
                # Never more than a clip: a line with a wrong end would
                # otherwise be fetched and embedded for a minute and a
                # half, and the memory that takes is not given back.
                end = (
                    min(max(line.end, line.start + LINE_MIN), line.start + CLIP_MAX)
                    + LINE_PAD
                )
                if not await reach.has(end):
                    # The audio runs behind the room. Every line after
                    # this one is younger still.
                    break
                try:
                    samples = await self._hear(reach, line.start - LINE_PAD, end)
                except audio.BudgetError:
                    # The rest is for the next round.
                    break
                if samples is None:
                    # The server does not have it any more.
                    await self._settle([line.id])
                    continue
                vector = await self._embed(samples)
                if vector is None:
                    await self._settle([line.id])
                    continue
                held.lines[line.id] = vector
            person = choose(
                {p: voice.score(vector) for p, voice in voices.items()},
                [p for p in persons if p not in voices],
            )
            if person is None:
                # Not clear, or a voice still unknown. Looked at again on
                # a later round, when more may have been learned.
                continue
            target = nearest(turns, person, line.start)
            held.lines.pop(line.id, None)
            if target.row_id != line.row_id and await self._was_read(
                turns, {target.row_id, line.row_id} - {None}
            ):
                # A line that moves now would take a question away from
                # under its thread, or put one in a turn nobody reads
                # again. A line under the wrong speaker is the smaller
                # mistake: it stays.
                await self._settle([line.id])
                continue
            await self._assign(line, target.row_id)

    async def _assign(self, line: Line, row_id: uuid.UUID) -> bool:
        """Keep what the voices decided. ``True`` when the line moved."""
        result = await self.session.execute(
            update(DebatOndertitel)
            # Not a line another worker has decided about in the meantime:
            # one decision per line, and the text follows from the lines.
            .where(DebatOndertitel.id == line.id, DebatOndertitel.stem_klaar.is_(False))
            .values(spreekbeurt_id=row_id, toewijzing=TOEWIJZING_STEM, stem_klaar=True)
        )
        if not result.rowcount or row_id == line.row_id:
            return False
        await derive_text(self.session, {row_id, line.row_id} - {None})
        self.moved += 1
        return True

    async def _settle(self, line_ids: list[uuid.UUID]) -> None:
        """These lines stay where they are; they are not looked at again."""
        if not line_ids:
            return
        await self.session.execute(
            update(DebatOndertitel)
            .where(DebatOndertitel.id.in_(line_ids))
            .values(stem_klaar=True)
        )
