"""Tests for the evaluation of what is marked in a debate.

The parts that count and compare are tested with made-up data. One test at
the end runs the production code path over the made-up debate of the
fixture, with a model that answers with the gold questions: what goes
wrong there is the doing of the code, not of a model.
"""

from __future__ import annotations

import copy
import json
import re
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from debat_eval import gold as gold_file  # noqa: E402
from debat_eval.apply_labels import (  # noqa: E402
    LabelError,
    apply_labels,
    cut_quote,
    parse_label,
)
from debat_eval.harness import (  # noqa: E402
    OracleLLM,
    beurt_from,
    interruption_before,
    run_debate,
)
from debat_eval.report import (  # noqa: E402
    apply_check,
    build_report,
    not_marked,
    score_run,
)
from debat_eval.scoring import (  # noqa: E402
    REASON_DROPPED,
    REASON_NOT_AN_ANSWER,
    REASON_NOT_FOUND,
    REASON_NOT_RUN,
    UNLABELLED,
    GoldItem,
    Marking,
    Negative,
    format_comparison,
    format_report,
    format_table,
    miss_reasons,
    same_passage,
    score,
    shared_share,
    words,
)
from debat_eval.variants import (  # noqa: E402
    ANCHOR,
    PROMPT_VARIANTS,
    VariantError,
    before_anchor,
    has_question_form,
    is_motion_text,
)

