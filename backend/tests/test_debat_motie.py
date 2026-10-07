"""Finding moties in a turn by rule.

Every sentence in here is made up, the mistakes of the transcript too:
they are of the kinds seen in real debates, not copies of them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bouwmeester.services.debat_motie import (
    MAX_DICTUM,
    VORM_AANGEKONDIGD,
    VORM_INGEDIEND,
    VORM_OVERWOGEN,
    dictum_without_close,
    find_moties,
    is_motion_text,
    motie_vorm,
)

FIXTURE = json.loads(
    (
        Path(__file__).parent / "fixtures" / "debat_markeringen_synthetisch.json"
    ).read_text(encoding="utf-8")
)

DICTUM = "verzoekt de regering om elk station een bewaakte stalling te geven"
CLOSE = "en gaat over tot de orde van de dag"
MOTIE = (
    "De Kamer, gehoord de beraadslaging, constaterende dat 140 stations geen"
    " stalling hebben, overwegende dat reizigers hun fiets kwijtraken,"
    f" {DICTUM}, {CLOSE}."
)


def _one(text: str):
    found = find_moties(text)
    assert len(found) == 1, found
    return found[0]


class TestReadOut:
    def test_the_dictum_is_the_quote(self):
        text = f"Voorzitter, ik heb één motie. {MOTIE} Dank u wel."
        motie = _one(text)

        assert motie.vorm == VORM_INGEDIEND
        assert motie.citaat == f"{DICTUM}, {CLOSE}"
        # Cut from the turn, at the place it says.
        assert text[motie.plek :].startswith(motie.citaat)
        # The whole formula is the motie, from its opening to its close.
        assert text[motie.start : motie.end].startswith("De Kamer, gehoord")
        assert text[motie.start : motie.end].endswith("orde van de dag")

    @pytest.mark.parametrize(
        "opening",
        [
            # A full stop where the speaker took a breath.
            "De Kamer gehoord. De beraadslaging",
            # Another word for the ones in between.
            "de Kamer grondig de beraadslaging",
            "Kamer gehoor de beraadslagingen",
            # Nothing of the opening at all: it fell in the turn before.
            "",
        ],
    )
    def test_a_misheard_opening_does_not_hide_it(self, opening):
        text = f"{opening} constaterende dat er niets gebeurt {DICTUM} {CLOSE}"
        assert _one(text).citaat == f"{DICTUM} {CLOSE}"

    @pytest.mark.parametrize(
        "close",
        [
            "en gaat over tot orde van de dag",
            "Gaat verder tot de orde van de dag",
            "en gaat over tot de... orde van de dag",
            "orde van dag",
        ],
    )
    def test_a_misheard_close_does_not_hide_it(self, close):
        text = f"overwegende dat er niets gebeurt, {DICTUM} {close}. Dank u wel."
        motie = _one(text)
        assert motie.citaat.startswith(DICTUM)
        assert motie.citaat.endswith("dag")

    def test_a_dictum_with_only_its_close_is_one(self):
        """The whole considerans can be in the turn before."""
        assert _one(f"{DICTUM}, {CLOSE}.").vorm == VORM_INGEDIEND

    def test_a_dictum_with_only_its_opening_is_one(self):
        """And the close in the turn after."""
        motie = _one(f"De Kamer, gehoord de beraadslaging, {DICTUM}")
        assert motie.citaat == DICTUM

    def test_a_dictum_alone_is_someone_talking_about_a_motie(self):
        assert find_moties(f"Onze motie van vorig jaar {DICTUM}.") == []
        assert (
            find_moties(f"Het voorstel dat nu voorligt {DICTUM}. Dat steun ik.") == []
        )

    def test_the_formula_without_a_dictum_is_no_motie(self):
        """Nothing to show: what is asked is in another turn."""
        assert find_moties("De Kamer, gehoord de beraadslaging, constaterende") == []
        assert find_moties("en gaat over tot de orde van de dag. Dank u wel.") == []

    def test_two_requests_in_one_motie_are_one_motie(self):
        text = (
            f"overwegende dat het kan, {DICTUM}, en verzoekt de regering de Kamer"
            f" daarover te informeren, {CLOSE}."
        )
        assert "daarover te informeren" in _one(text).citaat

    def test_two_moties_in_one_turn_are_two(self):
        tweede = "verzoekt het kabinet camera's verplicht te stellen"
        text = (
            f"Ik heb er twee. {MOTIE} En de tweede. De Kamer, gehoord de"
            f" beraadslaging, overwegende dat camera's helpen, {tweede}, {CLOSE}."
        )
        eerste, laatste = find_moties(text)
        assert eerste.citaat == f"{DICTUM}, {CLOSE}"
        assert laatste.citaat == f"{tweede}, {CLOSE}"
        assert eerste.end <= laatste.start

    def test_a_motie_whose_close_was_not_heard_ends_where_the_next_begins(self):
        tweede = "verzoekt het kabinet camera's verplicht te stellen"
        text = (
            f"constaterende dat er niets gebeurt, {DICTUM}. De Kamer, gehoord de"
            f" beraadslaging, overwegende dat camera's helpen, {tweede}, {CLOSE}."
        )
        eerste, laatste = find_moties(text)
        assert eerste.citaat == f"{DICTUM}."
        assert laatste.citaat == f"{tweede}, {CLOSE}"

    def test_without_a_close_a_dictum_does_not_run_on_for_a_page(self):
        text = f"overwegende dat het kan, {DICTUM} " + "en nog veel meer " * 200
        motie = _one(text)
        assert len(motie.citaat) <= MAX_DICTUM
        # Cut between two words.
        assert motie.citaat.endswith(("meer", "veel", "nog", "en"))

    @pytest.mark.parametrize(
        "dictum",
        [
            "verzoekt de minister van Voorbeelden om een plan te maken",
            "verzoekt het kabinet om een plan te maken",
            "verzoekt de staatssecretaris de Kamer te informeren",
            "verzoekt het Presidium een debat in te plannen",
            "spreekt uit dat elk station een stalling verdient",
            "roept de regering op om een plan te maken",
        ],
    )
    def test_what_a_dictum_opens_with(self, dictum):
        assert _one(f"overwegende dat het kan, {dictum}, {CLOSE}").citaat.startswith(
            dictum
        )

    def test_who_signed_it_stays_with_the_quote(self):
        text = f"{MOTIE} Mede ingediend door het lid B. Dan mijn tweede punt."
        assert _one(text).citaat.endswith(
            "orde van de dag. Mede ingediend door het lid B"
        )

    def test_the_co_signers_end_where_a_subtitle_line_runs_on(self):
        text = (
            f"overwegende dat het kan, {DICTUM} {CLOSE}... medeondertekend door"
            " het lid B... en dan nog iets heel anders over de begroting"
        )
        assert _one(text).citaat.endswith("medeondertekend door het lid B")

    def test_the_co_signers_do_not_swallow_the_next_motie(self):
        text = (
            f"overwegende dat het kan, {DICTUM} {CLOSE} mede ingediend door het"
            f" lid B de Kamer gehoord de beraadslaging overwegende dat het moet"
            f" verzoekt het kabinet om haast te maken {CLOSE}"
        )
        eerste, laatste = find_moties(text)
        assert eerste.citaat.endswith("mede ingediend door het lid B")
        assert laatste.citaat.startswith("verzoekt het kabinet")

    def test_what_follows_a_motie_is_not_part_of_it(self):
        text = f"{MOTIE} Ik hoop dat de minister deze motie als steun ziet."
        assert _one(text).citaat.endswith("orde van de dag")


class TestAnnounced:
    @pytest.mark.parametrize(
        "zin",
        [
            "Ik zal daar een motie over indienen.",
            "Daar dien ik in de tweede termijn een motie over in.",
            "Ik kondig alvast aan dat ik een motie zal indienen over de stallingen.",
            "Wij dienen hierover een motie in.",
            "Anders zullen wij op dit punt een motie indienen.",
            "Dan wil ik graag twee moties indienen.",
        ],
    )
    def test_an_announcement(self, zin):
        motie = _one(f"Dat stelt mij niet gerust. {zin} Dank u wel.")
        assert motie.vorm == VORM_AANGEKONDIGD
        assert motie.citaat == zin

    @pytest.mark.parametrize(
        "zin",
        [
            "Ik overweeg op dit punt een motie.",
            "Wij overwegen een motie in te dienen als dat antwoord uitblijft.",
        ],
    )
    def test_a_motie_that_is_only_considered(self, zin):
        motie = _one(f"Voorzitter. {zin}")
        assert motie.vorm == VORM_OVERWOGEN
        assert motie.citaat == zin

    @pytest.mark.parametrize(
        "zin",
        [
            # Of earlier.
            "De motie die vorig jaar is aangenomen vroeg daar al om.",
            "Wij hebben daar toen een motie over ingediend.",
            "Ik heb eerder een motie ingediend en die wil ik niet opnieuw indienen.",
            "Ik wil de minister vragen hoe hij de motie uitvoert die wij indienden.",
            # Of someone else.
            "En nu dient Kamerlid B een motie in over het geld.",
            "Kamerlid B gaat hier straks een motie over indienen.",
            "De motie van Kamerlid C gaan wij nog beoordelen.",
            # No motie at all.
            "Als de minister dat toezegt, dan scheelt dat mij een motie.",
            "Ik dien nu geen motie in.",
            "Dan hoef ik daar niet een motie over in te dienen.",
            # The word and nothing that submits.
            "Ik heb nog een vraag over die motie.",
            "Tot slot een motie.",
        ],
    )
    def test_what_is_not_an_announcement(self, zin):
        assert find_moties(f"Voorzitter. {zin} Dank u wel.") == []

    def test_an_announcement_right_before_the_motie_is_the_motie(self):
        """One motie, and the one that is read out says more."""
        motie = _one(f"Ik dien de volgende motie in. {MOTIE}")
        assert motie.vorm == VORM_INGEDIEND

    def test_an_announcement_after_a_motie_is_one_of_its_own(self):
        text = f"{MOTIE} En over het toezicht dien ik later nog een motie in."
        eerste, laatste = find_moties(text)
        assert (eerste.vorm, laatste.vorm) == (VORM_INGEDIEND, VORM_AANGEKONDIGD)

    def test_one_announcement_is_marked_once(self):
        text = "Ik dien twee moties in, een motie over geld en een motie over toezicht."
        assert len(find_moties(text)) == 1

    def test_in_a_transcript_without_full_stops_the_words_around_it_are_kept(self):
        before = "dat is wat ik ervan vind en " * 12
        after = " en dan ga ik nu door naar mijn volgende punt" * 8
        motie = _one(f"{before}daarom dien ik een motie in{after}")
        assert "dien ik een motie in" in motie.citaat
        assert len(motie.citaat) < 200


class TestTheQuoteThatWasStored:
    def test_the_form_is_read_back_from_the_quote(self):
        assert motie_vorm(f"{DICTUM}, {CLOSE}") == VORM_INGEDIEND
        assert motie_vorm("Ik zal daar een motie over indienen.") == VORM_AANGEKONDIGD
        assert motie_vorm("Ik overweeg een motie.") == VORM_OVERWOGEN

    def test_every_quote_the_rule_gives_reads_back_as_what_it_was(self):
        for turn in FIXTURE["beurten"]:
            for motie in find_moties(turn["tekst"]):
                assert motie_vorm(motie.citaat) == motie.vorm

    def test_the_first_line_leaves_the_close_out(self):
        assert dictum_without_close(f"{DICTUM}, {CLOSE}. Mede ingediend") == DICTUM
        assert dictum_without_close(f"{DICTUM} orde van de dag") == DICTUM
        assert dictum_without_close(DICTUM) == DICTUM
        # Whatever the transcript made of the words that lead up to it.
        assert dictum_without_close(f"{DICTUM}. Gaat verder tot orde van de dag") == (
            DICTUM
        )
        # A dictum that itself says "over" keeps it.
        informeren = "verzoekt de regering de Kamer over de voortgang te informeren"
        assert dictum_without_close(f"{informeren}, {CLOSE}") == informeren


class TestMotionTextInAQuestion:
    @pytest.mark.parametrize(
        "quote",
        [
            f"{DICTUM}, {CLOSE}",
            f"overwegende dat reizigers hun fiets kwijtraken, {DICTUM}",
            "De Kamer, gehoord de beraadslaging, constaterende dat het kan",
        ],
    )
    def test_two_parts_of_the_formula_are_motion_text(self, quote):
        assert is_motion_text(quote)

    @pytest.mark.parametrize(
        "quote",
        [
            "Kan de minister zeggen wanneer de telling klaar is?",
            "Is de minister van mening dat dit sneller kan?",
            "Ik verzoek de minister om daarop terug te komen.",
            "Hoe gaat de minister de motie uitvoeren?",
            "Wat is de orde van grootte van dat bedrag per dag?",
            # One word of the formula is a word people use.
            "Agressie is aan de orde van de dag. Wat gaat de minister daaraan doen?",
            "De motie verzoekt de regering om een plan te maken. Wanneer komt dat"
            " plan, minister?",
            "Alles overwegende vraag ik de minister of hij dit wil heroverwegen.",
            "Overwegende dat het kan: wanneer begint de minister?",
            f"{DICTUM}.",
        ],
    )
    def test_a_question_or_a_single_part_is_not(self, quote):
        assert not is_motion_text(quote)


FILL = "Dat is wat wij ervan vinden en daar blijven wij bij. " * 40


class TestThePartsStandCloseTogether:
    """Every part of the formula is also something people just say."""

    def test_a_figure_of_speech_and_a_motie_of_earlier_are_no_motie(self):
        text = (
            "Alles overwegende is dit een slecht plan. Kan de minister toezeggen"
            f" dat hij de Kamer informeert? {FILL}de motie van vorig jaar verzoekt"
            " de regering hiermee te stoppen."
        )
        assert find_moties(text) == []

    @pytest.mark.parametrize(
        "text",
        [
            "die motie verzoekt de regering om een plan te maken en agressie is"
            " aan de orde van de dag",
            "mijn fractie spreekt uit haar hart en dit is aan de orde van de dag",
            "Het voorstel verzoekt de regering om een plan en dat is aan de orde"
            " van de dag",
            "Zij spreekt uit ervaring en gaat over tot de orde van de dag",
            "Overwegende dat het al laat is: ik verzoek de regering om haast te maken.",
            "overwegende dat het kan zeg ik: mijn motie verzoekt de regering om"
            " haast te maken",
            "Alles overwegende verzoekt de regering dit zelf ook, zegt zij.",
            "Ik verzoek de regering om daarop terug te komen, overwegende dat het kan.",
        ],
    )
    def test_ordinary_speech_with_words_of_the_formula(self, text):
        assert find_moties(text) == []

    def test_a_considerans_far_before_a_dictum_is_not_its_considerans(self):
        text = f"overwegende dat het kan, ga ik door. {FILL}{DICTUM}."
        assert find_moties(text) == []

    def test_a_close_far_behind_a_dictum_is_not_its_close(self):
        text = (
            f"overwegende dat het kan, {DICTUM}. Kan de minister zeggen wanneer?"
            f" {FILL}En zo gaat de Kamer over tot de orde van de dag."
        )
        motie = _one(text)
        assert motie.citaat == f"{DICTUM}."
        assert len(text[motie.start : motie.end]) < 200

    def test_a_dictum_without_its_close_ends_with_its_sentence(self):
        """What follows is the rest of the turn, questions and all."""
        vraag = "Kan de minister zeggen wanneer dat klaar is?"
        text = f"overwegende dat het kan, {DICTUM}. {vraag} {FILL}"
        motie = _one(text)
        assert motie.citaat == f"{DICTUM}."
        assert text.index(vraag) >= motie.end

    def test_a_dropped_t_is_still_a_dictum(self):
        text = (
            "overwegende dat het kan, verzoek de regering een plan te maken, en"
            " gaat over tot de orde van de dag"
        )
        assert _one(text).citaat.startswith("verzoek de regering een plan")

    def test_a_long_text_is_read_in_a_blink(self):
        import time

        text = "ik dien een motie in " * 8000
        start = time.perf_counter()
        find_moties(text)
        assert time.perf_counter() - start < 2


class TestTheSpeakerSubmits:
    @pytest.mark.parametrize(
        "zin",
        [
            "wij zullen de motie die de collega gaat indienen steunen",
            "ik vind die motie overbodig indien de minister dit toezegt",
            "we dienen die motie gewoon uit te voeren",
            "dan zie ik af van de motie die ik wilde indienen",
            "wij dienen die motie in te trekken",
        ],
    )
    def test_what_only_looks_like_an_announcement(self, zin):
        assert find_moties(zin) == []
        assert find_moties(f"Voorzitter. {zin[0].upper()}{zin[1:]}. Dank.") == []

    def test_coming_with_a_motie_is_an_announcement(self):
        assert _one("Ik kom in de tweede termijn met een motie.").vorm == (
            VORM_AANGEKONDIGD
        )


class TestOnTheMadeUpDebate:
    def _members(self):
        return [
            turn
            for turn in FIXTURE["beurten"]
            if turn["soort"] != "chairman" and not turn["is_bewindspersoon"]
        ]

    def test_every_motie_of_the_fixture_is_found_and_nothing_else(self):
        gold = {
            (i["beurt"], i["citaat"]) for i in FIXTURE["items"] if i["soort"] == "motie"
        }
        assert len(gold) >= 6
        found = {
            (turn["nr"], motie.citaat)
            for turn in self._members()
            for motie in find_moties(turn["tekst"])
        }
        # The quote of the rule holds the quote of the labeller: the rule
        # takes who signed it along.
        assert len(found) == len(gold)
        for beurt, citaat in gold:
            assert any(nr == beurt and citaat in mine for nr, mine in found), citaat

    def test_the_forms(self):
        vormen = [
            motie.vorm
            for turn in self._members()
            for motie in find_moties(turn["tekst"])
        ]
        assert vormen.count(VORM_INGEDIEND) == 3
        assert vormen.count(VORM_AANGEKONDIGD) == 2
        assert vormen.count(VORM_OVERWOGEN) == 1

    def test_no_question_of_the_fixture_is_motion_text(self):
        questions = [i["citaat"] for i in FIXTURE["items"] if i["soort"] == "vraag"]
        assert not any(is_motion_text(quote) for quote in questions)
