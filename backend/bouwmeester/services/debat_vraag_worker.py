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
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.debat_sessie import (
    TIJDLIJN_LOOPT,
    DebatSessie,
    DebatSpreekbeurt,
)
from bouwmeester.services import debat_direct as dd
from bouwmeester.services import tk_activiteit
from bouwmeester.services.debat_kanaal_service import AMSTERDAM
from bouwmeester.services.debat_tijdlijn_service import (
    END_GRACE,
    GIVE_UP_AFTER,
    LOOKAHEAD,
)
from bouwmeester.services.debat_transcript_service import (
    _ORDER,
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
from bouwmeester.services.llm.base import BaseLLMService
from bouwmeester.services.mattermost_service import MattermostService

logger = logging.getLogger(__name__)

# How far past the end of a turn the subtitles have to be read before its
# text counts as complete. A line is filed under the turn it starts in, and
# the moment of an event is not exact to the second.
MARGIN = timedelta(seconds=10)
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
) -> bool:
    """Whether nothing more will be added to a turn.

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
    if next_message is None:
        return False
    offset = timedelta(milliseconds=entry.get("offset_ms") or 0)
    return position >= next_message + offset + MARGIN


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
                try:
                    waiting = await self._waiting(sessie_id)
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

    async def _service(self) -> DebatVraagService | None:
        if self.llm is not None:
            return DebatVraagService(self.session, self.mattermost, self.llm)
        return await DebatVraagService.create(self.session, self.mattermost)

    async def _waiting(self, sessie_id: uuid.UUID) -> list[_Waiting]:
        """The turns of a debate that are over and have not been read."""
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

        # Every message of the debate in the order of the channel, and
        # where each part ended. A turn is over when a message follows it.
        marks = (
            await self.session.execute(
                select(
                    DebatSpreekbeurt.id,
                    DebatSpreekbeurt.debat_direct_id,
                    DebatSpreekbeurt.event_type,
                    DebatSpreekbeurt.event_start,
                    DebatSpreekbeurt.post_id,
                )
                .where(
                    DebatSpreekbeurt.sessie_id == sessie_id,
                    or_(
                        DebatSpreekbeurt.post_id.is_not(None),
                        DebatSpreekbeurt.event_type == dd.EVENT_DEBATE_END,
                    ),
                )
                .order_by(*_ORDER)
            )
        ).all()
        next_message: dict[uuid.UUID, datetime] = {}
        ends: dict[str, datetime] = {}
        previous: uuid.UUID | None = None
        for row_id, debate_id, kind, start, post_id in marks:
            if kind == dd.EVENT_DEBATE_END:
                ends[debate_id] = start
            if post_id:
                if previous is not None:
                    next_message[previous] = start
                previous = row_id

        waiting: list[_Waiting] = []
        for debate_id in parts:
            entry = dict(ondertitels.get(debate_id) or {})
            turns = await load_turns(self.session, sessie_id, debate_id)
            floor: Turn | None = None
            for turn in turns:
                if turn.beoordeeld_at is None and text_is_complete(
                    entry, next_message.get(turn.row_id), ends.get(debate_id)
                ):
                    waiting.append(_Waiting(turn, floor, turns[0].start))
                if turn.key[0] == dd.EVENT_SPEAKER:
                    floor = turn
        # In the order they were spoken: a question asked again has to
        # find the first time it was asked.
        waiting.sort(key=lambda w: w.turn.start)
        return waiting[:MAX_TURNS]

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
                spreker=spreker.label if spreker else "Onbekende spreker",
                fractie=spreker.fractie if spreker else None,
                start=turn.start,
                moment_url=moment_url_from_kop(turn.kop),
                tekst=tekst,
                is_bewindspersoon=bool(spreker and is_bewindspersoon(spreker)),
                onderbroken=onderbroken.label if onderbroken else None,
                onderbroken_is_bewindspersoon=bool(
                    onderbroken and is_bewindspersoon(onderbroken)
                ),
            )
            outcome = await vragen.beoordeel_beurt(beurt, context)
            if outcome.opnieuw_proberen:
                # The model cannot be reached. The turns after this one
                # would find the same, each after its own wait; the next
                # round starts here again.
                result.fouten += 1
                return
            await self._mark(turn.row_id, now)
            result.beoordeeld += 1
            if outcome.uitkomst == UITKOMST_GEMARKEERD:
                result.vragen += len(outcome.markering_ids)

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
