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
from bouwmeester.services.debat_transcript import (
    append_text,
    assign_cues,
    fit_messages,
    render,
    split_text,
)
from bouwmeester.services.mattermost_service import MattermostService

logger = logging.getLogger(__name__)

_SPEAKING = (dd.EVENT_SPEAKER, dd.EVENT_INTERRUPTER)
# How far back the subtitles are read when a debate is first seen. The same
# patience the timeline has for what it missed.
READ_BACK = timedelta(minutes=10)
# Files per round. A round normally brings three; this is for catching up.
MAX_SEGMENTS = 60


@dataclass
class _Turn:
    """A message of the timeline and the rows whose text belongs in it."""

    row_id: uuid.UUID
    post_id: str
    kop: str
    key: tuple[str, str]
    geplaatst: int
    vervolg: list[str]
    texts: list[str] = field(default_factory=list)

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

        if "url" not in entry:
            debat = debates.get(debate_id)
            if debat is None or not debat.stream_url:
                return False
            master = await subs.fetch_text(client, debat.stream_url)
            entry = {
                "url": subs.find_subtitle_playlist(master, debat.stream_url) or "",
                "offset_ms": round(debat.stream_offset.total_seconds() * 1000),
            }
            if not entry["url"]:
                logger.info("Debat %s heeft geen ondertitelspoor", debate_id)
            # A new dict every time: a JSON column only notices a value
            # that is replaced, not one that is changed in place.
            sessie.ondertitels = {**state, debate_id: dict(entry)}
            if not entry["url"]:
                return True
        if not entry["url"]:
            return False

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
        if ends and position is not None and position > max(ends):
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

    async def _turns(self, sessie_id: uuid.UUID, debate_id: str) -> list[_Turn]:
        rows = (
            await self.session.execute(
                select(
                    DebatSpreekbeurt.id,
                    DebatSpreekbeurt.event_type,
                    DebatSpreekbeurt.object_id,
                    DebatSpreekbeurt.post_id,
                    DebatSpreekbeurt.kop,
                    DebatSpreekbeurt.tekst,
                    DebatSpreekbeurt.tekst_geplaatst,
                    DebatSpreekbeurt.vervolg_post_ids,
                )
                .where(
                    DebatSpreekbeurt.sessie_id == sessie_id,
                    DebatSpreekbeurt.debat_direct_id == debate_id,
                )
                .order_by(*_ORDER)
            )
        ).all()
        turns: list[_Turn] = []
        current: _Turn | None = None
        for row_id, kind, who, post_id, kop, tekst, geplaatst, vervolg in rows:
            if post_id:
                current = None
                if kind in _SPEAKING and kop:
                    current = _Turn(
                        row_id,
                        post_id,
                        kop,
                        (kind, who),
                        geplaatst,
                        list(vervolg or []),
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

    async def _write(
        self,
        sessie_id: uuid.UUID,
        channel_id: str,
        debate_id: str,
        result,  # type: ignore[no-untyped-def]
    ) -> None:
        turns = await self._turns(sessie_id, debate_id)
        for index, turn in enumerate(turns):
            text = turn.text
            if len(text) == turn.geplaatst:
                continue
            is_last = index == len(turns) - 1
            pieces = split_text(text)
            if not is_last:
                # A next message would land below whoever spoke after.
                pieces = fit_messages(pieces, 1 + len(turn.vervolg))
            # Full messages never change; only the last one that exists is
            # written again, and whatever comes after it is new.
            first = len(turn.vervolg) if turn.geplaatst else 0
            vervolg = list(turn.vervolg)
            done = True
            for number in range(first, len(pieces)):
                message = render(turn.kop, pieces[number], vervolg=number > 0)
                if number == 0:
                    ok = await self.mattermost.update_post(turn.post_id, message)
                elif number <= len(vervolg):
                    ok = await self.mattermost.update_post(vervolg[number - 1], message)
                else:
                    post_id = await self.mattermost.send_channel_message(
                        channel_id, message
                    )
                    ok = bool(post_id)
                    if post_id:
                        vervolg.append(post_id)
                        result.berichten += 1
                if not ok:
                    logger.warning(
                        "Tekst van spreekbeurt %s niet geplaatst", turn.row_id
                    )
                    result.fouten += 1
                    done = False
                    break
            values: dict = {"vervolg_post_ids": vervolg}
            if done:
                values["tekst_geplaatst"] = len(text)
            await self.session.execute(
                update(DebatSpreekbeurt)
                .where(DebatSpreekbeurt.id == turn.row_id)
                .values(**values)
            )
            # Per turn: a message that exists has to be known, or a restart
            # makes it a second time.
            await self.session.commit()
            if not done:
                # Later turns wait: the next round starts here again.
                return


# The order of the timeline: by moment, and within one second whatever is
# not someone speaking first.
_ORDER = (
    DebatSpreekbeurt.event_start,
    case((DebatSpreekbeurt.event_type.in_(_SPEAKING), 1), else_=0),
)


def _moment(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment if moment.tzinfo else None