from bouwmeester.models.debat_sessie import DebatSessie  # noqa: E402
from bouwmeester.services.llm.prompts import (  # noqa: E402
    build_debat_vragen_prompt,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "debat_markeringen_synthetisch.json"
FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

Q_BUDGET = "Klopt het dat het budget volgend jaar met 12 miljoen wordt verlaagd?"
Q_CAMERA = "Is de minister bereid om afspraken te maken over camera's in elke stalling?"
STATEMENT = "Niemand kan mij vertellen waar de 30 miljoen aan is uitgegeven."


def item(citaat: str, soort: str = "vraag", beurt: int = 1, **extra) -> GoldItem:
    return GoldItem("d", beurt, soort, citaat, **extra)


def marking(citaat: str, soort: str = "vraag", beurt: int = 1, **extra) -> Marking:
    return Marking("d", beurt, soort, citaat, **extra)


class TestSamePassage:
    def test_words_drop_case_accents_and_punctuation(self):
        assert words("Vóór de zomer, één brief!") == [
            "voor",
            "de",
            "zomer",
            "een",
            "brief",
        ]

    def test_the_same_quote_matches(self):
        assert shared_share(Q_BUDGET, Q_BUDGET) == 1.0

    def test_a_sentence_more_still_matches(self):
        longer = f"Dan heb ik vragen aan de minister. {Q_BUDGET} En zo ja, waarom?"
        assert same_passage(longer, Q_BUDGET)

    def test_half_of_the_shorter_quote_is_enough(self):
        assert same_passage(
            "Klopt het dat het budget volgend jaar omlaag gaat?", Q_BUDGET
        )

    def test_two_questions_that_share_small_words_do_not_match(self):
        other = "Hoe kijkt de minister naar het budget voor de handhaving?"
        assert not same_passage(other, Q_BUDGET)

    def test_shared_words_in_another_order_do_not_match(self):
        shuffled = "verlaagd wordt miljoen 12 met jaar volgend budget het dat het Klopt"
        assert shared_share(shuffled, Q_BUDGET) < 0.5

    def test_a_quote_with_an_omission_matches_on_its_pieces(self):
        pieces = "Klopt het dat het budget (...) met 12 miljoen wordt verlaagd?"
        assert same_passage(pieces, Q_BUDGET)

    def test_a_short_quote_inside_a_long_one_matches(self):
        assert same_passage("Kan hij dat toezeggen?", "Mooi. Kan hij dat toezeggen?")

    def test_nothing_matches_an_empty_quote(self):
        assert shared_share("", Q_BUDGET) == 0.0
        assert shared_share("...", "?") == 0.0


class TestScore:
    def test_found_and_missed(self):
        result = score(
            [marking(Q_BUDGET)],
            [item(Q_BUDGET), item(Q_CAMERA)],
            kinds=("vraag",),
        )["vraag"]
        assert (result.required, result.found, len(result.misses)) == (2, 1, 1)
        assert result.misses[0].item.citaat == Q_CAMERA
        assert result.recall == 0.5
        assert result.precision == 1.0

    def test_a_marking_counts_only_in_its_own_turn(self):
        result = score([marking(Q_BUDGET, beurt=2)], [item(Q_BUDGET, beurt=1)])["vraag"]
        assert result.found == 0
        assert [fp.category for fp in result.false_positives] == [UNLABELLED]

    def test_an_optional_item_is_not_a_miss_and_not_a_false_positive(self):
        unsure = item(Q_BUDGET, onzeker=True)
        repeat = item(Q_CAMERA, herhaling=True)
        missed = score([], [unsure, repeat])["vraag"]
        assert (missed.required, missed.optional, missed.misses) == (0, 2, [])
        assert missed.recall is None
        found = score([marking(Q_BUDGET)], [unsure, repeat])["vraag"]
        assert (found.optional_found, found.right, found.false_positives) == (1, 1, [])

    def test_two_markings_on_one_gold_item_are_both_right(self):
        whole = "Is de minister bereid om afspraken te maken? Wanneer hoort de Kamer?"
        result = score(
            [
                marking("Is de minister bereid om afspraken te maken?"),
                marking("Wanneer hoort de Kamer?"),
            ],
            [item(whole)],
        )["vraag"]
        assert (result.marked, result.right, result.found) == (2, 2, 1)
        assert result.precision == 1.0

    def test_a_false_positive_is_named_after_the_negative_it_matches(self):
        result = score(
            [marking(STATEMENT)],
            [item(Q_BUDGET)],
            [Negative("d", 1, "stelling", STATEMENT)],
        )["vraag"]
        assert result.fp_categories == {"stelling": 1}
        assert result.precision == 0.0

    def test_a_false_positive_on_another_kind_is_named_after_that_kind(self):
        dictum = "verzoekt de regering een plan te maken voor elk station"
        result = score([marking(dictum)], [item(dictum, soort="motie")])["vraag"]
        assert result.fp_categories == {"soort:motie": 1}

    def test_a_request_for_a_letter_marked_as_question_is_left_out(self):
        letter = "Ik zou graag een brief van de minister ontvangen met een overzicht."
        result = score(
            [marking(letter), marking(Q_BUDGET)],
            [item(letter, soort="verzoek_om_brief"), item(Q_BUDGET)],
        )
        assert result["vraag"].left_out == 1
        assert result["vraag"].false_positives == []
        assert result["vraag"].precision == 1.0
        # Nothing was marked as a request for a letter, so that one is missed.
        assert len(result["verzoek_om_brief"].misses) == 1

    def test_why_a_question_was_missed(self):
        run = {
            "debatten": [
                {
                    "naam": "d",
                    "beurten": [
                        {"nr": 1, "uitkomst": "overgeslagen", "reden": "voorzitter"},
                        {
                            "nr": 2,
                            "uitkomst": "geen_vraag",
                            "ruw": [{"citaat": Q_CAMERA}],
                        },
                        {"nr": 3, "uitkomst": "geen_vraag", "ruw": []},
                        {"nr": 4, "uitkomst": "llm_onbruikbaar"},
                    ],
                }
            ]
        }
        items = [
            item(Q_BUDGET, beurt=1),
            item(Q_CAMERA, beurt=2),
            item(Q_BUDGET, beurt=3),
            item(Q_BUDGET, beurt=4),
            item(Q_BUDGET, beurt=5),
        ]
        result = score([], items, turns=miss_reasons(run))["vraag"]
        assert [miss.reason for miss in result.misses] == [
            "beurt overgeslagen: voorzitter",
            REASON_DROPPED,
            REASON_NOT_FOUND,
            "model gaf geen bruikbaar antwoord",
            REASON_NOT_RUN,
        ]

    def test_no_numbers_without_anything_to_count(self):
        result = score([], [])["vraag"]
        assert result.precision is None and result.recall is None
        assert "vraag" not in format_table({"vraag": result})


class TestReport:
    def _scores(self, markings):
        return score(
            markings,
            [item(Q_BUDGET), item(Q_CAMERA, beurt=2)],
            [Negative("d", 1, "stelling", STATEMENT)],
            kinds=("vraag",),
        )

    def test_the_table_has_the_numbers(self):
        table = format_table(self._scores([marking(Q_BUDGET), marking(STATEMENT)]))
        row = table.splitlines()[1].split()
        # kind, gold, found, missed, marked, right, wrong, precision, recall
        assert row == ["vraag", "2", "1", "1", "2", "1", "1", "50%", "50%"]

    def test_misses_and_false_positives_are_listed_with_turn_and_quote(self):
        report = format_report(
            self._scores([marking(Q_BUDGET), marking(STATEMENT, samenvatting="Waar?")]),
            {("d", 1): "Kamerlid A (X)", ("d", 2): "Kamerlid B (Y)"},
        )
        assert "d beurt 2 (Kamerlid B (Y))" in report
        assert Q_CAMERA in report
        assert "1 × stelling" in report
        assert f"citaat: {STATEMENT}" in report
        assert "samenvatting: Waar?" in report

    def test_comparison_names_what_changed(self):
        before = self._scores([marking(Q_BUDGET), marking(STATEMENT)])
        now = self._scores([marking(Q_CAMERA, beurt=2)])
        text = format_comparison(now, before, "baseline")
        assert "Vergeleken met baseline" in text
        assert "precisie 100% (+50)" in text
        assert "fout 0 (-1)" in text
        assert "Nu gevonden, eerder gemist (1)" in text
        assert "Nu gemist, eerder gevonden (1)" in text
        assert "Niet meer ten onrechte (1)" in text
        assert "Nieuw ten onrechte" not in text


class TestGoldFile:
    def test_the_fixture_is_sound(self):
        assert gold_file.validate(FIXTURE) == []
        assert 20 <= len(FIXTURE["beurten"]) <= 40

    def test_the_fixture_covers_every_kind_and_every_hard_negative(self):
        assert {i["soort"] for i in FIXTURE["items"]} == set(gold_file.KINDS)
        types = {n["type"] for n in FIXTURE["negatieven"]}
        assert {
            gold_file.NEG_RETORISCH,
            gold_file.NEG_AAN_KAMERLID,
            gold_file.NEG_AAN_INITIATIEFNEMERS,
            gold_file.NEG_OVER_KABINET,
            gold_file.NEG_STELLING,
            "aangehaald",
            "oproep",
        } <= types
        assert any(i["herhaling"] for i in FIXTURE["items"])
        assert any(i["onzeker"] for i in FIXTURE["items"])

    def test_the_fixture_names_nobody(self):
        speaker = re.compile(
            r"^(de voorzitter|Kamerlid [A-Z] \([A-Z]\)|Bewindspersoon [A-Z] \(.+\))$"
        )
        for turn in FIXTURE["beurten"]:
            assert speaker.match(turn["spreker"]), turn["spreker"]
            assert turn["fractie"] is None or len(turn["fractie"]) == 1

    def test_a_quote_that_is_not_in_its_turn_is_a_problem(self):
        broken = copy.deepcopy(FIXTURE)
        broken["items"][0]["citaat"] = "Dit is nergens gezegd."
        broken["items"][1]["soort"] = "applaus"
        broken["negatieven"][0]["beurt"] = 999
        problems = gold_file.validate(broken)
        assert any("quote is not in the turn" in p for p in problems)
        assert any("unknown kind 'applaus'" in p for p in problems)
        assert any("no such turn" in p for p in problems)

    def test_loading_a_broken_file_raises(self, tmp_path):
        path = tmp_path / "gold.json"
        path.write_text(json.dumps({"beurten": []}), encoding="utf-8")
        with pytest.raises(gold_file.GoldError):
            gold_file.load(path)


class TestLabels:
    TEXTS = {3: f"Voorzitter. {Q_BUDGET} En zo ja, waarom? Dank u wel."}

    def test_a_quote_is_cut_from_first_to_last_words(self):
        assert (
            cut_quote(self.TEXTS[3], "Klopt het", "waarom?")
            == f"{Q_BUDGET} En zo ja, waarom?"
        )

    def test_an_item_with_flags_and_a_note(self):
        target, entry = parse_label(
            "3 vraag @minister ? h :: Klopt het >>> verlaagd? ## uit de eerste termijn",
            self.TEXTS,
        )
        assert target == "items"
        assert entry == {
            "beurt": 3,
            "soort": "vraag",
            "citaat": Q_BUDGET,
            "gericht_aan": "minister",
            "onzeker": True,
            "herhaling": True,
            "notitie": "uit de eerste termijn",
        }

    def test_a_negative_is_written_with_a_dash(self):
        target, entry = parse_label("3 -retorisch :: En zo ja, waarom?", self.TEXTS)
        assert target == "negatieven"
        assert entry == {"beurt": 3, "type": "retorisch", "citaat": "En zo ja, waarom?"}

    @pytest.mark.parametrize(
        "line",
        [
            "3 vraag :: Dit staat er niet",
            "3 vraag :: Klopt het >>> staat er niet",
            "9 vraag :: Klopt het",
            "3 applaus :: Klopt het",
            "3 vraag x :: Klopt het",
            "3 vraag Klopt het",
            "vraag 3 :: Klopt het",
        ],
    )
    def test_a_label_that_cannot_be_right_is_refused(self, line):
        with pytest.raises(LabelError):
            parse_label(line, self.TEXTS)

    def test_labels_replace_what_was_there_and_errors_are_reported(self):
        gold = {
            "beurten": [{"nr": 3, "tekst": self.TEXTS[3]}],
            "items": [{"old": True}],
            "negatieven": [],
        }
        errors = apply_labels(
            gold,
            ["# comment", "", "3 vraag :: Klopt het >>> verlaagd?", "3 vraag :: nee"],
        )
        assert [i["citaat"] for i in gold["items"]] == [Q_BUDGET]
        assert errors == ["line 4: not in the turn: 'nee'"]
        assert gold_file.validate(gold) == []


class TestVariants:
    def _prompt(self) -> str:
        return build_debat_vragen_prompt(
            onderwerp="Onderwerp",
            soort_vergadering="Notaoverleg",
            bewindspersonen=["minister van Voorbeelden: Bewindspersoon A"],
            stukken=[],
            openstaand=[],
            spreker="Kamerlid A (X)",
            interruptie=False,
            tekst=Q_BUDGET,
        )

    def test_the_production_variant_changes_nothing(self):
        assert PROMPT_VARIANTS["productie"](self._prompt()) == self._prompt()

    def test_a_variant_adds_its_text_before_the_heading_it_hooks_onto(self):
        prompt = self._prompt()
        changed = before_anchor(prompt, "## Een alinea om te proberen\nTekst.\n\n")
        assert len(changed) > len(prompt)
        head, tail = prompt.split(ANCHOR)
        assert changed.startswith(head)
        assert changed.endswith(ANCHOR + tail)
        # The turn itself is not touched.
        assert f"<spreekbeurt>\n{Q_BUDGET}\n</spreekbeurt>" in changed

    def test_a_variant_fails_when_the_heading_is_gone(self):
        with pytest.raises(VariantError):
            before_anchor("Een prompt zonder die kop.", "Een alinea.")

    @pytest.mark.parametrize(
        "quote",
        [
            Q_BUDGET,
            "Kan de minister dat toelichten.",
            "en is het kabinet bereid om dat te doen",
            "Graag een reactie van de minister.",
            "Mijn vraag aan de minister is wat hij gaat doen",
            "Ik hoor graag van de minister of hij die cijfers heeft.",
            "Hoe kijkt de staatssecretaris daarnaar",
            "Dat is een stap vooruit... maar waarom duurt het zo lang",
            "Ik ben benieuwd hoe de minister daartegen aankijkt.",
            "Kan hij dat toezeggen",
        ],
    )
    def test_a_question_or_request_has_question_form(self, quote):
        assert has_question_form(quote)

    @pytest.mark.parametrize(
        "quote",
        [
            STATEMENT,
            "Het kabinet moet ophouden met wijzen naar anderen.",
            "Misschien kunnen wij de minister er nog van overtuigen.",
            "De grote vraag is of een landelijke norm wel uitvoerbaar is.",
            "Ik weet niet hoe de minister dat voor zich ziet.",
            "Dat heeft het kabinet ons nooit uitgelegd.",
            "In het voorjaar heb ik de minister gevraagd of hij dat wilde onderzoeken",
        ],
    )
    def test_a_statement_has_no_question_form(self, quote):
        assert not has_question_form(quote)

    def test_the_check_passes_the_gold_questions_of_the_fixture(self):
        questions = [i for i in FIXTURE["items"] if i["soort"] == "vraag"]
        assert [
            q["citaat"] for q in questions if not has_question_form(q["citaat"])
        ] == []

    def test_the_check_stops_the_statements_of_the_fixture(self):
        stopped = {
            n["type"]
            for n in FIXTURE["negatieven"]
            if not has_question_form(n["citaat"])
        }
        assert {"stelling", "over_kabinet", "oproep"} <= stopped

    def test_the_text_of_a_motion_is_recognised(self):
        motions = [i["citaat"] for i in FIXTURE["items"] if i["soort"] == "motie"]
        assert any(is_motion_text(quote) for quote in motions)
        # One word of the formula is not enough: people use those words.
        assert not is_motion_text("Agressie is aan de orde van de dag.")
        questions = [i["citaat"] for i in FIXTURE["items"] if i["soort"] == "vraag"]
        assert not any(is_motion_text(quote) for quote in questions)
        kept, stopped = apply_check(
            [marking("Verzoekt de regering een plan te maken."), marking(Q_BUDGET)],
            "vraagvorm+geen-motietekst",
        )
        assert [m.citaat for m in kept] == [Q_BUDGET]
        assert len(stopped) == 1

    def test_a_check_only_touches_its_own_kind(self):
        markings = [marking(STATEMENT), marking(STATEMENT, soort="motie")]
        kept, stopped = apply_check(markings, "vraagvorm")
        assert [m.soort for m in kept] == ["motie"]
        assert [m.soort for m in stopped] == ["vraag"]
        assert apply_check(markings, None) == (markings, [])


class TestTheInterruptionBeforeAnAnswer:
    """What the harness hands the service as the turn before, as the worker does."""

    TURNS = FIXTURE["beurten"]

    def _before(self, number: int) -> dict | None:
        index = next(i for i, t in enumerate(self.TURNS) if t["nr"] == number)
        return interruption_before(self.TURNS, index)

    def test_the_interruption_of_a_member_right_before(self):
        assert self._before(25)["nr"] == 24

    def test_the_chairman_in_between_is_passed_over(self):
        turns = [
            {"soort": "interrupter", "fractie": "X", "nr": 1},
            {"soort": "chairman", "fractie": None, "nr": 2},
            {"soort": "speaker", "fractie": None, "nr": 3},
        ]
        assert interruption_before(turns, 2)["nr"] == 1

    def test_a_term_before_is_no_interruption(self):
        assert self._before(18) is None
        assert self._before(1) is None

    def test_only_an_answer_of_the_bewindspersoon_gets_it(self):
        sessie_id = uuid.uuid4()
        answer = beurt_from(self.TURNS[24], sessie_id, self.TURNS[23])
        assert answer.is_bewindspersoon
        assert answer.voorafgaand == "Kamerlid A (X)"
        assert answer.voorafgaand_tekst == self.TURNS[23]["tekst"]
        # The key of the interruption is the key its questions are stored by.
        asked = beurt_from(self.TURNS[23], sessie_id)
        assert answer.voorafgaand_sleutel == asked.sleutel
        member = beurt_from(self.TURNS[23], sessie_id, self.TURNS[21])
        assert (member.voorafgaand, member.voorafgaand_tekst) == (None, "")
        assert member.voorafgaand_sleutel is None


class TestTheProductionPathOnTheFixture:
    """`DebatVraagService` over the made-up debate, the model an oracle."""

    async def test_a_toezegging_that_answers_a_question_is_not_a_second_question(
        self, db_session
    ):
        """The link leaves a vermelding on the question. The harness keeps
        it as a link, and does not count it as the question marked again."""
        gevraagd = (
            "Klopt het dat het budget voor bewaakte stallingen volgend jaar met 12"
            " miljoen euro wordt verlaagd?"
        )
        assert gevraagd in FIXTURE["beurten"][1]["tekst"]

        class Linking(OracleLLM):
            async def _complete(self, prompt: str, max_tokens: int = 1024) -> str:
                if gevraagd in prompt and '{"vragen"' in prompt:
                    return json.dumps(
                        {
                            "vragen": [
                                {
                                    "citaat": gevraagd,
                                    "gericht_aan": "de minister",
                                    "samenvatting": "Wordt het budget verlaagd?",
                                }
                            ]
                        }
                    )
                listed = re.search(r"(\d+)\. Kamerlid A \(X\): Wordt", prompt)
                if listed and "Dat zeg ik toe" in prompt:
                    return json.dumps(
                        {
                            "toezeggingen": [
                                {
                                    # The answer speaks of the budget right
                                    # before it: that is what the link is
                                    # kept on.
                                    "citaat": "Dat zeg ik toe: de Kamer krijgt die"
                                    " brief vóór de begrotingsbehandeling.",
                                    "samenvatting": "Stuurt een brief over het budget.",
                                    "bij_vraag": int(listed.group(1)),
                                }
                            ]
                        }
                    )
                return await super()._complete(prompt, max_tokens)

        block = await run_debate(
            db_session, Linking(FIXTURE), FIXTURE, "synthetisch", max_turns=18
        )
        outcomes = {turn["nr"]: turn for turn in block["beurten"]}
        (vraag,) = outcomes[2]["gemarkeerd"]
        (toezegging,) = outcomes[18]["gemarkeerd"]
        assert (toezegging["soort"], toezegging["herhaling"]) == ("toezegging", False)
        assert toezegging["bij_volgnummer"] == vraag["volgnummer"]
        assert toezegging["gericht_aan"] == "Kamerlid A (X)"
        assert outcomes[18]["ruw"][0]["bij_vraag"] == vraag["volgnummer"]

    async def test_the_code_marks_what_the_oracle_says_and_cleans_up(self, db_session):
        block = await run_debate(db_session, OracleLLM(FIXTURE), FIXTURE, "synthetisch")
        block["gold"] = str(FIXTURE_PATH)
        run = {"meta": {"label": "orakel"}, "debatten": [block]}
        golds = {"synthetisch": FIXTURE}

        outcomes = {turn["nr"]: turn for turn in block["beurten"]}
        assert len(outcomes) == len(FIXTURE["beurten"])
        # The chairman, and a member who interrupts a member without naming
        # a bewindspersoon, are never shown to the model.
        assert outcomes[1]["reden"] == "voorzitter"
        assert outcomes[4]["reden"] == "interruptie van een ander"
        assert outcomes[4]["aanroepen"] == 0
        # An interruption of a member that names the minister is shown.
        assert outcomes[6]["aanroepen"] == 1
        assert block["aanroepen"] == sum(t["aanroepen"] for t in block["beurten"])

        scores, _ = score_run(run, golds)
        vraag = scores["vraag"]
        assert vraag.false_positives == []
        assert vraag.precision == 1.0
        # Everything the oracle was allowed to say was stored as it stands
        # in the gold file. No required question is lost in the code.
        assert vraag.misses == []
        # The repeated question that landed in the turn of the minister is
        # the one thing nobody can find: that turn is skipped.
        assert (vraag.optional, vraag.optional_found) == (2, 1)

        # The moties are found by rule, whatever the oracle says: all six
        # of the made-up debate, the one in a turn the model never saw
        # included, and nothing in the turn of the minister who repeats a
        # dictum or of the member who talks about moties of earlier.
        motie = scores["motie"]
        assert (motie.required, motie.found, motie.optional_found) == (5, 5, 1)
        assert motie.false_positives == []
        assert outcomes[30]["reden"] == ""
        assert outcomes[30]["aanroepen"] == 0
        assert [m["soort"] for m in outcomes[30]["gemarkeerd"]] == ["motie"]
        # That turn holds no words of a commitment either, so it costs no call.
        assert outcomes[31]["reden"] == "bewindspersoon"
        assert outcomes[31]["aanroepen"] == 0
        assert outcomes[32]["gemarkeerd"] == []
        # A question and two moties in one turn: each once.
        assert [m["soort"] for m in outcomes[29]["gemarkeerd"]] == [
            "vraag",
            "motie",
            "motie",
        ]

        # The answers of the minister are read for toezeggingen, and for
        # nothing else: one call each, with the prompt of its own.
        assert outcomes[18]["bewindspersoon"] is True
        assert outcomes[18]["aanroepen"] == 1
        assert [m["soort"] for m in outcomes[18]["gemarkeerd"]] == [
            "toezegging",
            "toezegging",
        ]
        assert {r["soort"] for r in outcomes[18]["ruw"]} == {"toezegging"}
        toezegging = scores["toezegging"]
        assert toezegging.false_positives == []
        # Six the labeller is sure of. Five are in a turn of the minister
        # and are found; the sixth stands in the turn of the member who
        # interrupted, where nothing looks for a toezegging.
        assert (toezegging.required, toezegging.found) == (6, 5)
        assert [(m.item.beurt, m.reason) for m in toezegging.misses] == [
            (22, REASON_NOT_AN_ANSWER)
        ]
        # Of the optional ones the effort is found; the two the chairman
        # reads out at the end are not, his turn is skipped.
        assert (toezegging.optional, toezegging.optional_found) == (3, 1)
        # The refusal and the condition in the last answer are not marked,
        # the toezegging behind them is.
        assert [m["citaat"][:14] for m in outcomes[36]["gemarkeerd"]] == [
            "Wel stuur ik d"
        ]
        # A member who asks for a toezegging is asked about questions.
        assert outcomes[35]["bewindspersoon"] is False
        assert all(m["soort"] != "toezegging" for m in outcomes[35]["gemarkeerd"])

        report = build_report(run, golds)
        assert "Run orakel" in report
        assert "toezegging" not in not_marked(run, golds)

        left = (
            await db_session.execute(
                select(func.count())
                .select_from(DebatSessie)
                .where(DebatSessie.onderwerp == FIXTURE["debat"]["onderwerp"])
            )
        ).scalar()
        assert left == 0
