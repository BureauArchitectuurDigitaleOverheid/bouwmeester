"""Replay a debate in time: what is marked, and how long after it was said.

`harness.run_debate` hands every turn to the marking when the debate is
over, which measures what is marked and not when. This plays a gold file
that carries its subtitle lines (`build_turns --regels`) on a clock, in
rounds as the worker makes them, and hands in what the worker would hand
in at that moment: a turn that is over and final, turns of members first,
and of an answer of the bewindspersoon that goes on the part that is final.
Everything that is stored gets the moment of the clock at which it was.

Nothing is fetched and no voices are told apart here, so when a line is
final is a rule (`Clock`), with the numbers of the worker where it has
them and an assumption where production depends on something outside it:
how far the subtitles are behind, and how soon the voices decide.

The turns are those of the gold file: one per event of Debat Direct. The
worker reads one message, which is the same speaker carrying on after a
word of the chairman as well, so a turn ends a little earlier here than
there. That holds for both ways of reading, with and without `meelezen`.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.config import get_settings
from bouwmeester.models.debat_markering import (
    VERMELDING_ANTWOORD,
    DebatMarkering,
    DebatMarkeringVermelding,
)
from bouwmeester.models.debat_sessie import DebatSessie
from bouwmeester.services.debat_stemmen_service import AFTER, BEFORE, WAIT
from bouwmeester.services.debat_transcript import append_text
from bouwmeester.services.debat_vraag_moment import Line, moment_of_position
from bouwmeester.services.debat_vraag_service import (
    Beoordeling,
    Beurt,
    DebatVraagService,
    final_end,
    running_window,
)
from bouwmeester.services.debat_vraag_worker import (
    MARGIN,
    MAX_ANSWER_WINDOWS_PER_ROUND,
    MAX_TURNS,
    NEVER_MOVES_AFTER,
    RUNNING_EVERY,
    WAIT_FOR_INTERRUPTION,
)
from bouwmeester.services.llm.base import BaseLLMService

from .harness import (
    CHAIRMAN,
    TEAM,
    TURN_TIMEOUT,
    RecordingLLM,
    SilentMattermost,
    _raw_answer,
    _read_closing_list,
    beurt_from,
    context_from,
    interruption_before,
)

VOICES_AT_ONCE = "direct"
VOICES_NEVER = "nooit"


class ReplayError(ValueError):
    pass


@dataclass(frozen=True)
class Clock:
    """What a replay assumes about the time production needs."""

    # How long after it was said a subtitle line is with the worker: the
    # playlist lists a file about half a minute after its moment
    # (`debat_subtitles`), and the timeline looks every ten seconds.
    subtitle_lag: float = 40.0
    # When the voices are done with a line near a change of speaker: as
    # soon as they may look (`WAIT`), or never, so that the worker gives
    # up on it after `NEVER_MOVES_AFTER`. Production is in between, and
    # nearer the first when the voices are known.
    voices: str = VOICES_AT_ONCE
    # How long the worker sleeps between two rounds.
    round_seconds: float = float(get_settings().DEBAT_VRAGEN_INTERVAL_SECONDS)
    # How long a call of the model takes on this clock. Measured for a
    # window of an answer: 4.2 to 7.1 seconds; a turn of a member took 3
    # to 14. The real duration of a call in a replay says nothing: a
    # replay asks through a command line that takes its own time to start.
    call_seconds: float = 6.0
    # Whether an answer of the bewindspersoon is read while it goes on.
    # Without it, as it was: every turn is read when it is over.
    meelezen: bool = True
    # How long an answer that goes on is left alone after a window of it
    # was asked about, and how long it waits for the interruption before
    # it to be read: the worker's own numbers.
    running_every: float = RUNNING_EVERY.total_seconds()
    wait_for_interruption: float = WAIT_FOR_INTERRUPTION.total_seconds()


@dataclass
class _Turn:
    raw: dict
    index: int
    start: datetime
    # (start, end, text) of every line, in order.
    lines: list[tuple[datetime, datetime, str]]
    # When each of those lines is final on the clock.
    final_at: list[datetime]
    # From when anything of the turn can be read: the lines around its
    # beginning are decided about.
    opens_at: datetime
    # When the turn is over and final as a whole.
    done_at: datetime
    position: int = 0
    read: bool = False
    # When a window of it was last asked about while it went on.
    asked_at: datetime | None = None
    calls: int = 0
    outcome: Beoordeling | None = None
    answers: list[str] | None = None


def _moment(value: str) -> datetime:
    return datetime.fromisoformat(value)


def said_at(turn: dict, quote: str) -> datetime | None:
    """When a quote of a turn was said: the moment of the line it begins in."""
    lines = [Line(_moment(r["start"]), r["tekst"]) for r in turn.get("regels") or []]
    plek = turn["tekst"].find(quote)
    if plek < 0:
        return None
    return moment_of_position(lines, turn["tekst"], plek)


def _timeline(gold: dict, clock: Clock, max_turns: int | None) -> list[_Turn]:
    """Every turn of a gold file with the moments its lines are final."""
    turns = gold["beurten"][:max_turns]
    if any("regels" not in turn for turn in turns):
        raise ReplayError(
            "Deze gouden set heeft geen ondertitelregels per beurt; maak ze"
            " met `build_turns --regels-bij`."
        )
    # A change of speaker: the voices decide about the lines around it.
    changes = [
        _moment(later["start"])
        for earlier, later in zip(turns, turns[1:], strict=False)
        if earlier["spreker"] != later["spreker"]
    ]
    wait = WAIT.total_seconds()
    decided = (
        wait if clock.voices == VOICES_AT_ONCE else NEVER_MOVES_AFTER.total_seconds()
    )

    def final(start: datetime) -> datetime:
        near = any(change - BEFORE <= start <= change + AFTER for change in changes)
        return start + timedelta(
            seconds=max(clock.subtitle_lag, decided if near else wait)
        )

    every = [
        (_moment(line["start"]), final(_moment(line["start"])))
        for turn in turns
        for line in turn["regels"]
    ]

    def edge(change: datetime) -> datetime | None:
        around = [
            done for start, done in every if change - BEFORE <= start <= change + AFTER
        ]
        return max(around) if around else None

    lag = timedelta(seconds=clock.subtitle_lag)
    messages = [turn for turn in turns if turn["soort"] != CHAIRMAN]
    following = {
        earlier["nr"]: _moment(later["start"])
        for earlier, later in zip(messages, messages[1:], strict=False)
    }
    last_line = max(_moment(line["einde"]) for t in turns for line in t["regels"])
    built: list[_Turn] = []
    for index, turn in enumerate(turns):
        start = _moment(turn["start"])
        lines = [
            (_moment(r["start"]), _moment(r["einde"]), r["tekst"])
            for r in turn["regels"]
        ]
        opens = edge(start) or start
        next_message = following.get(turn["nr"])
        if next_message is None:
            # The last turn: over when the subtitles of the part are in.
            done = last_line + lag
        else:
            # `text_is_complete`: the subtitles read past the next message
            # and the margin; and no line around either end still in play.
            done = max(
                next_message + MARGIN + lag, edge(next_message) or next_message, opens
            )
        built.append(
            _Turn(
                raw=turn,
                index=index,
                start=start,
                lines=lines,
                final_at=[final(line[0]) for line in lines],
                opens_at=opens,
                done_at=max([done, *(final(line[0]) for line in lines)]),
            )
        )
    return built


def final_part(turn: _Turn, now: datetime) -> tuple[str, tuple[Line, ...]]:
    """The text of a turn that is final at `now`, and its lines."""
    if now < turn.opens_at:
        return "", ()
    lines: list[Line] = []
    for (start, _, text), done in zip(turn.lines, turn.final_at, strict=True):
        if done > now:
            break
        lines.append(Line(start, text))
    return append_text("", " ".join(line.text for line in lines)), tuple(lines)


async def replay_debate(
    session: AsyncSession,
    llm: BaseLLMService,
    gold: dict,
    name: str,
    clock: Clock,
    *,
    transform: Callable[[str], str] | None = None,
    max_turns: int | None = None,
    on_turn: Callable[[dict, dict], None] | None = None,
    on_round: Callable[[datetime, int, int], None] | None = None,
) -> dict:
    """Play one debate on the clock; returns its block of the run file.

    The block is that of `harness.run_debate`, and every marking in it
    also says when it was stored (`gemarkeerd_om`), when it was said
    (`gezegd_om`) and how many seconds lie between (`na`).
    """
    turns = _timeline(gold, clock, max_turns)
    recorder = RecordingLLM(llm, transform)
    mattermost = SilentMattermost()
    sessie = DebatSessie(
        activiteit_id=str(uuid.uuid4()),
        onderwerp=gold["debat"]["onderwerp"][:500],
        team_id=TEAM,
    )
    session.add(sessie)
    await session.commit()
    sessie_id = sessie.id
    service = DebatVraagService(session, mattermost, recorder)
    context = context_from(gold)
    block: dict = {
        "naam": name,
        "beurten": [],
        "aanroepen": 0,
        "klok": asdict(clock),
    }
    stored_at: dict[uuid.UUID, datetime] = {}
    raw_turns = [turn.raw for turn in turns]

    def as_beurt(turn: _Turn, **extra) -> Beurt:
        beurt = beurt_from(
            turn.raw, sessie_id, interruption_before(raw_turns, turn.index)
        )
        return replace(beurt, gelezen_tot=turn.position, **extra)

    async def hand_in(turn: _Turn, beurt: Beurt, now: datetime) -> datetime:
        """One call of the marking; returns the clock after it."""
        mattermost.messages.setdefault(beurt.post_id, turn.raw["tekst"][:200])
        before = len(recorder.answers)
        outcome = await asyncio.wait_for(
            service.beoordeel_beurt(beurt, context), TURN_TIMEOUT
        )
        asked = recorder.answers[before:]
        turn.calls += len(asked)
        turn.answers = [*(turn.answers or []), *asked]
        turn.outcome = outcome
        now += timedelta(seconds=clock.call_seconds * len(asked))
        ids = await session.execute(
            select(DebatMarkering.id).where(DebatMarkering.sessie_id == sessie_id)
        )
        for markering_id in ids.scalars().all():
            stored_at.setdefault(markering_id, now)
        await session.commit()
        if not outcome.opnieuw_proberen:
            turn.position = max(turn.position, outcome.gelezen_tot)
        return now

    try:
        now = min(turn.start for turn in turns)
        step = timedelta(seconds=clock.round_seconds)
        failures = 0
        messages = [turn for turn in turns if turn.raw["soort"] != CHAIRMAN]
        before = {
            later.index: earlier
            for earlier, later in zip(messages, messages[1:], strict=False)
        }
        # The model away three rounds in a row: no use playing on.
        while any(not turn.read for turn in messages) and failures < 3:
            now += step
            waiting = [turn for turn in messages if not turn.read]
            over = [turn for turn in waiting if now >= turn.done_at]
            # Members first, as the worker has it.
            members = [t for t in over if not t.raw.get("is_bewindspersoon")]
            away = False
            for turn in members[:MAX_TURNS]:
                now = await hand_in(turn, as_beurt(turn), now)
                if turn.outcome is not None and turn.outcome.opnieuw_proberen:
                    away = True
                    break
                turn.read = True
            if away:
                # The worker leaves the debate alone after this.
                failures += 1
                continue
            failed = failures
            answers = [t for t in over if t.raw.get("is_bewindspersoon")]
            going: list[_Turn] = []
            if clock.meelezen:
                for turn in waiting:
                    if turn in over or not turn.raw.get("is_bewindspersoon"):
                        continue
                    earlier = before.get(turn.index)
                    if (
                        earlier is not None
                        and not earlier.read
                        and earlier.raw["soort"] == "interrupter"
                        and (now - turn.start).total_seconds()
                        < clock.wait_for_interruption
                    ):
                        # The interruption before it has to be read
                        # first, for the question a toezegging is tied to.
                        continue
                    tekst, _ = final_part(turn, now)
                    venster = running_window(tekst, turn.position)
                    if venster is None:
                        continue
                    if (
                        turn.asked_at is not None
                        and (now - turn.asked_at).total_seconds() < clock.running_every
                        and venster[2] == final_end(tekst)
                    ):
                        continue
                    going.append(turn)
            for turn in [*answers, *going][:MAX_ANSWER_WINDOWS_PER_ROUND]:
                if turn in going:
                    tekst, lines = final_part(turn, now)
                    beurt = as_beurt(turn, tekst=tekst, lines=lines, loopt=True)
                    turn.asked_at = now
                    now = await hand_in(turn, beurt, now)
                    continue
                lines = tuple(Line(start, text) for start, _, text in turn.lines)
                now = await hand_in(turn, as_beurt(turn, lines=lines), now)
                outcome = turn.outcome
                if outcome is not None and outcome.opnieuw_proberen:
                    failures += 1
                elif outcome is not None and not outcome.meer:
                    turn.read = True
            if failures == failed:
                failures = 0
            if on_round is not None:
                on_round(now, sum(turn.read for turn in messages), len(messages))

        for turn in turns:
            block["beurten"].append(
                await _result(session, sessie_id, turn, recorder, stored_at)
            )
            block["aanroepen"] += turn.calls
            if on_turn is not None:
                on_turn(turn.raw, block["beurten"][-1])
        await _read_closing_list(
            session, service, recorder, context, raw_turns, block, sessie_id
        )
    except BaseException:
        await session.rollback()
        raise
    finally:
        await session.execute(delete(DebatSessie).where(DebatSessie.id == sessie_id))
        await session.commit()
    return block


async def _result(
    session: AsyncSession,
    sessie_id: uuid.UUID,
    turn: _Turn,
    recorder: RecordingLLM,
    stored_at: dict[uuid.UUID, datetime],
) -> dict:
    """What became of one turn, in the shape `harness.run_debate` gives."""
    sleutel = beurt_from(turn.raw, sessie_id).sleutel
    marked: list[dict] = []
    for row in (
        await session.execute(
            select(
                DebatMarkering.soort,
                DebatMarkering.citaat,
                DebatMarkering.gericht_aan,
                DebatMarkering.samenvatting,
                DebatMarkering.volgnummer,
                DebatMarkering.termijn,
                DebatMarkering.bij_volgnummer,
                DebatMarkering.id,
            )
            .where(
                DebatMarkering.sessie_id == sessie_id,
                DebatMarkering.beurt_sleutel == sleutel,
            )
            .order_by(DebatMarkering.volgnummer)
        )
    ).all():
        at = stored_at.get(row[7])
        said = said_at(turn.raw, row[1])
        marked.append(
            {
                "soort": row[0],
                "citaat": row[1],
                "gericht_aan": row[2],
                "samenvatting": row[3],
                "herhaling": False,
                "volgnummer": row[4],
                "termijn": row[5],
                "bij_volgnummer": row[6],
                "gemarkeerd_om": at.isoformat() if at else None,
                "gezegd_om": said.isoformat() if said else None,
                "na": round((at - said).total_seconds()) if at and said else None,
            }
        )
    marked += [
        {"soort": row[0], "citaat": row[1], "herhaling": True}
        for row in (
            await session.execute(
                select(DebatMarkering.soort, DebatMarkeringVermelding.citaat)
                .join(
                    DebatMarkering,
                    DebatMarkering.id == DebatMarkeringVermelding.markering_id,
                )
                .where(
                    DebatMarkeringVermelding.sessie_id == sessie_id,
                    DebatMarkeringVermelding.beurt_sleutel == sleutel,
                    DebatMarkeringVermelding.soort != VERMELDING_ANTWOORD,
                )
            )
        ).all()
    ]
    await session.commit()
    outcome = turn.outcome
    answers = turn.answers or []
    return {
        "nr": turn.raw["nr"],
        "uitkomst": outcome.uitkomst if outcome else "overgeslagen",
        "bewindspersoon": bool(turn.raw.get("is_bewindspersoon")),
        "reden": (outcome.reden if outcome else "voorzitter"),
        "afgevallen": outcome.afgevallen if outcome else 0,
        "aanroepen": turn.calls,
        "ruw": [raw for answer in answers for raw in _raw_answer(recorder, answer)],
        "gemarkeerd": marked,
        # When the turn was over and final as a whole: when it was read
        # before answers were read while they go on.
        "klaar_om": turn.done_at.isoformat(),
    }
