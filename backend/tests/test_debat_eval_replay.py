"""Tests for replaying a debate in time, and for what that measures.

A made-up debate with subtitle lines that each have a moment: a member
asks, the minister answers for ten minutes with a toezegging in the first
one, a member interrupts and the minister answers shortly. The model is
the oracle, so what is marked is the same either way and only the moment
differs.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from debat_eval.build_turns import add_lines, build_turns  # noqa: E402
from debat_eval.harness import OracleLLM, run_debate  # noqa: E402
from debat_eval.replay import (  # noqa: E402
    VOICES_NEVER,
    Clock,
    ReplayError,
    _timeline,
    final_part,
    replay_debate,
    said_at,
)
from debat_eval.timing import delays, percentile, timing_report  # noqa: E402

from bouwmeester.services import debat_direct as dd  # noqa: E402
from bouwmeester.services.debat_subtitles import Cue  # noqa: E402
from bouwmeester.services.debat_vraag_worker import NEVER_MOVES_AFTER  # noqa: E402

START = datetime(2026, 3, 3, 9, 0, tzinfo=UTC)
MINISTER = "Bewindspersoon A (Minister van Voorbeelden)"
Q_BRIEF = "Kan de minister toezeggen dat de Kamer een brief krijgt over de bezetting?"
Q_PROEF = "Wanneer hoort de Kamer hoe de proef met de regeling is verlopen?"
T_BRIEF = "Ik zeg toe dat de Kamer voor de zomer een brief krijgt over de bezetting."
T_PROEF = "Ik stuur de Kamer in het voorjaar de evaluatie van de proef."
T_KORT = "Dat zeg ik toe: u krijgt dat overzicht van de regeling voor het kerstreces."


def _filler(count: int) -> str:
    return " ".join(
        f"Onderdeel {number} van de regeling is in de praktijk uitvoerbaar gebleken."
        for number in range(1, count + 1)
    )


def _turn(nr: int, soort: str, spreker: str, tekst: str, **extra) -> dict:
    return {
        "nr": nr,
        "soort": soort,
        "spreker": spreker,
        "fractie": extra.pop("fractie", None),
        "is_bewindspersoon": spreker == MINISTER,
        "onderbroken": None,
        "onderbroken_is_bewindspersoon": False,
        "tekst": tekst,
        **extra,
    }


def _gold() -> dict:
    """The made-up debate, every turn with lines of eight words, three
    seconds each."""
    long_answer = " ".join(
        [
            "Voorzitter, dank voor de vragen over de regeling.",
            T_BRIEF,
            "Dan is er het punt van de uitvoering in de regio.",
            _filler(90),
            T_PROEF,
            "Daar is de afgelopen jaren veel over gezegd.",
        ]
    )
    turns = [
        _turn(1, "chairman", "de voorzitter", "Het woord is aan de heer A."),
        _turn(
            2,
            "speaker",
            "Kamerlid A (X)",
            f"Voorzitter, dank u wel voor het woord. {Q_BRIEF}",
            fractie="X",
        ),
        _turn(3, "chairman", "de voorzitter", "Dan geef ik het woord aan de minister."),
        _turn(4, "speaker", MINISTER, long_answer),
        _turn(
            5,
            "interrupter",
            "Kamerlid B (Y)",
            f"Voorzitter, een korte vraag aan de minister. {Q_PROEF}",
            fractie="Y",
            onderbroken=MINISTER,
            onderbroken_is_bewindspersoon=True,
        ),
        _turn(6, "speaker", MINISTER, f"{T_KORT} Meer kan ik er nu niet over zeggen."),
        _turn(7, "chairman", "de voorzitter", "Ik sluit de vergadering."),
    ]
    now = START
    for turn in turns:
        turn["start"] = now.isoformat()
        words = turn["tekst"].split()
        turn["regels"] = []
        for at in range(0, len(words), 8):
            turn["regels"].append(
                {
                    "start": now.isoformat(),
                    "einde": (now + timedelta(seconds=3)).isoformat(),
                    "tekst": " ".join(words[at : at + 8]),
                }
            )
            now += timedelta(seconds=3)
        now += timedelta(seconds=2)
    return {
        "debat": {
            "onderwerp": "De regeling voor de regio",
            "soort": "Commissiedebat",
            "bewindspersonen": [
                {"naam": "A. Bewindspersoon", "functie": "minister van Voorbeelden"}
            ],
            "stukken": [],
            "initiatiefnemers": False,
        },
        "beurten": turns,
        "items": [
            {
                "beurt": 2,
                "soort": "vraag",
                "citaat": Q_BRIEF,
                "gericht_aan": "minister",
            },
            {
                "beurt": 5,
                "soort": "vraag",
                "citaat": Q_PROEF,
                "gericht_aan": "minister",
            },
            {"beurt": 4, "soort": "toezegging", "citaat": T_BRIEF},
            {"beurt": 4, "soort": "toezegging", "citaat": T_PROEF},
            {"beurt": 6, "soort": "toezegging", "citaat": T_KORT},
        ],
        "negatieven": [],
    }


def _marked(block: dict) -> dict[str, dict]:
    return {
        marking["citaat"]: marking
        for turn in block["beurten"]
        for marking in turn["gemarkeerd"]
        if not marking.get("herhaling")
    }


class TestWhenALineIsFinal:
    def test_a_line_is_final_when_it_was_read_and_the_voices_may_look(self):
        gold = _gold()
        clock = Clock(subtitle_lag=40)
        answer = _timeline(gold, clock, None)[3]

        # Far from a change of speaker: as soon as the subtitles have it.
        inside = answer.lines[10][0]
        assert answer.final_at[10] == inside + timedelta(seconds=40)
        tekst, lines = final_part(answer, inside + timedelta(seconds=39))
        assert len(lines) == 10
        assert gold["beurten"][3]["tekst"].startswith(tekst)

    def test_nothing_of_a_turn_is_final_before_its_first_lines_are_decided_about(self):
        gold = _gold()
        answer = _timeline(gold, Clock(voices=VOICES_NEVER), None)[3]
        wait = NEVER_MOVES_AFTER

        assert answer.opens_at >= answer.start + wait
        assert final_part(answer, answer.start + timedelta(seconds=100)) == ("", ())
        tekst, _ = final_part(answer, answer.opens_at)
        assert tekst.startswith("Voorzitter, dank voor de vragen")

    def test_a_turn_is_over_when_the_next_one_was_read_past(self):
        gold = _gold()
        turns = _timeline(gold, Clock(subtitle_lag=40), None)
        answer, interruption = turns[3], turns[4]

        assert answer.done_at >= interruption.start + timedelta(seconds=40)
        # The last turn of all: when the last line is in.
        assert turns[-1].done_at >= turns[-1].lines[-1][1] + timedelta(seconds=40)

    def test_a_gold_file_without_lines_cannot_be_replayed(self):
        gold = _gold()
        del gold["beurten"][2]["regels"]

        with pytest.raises(ReplayError):
            _timeline(gold, Clock(), None)

    def test_when_a_quote_was_said(self):
        gold = _gold()
        answer = gold["beurten"][3]

        said = said_at(answer, T_PROEF)

        line = next(r for r in answer["regels"] if "evaluatie" in r["tekst"])
        assert said is not None
        assert abs((said - datetime.fromisoformat(line["start"])).total_seconds()) <= 3
        assert said_at(answer, "dit staat er niet") is None


@pytest.mark.asyncio
class TestReplay:
    async def test_a_toezegging_is_marked_while_the_answer_goes_on(self, db_session):
        gold = _gold()
        after = await replay_debate(
            db_session, OracleLLM(gold), gold, "na", Clock(meelezen=False)
        )
        during = await replay_debate(db_session, OracleLLM(gold), gold, "mee", Clock())

        # The same markings either way.
        assert set(_marked(after)) == set(_marked(during))
        assert set(_marked(during)) == {Q_BRIEF, Q_PROEF, T_BRIEF, T_PROEF, T_KORT}

        late, early = _marked(after)[T_BRIEF], _marked(during)[T_BRIEF]
        # Read at its end, the answer of ten minutes shows nothing for ten.
        assert late["na"] > 400
        # Read as it comes: the subtitles, a sentence, a round and a call.
        assert early["na"] < 90
        assert early["gezegd_om"] == late["gezegd_om"]
        # A question waits as long as it did.
        assert _marked(after)[Q_BRIEF]["na"] == _marked(during)[Q_BRIEF]["na"]

    async def test_it_costs_calls_and_the_block_says_how_many(self, db_session):
        gold = _gold()
        after = await replay_debate(
            db_session, OracleLLM(gold), gold, "na", Clock(meelezen=False)
        )
        during = await replay_debate(db_session, OracleLLM(gold), gold, "mee", Clock())

        calls = {t["nr"]: t["aanroepen"] for t in during["beurten"]}
        before = {t["nr"]: t["aanroepen"] for t in after["beurten"]}
        assert during["aanroepen"] == sum(calls.values())
        # The members cost what they did. The long answer costs a call
        # per toezegging here, as it did: nothing else in it has the
        # words of a commitment, and a window without them is not sent.
        assert (calls[2], calls[5]) == (before[2], before[5])
        assert (before[4], calls[4]) == (2, 2)
        assert during["klok"]["meelezen"] is True
        assert after["klok"]["meelezen"] is False

    async def test_what_is_marked_is_what_the_run_without_a_clock_marks(
        self, db_session
    ):
        gold = _gold()
        plain = await run_debate(db_session, OracleLLM(gold), gold, "gewoon")
        replayed = await replay_debate(
            db_session, OracleLLM(gold), gold, "mee", Clock()
        )

        assert set(_marked(plain)) == set(_marked(replayed))
        assert [t["nr"] for t in replayed["beurten"]] == [
            t["nr"] for t in plain["beurten"]
        ]

    async def test_the_report_says_how_long_and_how_many(self, db_session):
        gold = _gold()
        block = await replay_debate(db_session, OracleLLM(gold), gold, "mee", Clock())
        run = {"meta": {"label": "mee"}, "debatten": [block]}

        found = delays(run, {"mee": gold})

        assert len(found["toezegging"]) == 3 and len(found["vraag"]) == 2
        for own, to_end in found["toezegging"]:
            # Never later than a round and a call after the turn is over.
            assert own <= to_end + 15 + 2 * 6
        report = timing_report(run, {"mee": gold})
        assert "meelezen aan" in report
        assert "toezegging" in report and "per uur" in report

    async def test_a_run_without_a_clock_has_no_timing(self, db_session):
        gold = _gold()
        block = await run_debate(db_session, OracleLLM(gold), gold, "gewoon")

        assert "niet op een klok" in timing_report({"debatten": [block]}, {})


class TestPercentile:
    def test_the_nearest_value_that_is_there(self):
        values = [5.0, 1.0, 3.0, 2.0, 4.0]

        assert percentile(values, 0.5) == 3.0
        assert percentile(values, 0.9) == 5.0
        assert percentile([7.0], 0.9) == 7.0


@pytest.mark.asyncio
class TestTheOracleAndAWindow:
    async def test_it_gives_only_what_stands_in_the_words_it_is_shown(self):
        """A window in the middle of an answer is not the end of a turn."""
        gold = _gold()
        oracle = OracleLLM(gold)
        tekst = gold["beurten"][3]["tekst"]
        middle = tekst[: tekst.index(T_PROEF)].rstrip()

        answer = await oracle._complete(
            f'<spreekbeurt>\n{middle}\n</spreekbeurt>\n{{"toezeggingen": []}}'
        )

        assert T_BRIEF in answer and T_PROEF not in answer


class TestLinesInAGoldFile:
    def _recording(self):
        events = tuple(
            dd.DdEvent(START + timedelta(seconds=seconds), dd.EVENT_SPEAKER, who, "")
            for seconds, who in ((0, "a"), (30, "m"))
        )
        debat = dd.DdDebat(
            id="d1",
            name="De regeling",
            slug="de-regeling",
            debate_type=None,
            debate_date="2026-03-03",
            starts_at=None,
            started_at=None,
            ended_at=None,
            location_id=None,
            location_name=None,
            category_ids=(),
            events=events,
        )
        sprekers = {
            "a": dd.Spreker("Kamerlid A", "X", "Tweede Kamerlid"),
            "m": dd.Spreker("Bewindspersoon A", None, "Minister van Voorbeelden"),
        }
        cues = [
            Cue(
                START + timedelta(seconds=s),
                START + timedelta(seconds=s + 3),
                f"regel {s}.",
            )
            for s in (2, 6, 32, 36, 40)
        ]
        return debat, sprekers, cues

    def test_every_turn_carries_the_lines_its_text_is_made_of(self):
        debat, sprekers, cues = self._recording()

        turns = build_turns(debat, sprekers, cues, with_lines=True)

        assert [len(turn["regels"]) for turn in turns] == [2, 3]
        for turn in turns:
            assert " ".join(r["tekst"] for r in turn["regels"]) == turn["tekst"]
            assert turn["regels"][0]["start"] < turn["regels"][0]["einde"]
        assert "regels" not in build_turns(debat, sprekers, cues)[0]

    def test_lines_are_added_to_a_labelled_file_where_the_text_is_the_same(self):
        debat, sprekers, cues = self._recording()
        turns = build_turns(debat, sprekers, cues, with_lines=True)
        labelled = {
            "beurten": [
                {"nr": 1, "tekst": turns[0]["tekst"]},
                {"nr": 2, "tekst": "een andere tekst", "regels": ["oud"]},
            ],
            "items": [{"beurt": 1, "soort": "vraag", "citaat": "regel 2."}],
        }

        given = add_lines(labelled, turns)

        assert given == 1
        assert labelled["beurten"][0]["regels"] == turns[0]["regels"]
        assert "regels" not in labelled["beurten"][1]
        assert labelled["items"] == [
            {"beurt": 1, "soort": "vraag", "citaat": "regel 2."}
        ]
