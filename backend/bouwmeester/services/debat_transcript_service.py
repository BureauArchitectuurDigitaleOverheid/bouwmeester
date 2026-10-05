"""Put what is said under the message of who says it.

The timeline posts one message per turn at speaking, with only a first
line: who and when. This reads the subtitles of the stream, files each line
under the turn it was spoken in, and writes the message again with the text
below the first line. A turn that goes on gets a message that grows.

Everything is kept in the database first and written to Mattermost from
there. A row holds the text of its turn and how much of it is in the
channel, so a message that could not be written is simply written on the
next round, and a restart continues where the reading stood.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx
from sqlalchemy import case, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.debat_sessie import DebatSessie, DebatSpreekbeurt
from bouwmeester.services import debat_direct as dd
from bouwmeester.services import debat_subtitles as subs
from bouwmeester.services.debat_statusregel import SCHEIDING, voeg_samen
from bouwmeester.services.debat_transcript import (
    append_text,
    assign_cues,
    fit_messages,
    render,
    render_closing,
    split_text,
)
from bouwmeester.services.debat_vraag_service import statusblok_voor_post
from bouwmeester.services.mattermost_service import (
    MattermostService,
    PostNotFoundError,
)

logger = logging.getLogger(__name__)

_SPEAKING = (dd.EVENT_SPEAKER, dd.EVENT_INTERRUPTER)
_CLOSING = (dd.EVENT_SUSPENDED, dd.EVENT_DEBATE_END)
# How far back the subtitles are read when a debate is first seen. The same
# patience the timeline has for what it missed.
READ_BACK = timedelta(minutes=10)
# Files per round. A round normally brings three; this is for catching up,
# and every file is a request the other debates wait for.
MAX_SEGMENTS = 30
# How long a stream without a subtitle track is left alone before looking
# again.
LOOK_AGAIN = timedelta(minutes=5)
# See `_read`: how long nothing may happen before a part counts as over.
SILENT_IS_OVER = timedelta(hours=1)
# Mattermost refuses a message over 16383 characters. Only reachable by
# late words piling into a message that may not continue below itself.
MESSAGE_MAX = 16000


@dataclass
class Turn:
    """A message of the timeline and the rows whose text belongs in it."""

    row_id: uuid.UUID
    post_id: str
    kop: str
    key: tuple[str, str]
    geplaatst: int
    vervolg: list[str]
    # When the turn began, and when it was read for questions.
    start: datetime
    beoordeeld_at: datetime | None = None
    texts: list[str] = field(default_factory=list)
    # A suspension or the end: the text is the chairman's, and only the
    # last of it is shown.
    closing: bool = False

    @property
    def text(self) -> str:
        joined = ""
        for text in self.texts:
            joined = append_text(joined, text)
        return joined


class DebatTranscript:
    def __init__(self, session: AsyncSession, mattermost: MattermostService) -> None:
        self.session = session
        self.mattermost = mattermost

    async def update(
        self,
        sessie: DebatSessie,
        debates: dict[str, dd.DdDebat],
        client: httpx.AsyncClient,
        now: datetime,
        result,  # type: ignore[no-untyped-def]
    ) -> None:
        """Read what is new in the subtitles of every part and show it."""
        sessie_id = sessie.id
        channel_id = sessie.channel_id
        if channel_id is None:
            return
        for debate_id in list(sessie.debat_direct_ids or []):
            try:
                changed = await self._read(sessie, debate_id, debates, client, now)
            except subs.SubtitleError:
                # The timeline does not depend on the text. Not counted as
                # an error either: a debate without subtitles is not stuck.
                logger.warning("Ondertitels van %s niet te lezen", debate_id)
                changed = False
            if changed:
                await self.session.commit()
            # Also when nothing is new: what could not be written before
            # is written now.
            await self._write(sessie_id, channel_id, debate_id, result)

    async def _read(
        self,
        sessie: DebatSessie,
        debate_id: str,
        debates: dict[str, dd.DdDebat],
        client: httpx.AsyncClient,
        now: datetime,
    ) -> bool:
        state = dict(sessie.ondertitels or {})
        entry = dict(state.get(debate_id) or {})

        debat = debates.get(debate_id)
        if not entry.get("url"):
            looked = _moment(entry.get("gekeken"))
            if looked is not None and now - looked < LOOK_AGAIN:
                return False
            if debat is None or not debat.stream_url:
                return False
            master = await subs.fetch_text(client, debat.stream_url)
            # A stream without a subtitle track is looked at again later,
            # not on every round: the track may not be there yet at the
            # start.
            entry = {
                "url": subs.find_subtitle_playlist(master, debat.stream_url) or "",
                "offset_ms": round(debat.stream_offset.total_seconds() * 1000),
                "gekeken": now.isoformat(),
            }
            # A new dict every time: a JSON column only notices a value
            # that is replaced, not one that is changed in place.
            sessie.ondertitels = {**state, debate_id: dict(entry)}
            if not entry["url"]:
                logger.info("Debat %s heeft geen ondertitelspoor", debate_id)
                return True

        rows = (
            await self.session.execute(
                select(
                    DebatSpreekbeurt.id,
                    DebatSpreekbeurt.event_type,
                    DebatSpreekbeurt.event_start,
                    DebatSpreekbeurt.tekst,
                )
                .where(
                    DebatSpreekbeurt.sessie_id == sessie.id,
                    DebatSpreekbeurt.debat_direct_id == debate_id,
                )
                .order_by(*_ORDER)
            )
        ).all()
        if not rows:
            return False

        position = _moment(entry.get("positie"))
        # Past the end of the part there is nothing left to read: a line is
        # in the file it starts in, and that file has been read by then.
        ends = [r[2] for r in rows if r[1] == dd.EVENT_DEBATE_END]
        if debat is not None and debat.ended_at is not None:
            ends.append(debat.ended_at)
        if ends and position is not None and position > max(ends):
            return False
        # The address belongs to the room, not to the debate: the next
        # debate in that room is on the same one. Without an end, a part
        # in which nothing has happened for this long is taken to be over,
        # so that someone else's debate does not end up in this channel.
        if position is not None and position - rows[-1][2] > SILENT_IS_OVER:
            return False

        cues, position = await subs.fetch_since(
            client,
            entry["url"],
            position,
            max_segments=MAX_SEGMENTS,
            since=max(rows[0][2], now - READ_BACK),
        )
        if position is None or position.isoformat() == entry.get("positie"):
            return False

        offset = timedelta(milliseconds=entry.get("offset_ms") or 0)
        spoken = assign_cues(cues, [(r[0], r[2]) for r in rows], offset)
        existing = {r[0]: r[3] for r in rows}
        for row_id, text in spoken.items():
            await self.session.execute(
                update(DebatSpreekbeurt)
                .where(DebatSpreekbeurt.id == row_id)
                .values(tekst=append_text(existing[row_id], text))
            )
        entry["positie"] = position.isoformat()
        sessie.ondertitels = {**state, debate_id: dict(entry)}
        return True

    async def _write(
        self,
        sessie_id: uuid.UUID,
        channel_id: str,
        debate_id: str,
        result,  # type: ignore[no-untyped-def]
    ) -> None:
        turns = await load_turns(self.session, sessie_id, debate_id)
        if not any(len(turn.text) != turn.geplaatst for turn in turns):
            return
        # The last thing the timeline put in the channel, of any part and
        # any kind. Only the turn that is that can continue below itself.
        newest = (
            await self.session.execute(
                select(DebatSpreekbeurt.id)
                .where(
                    DebatSpreekbeurt.sessie_id == sessie_id,
                    DebatSpreekbeurt.post_id.is_not(None),
                )
                .order_by(*(column.desc() for column in _ORDER))
                .limit(1)
            )
        ).scalar_one_or_none()
        for turn in turns:
            text = turn.text
            if len(text) == turn.geplaatst:
                continue
            if turn.closing:
                # `tekst_geplaatst` of this row counts the chairman's words
                # shown under it, which are kept on other rows.
                if await self._rewrite(turn.post_id, render_closing(turn.kop, text)):
                    await self._keep(turn.row_id, tekst_geplaatst=len(text))
                else:
                    logger.warning(
                        "Woorden van de voorzitter bij %s niet geplaatst", turn.row_id
                    )
                    result.fouten += 1
                continue
            pieces = split_text(text)
            if turn.row_id != newest:
                # A next message would land below whatever came after.
                pieces = fit_messages(pieces, 1 + len(turn.vervolg))
            # Full messages never change; only the last one that exists is
            # written again, and whatever comes after it is new.
            first = len(turn.vervolg)
            vervolg = list(turn.vervolg)
            done = True
            for number in range(first, len(pieces)):
                message = render(turn.kop, pieces[number], vervolg=number > 0)
                if number == 0:
                    # The first message is also where the questions of the
                    # turn are counted. Writing it again from the text alone
                    # would wipe that, so it goes back in, below the text
                    # and outside what is cut into messages.
                    blok = await statusblok_voor_post(self.session, turn.post_id)
                    if blok:
                        # Room for the rule and the block: what Mattermost
                        # refuses for its length is cut from the text.
                        room = MESSAGE_MAX - len(blok) - len(SCHEIDING) - 3
                        message = message[:room]
                    message = voeg_samen(message, blok)
                if number <= len(vervolg):
                    target = turn.post_id if number == 0 else vervolg[number - 1]
                    ok = await self._rewrite(target, message)
                else:
                    post_id = await self.mattermost.send_channel_message(
                        channel_id, message
                    )
                    ok = bool(post_id)
                    if post_id:
                        vervolg.append(post_id)
                        result.berichten += 1
                        # At once: a message that exists has to be known,
                        # or a restart makes it a second time.
                        await self._keep(turn.row_id, vervolg_post_ids=list(vervolg))
                if not ok:
                    logger.warning(
                        "Tekst van spreekbeurt %s niet geplaatst", turn.row_id
                    )
                    result.fouten += 1
                    done = False
                    break
            if done:
                await self._keep(turn.row_id, tekst_geplaatst=len(text))
            # A turn that could not be written does not hold up the ones
            # after it: it is tried again on a later round.

    async def _rewrite(self, post_id: str, message: str) -> bool:
        """Write a message again. ``True`` also when it never can be.

        Someone can delete a message of the timeline. Trying that one
        again on every round, for the rest of the debate, helps nobody.
        """
        if await self.mattermost.update_post(post_id, message[:MESSAGE_MAX]):
            return True
        try:
            await self.mattermost.get_post(post_id)
        except PostNotFoundError:
            logger.info("Bericht %s is weg; de tekst komt er niet meer in", post_id)
            return True
        return False

    async def _keep(self, row_id: uuid.UUID, **values) -> None:  # type: ignore[no-untyped-def]
        await self.session.execute(
            update(DebatSpreekbeurt)
            .where(DebatSpreekbeurt.id == row_id)
            .values(**values)
        )
        await self.session.commit()


# The order of the timeline: by moment, and within one second whatever is
# not someone speaking first.
_ORDER = (
    DebatSpreekbeurt.event_start,
    case((DebatSpreekbeurt.event_type.in_(_SPEAKING), 1), else_=0),
    # And a fixed order for two people speaking in the same second, so
    # that reading and writing agree on who came last.
    DebatSpreekbeurt.event_type,
    DebatSpreekbeurt.object_id,
)


def _moment(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment if moment.tzinfo else None


async def load_turns(
    session: AsyncSession, sessie_id: uuid.UUID, debate_id: str
) -> list[Turn]:
    """The messages of one part of a debate, each with the text that is its.

    The one place that says what a turn is. Writing the text and reading it
    for questions both go by this, so they cannot disagree about which
    words belong under which message.
    """
    rows = (
        await session.execute(
            select(
                DebatSpreekbeurt.id,
                DebatSpreekbeurt.event_type,
                DebatSpreekbeurt.object_id,
                DebatSpreekbeurt.event_start,
                DebatSpreekbeurt.post_id,
                DebatSpreekbeurt.kop,
                DebatSpreekbeurt.tekst,
                DebatSpreekbeurt.tekst_geplaatst,
                DebatSpreekbeurt.vervolg_post_ids,
                DebatSpreekbeurt.beoordeeld_at,
            )
            .where(
                DebatSpreekbeurt.sessie_id == sessie_id,
                DebatSpreekbeurt.debat_direct_id == debate_id,
            )
            .order_by(*_ORDER)
        )
    ).all()
    turns: list[Turn] = []
    current: Turn | None = None
    # What was said from the chair since a member last spoke, or since
    # the last suspension. Not only on rows of the chairman: what is
    # said after a resumption or a change of chairman is kept on the row
    # of that event.
    chairman = ""
    for row_id, kind, who, start, post_id, kop, tekst, geplaatst, vervolg, read in rows:
        if kind in _SPEAKING:
            chairman = ""
        elif kind not in _CLOSING:
            chairman = append_text(chairman, tekst or "")
        if post_id:
            current = None
            if kind in _CLOSING and kop and chairman:
                # "Ik schors de vergadering tot kwart over twee" is said
                # by the chairman just before the event. Without it the
                # suspension comes out of nowhere.
                turns.append(
                    Turn(
                        row_id,
                        post_id,
                        kop,
                        (kind, who),
                        geplaatst,
                        [],
                        start,
                        texts=[chairman],
                        closing=True,
                    )
                )
            if kind in _CLOSING:
                # Said once. A second suspension, or the end after a
                # suspension, does not repeat it.
                chairman = ""
            if kind in _SPEAKING and kop:
                current = Turn(
                    row_id,
                    post_id,
                    kop,
                    (kind, who),
                    geplaatst,
                    list(vervolg or []),
                    start,
                    read,
                )
                turns.append(current)
        elif kind in _SPEAKING and (current is None or current.key != (kind, who)):
            # Someone spoke who has no message: a stretch the timeline
            # missed. What follows is not the turn from before it.
            current = None
        if current is not None and kind in _SPEAKING and tekst:
            # The row of the message itself, and the rows of the same
            # speaker carrying on after the chairman said a word. What
            # the chairman said in between is kept but not shown.
            current.texts.append(tekst)
    return turns
