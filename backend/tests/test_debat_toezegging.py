"""A toezegging of the bewindspersoon as a markering.

What counts by its form (`debat_toezegging`), what the service makes of an
answer of the model, what is stored and what is put in the channel, and
what the worker hands over.

Every sentence in here is made up, as is the debate in
`fixtures/debat_markeringen_synthetisch.json`; nothing in it was ever said.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from bouwmeester.models.debat_markering import (
    SOORT_TOEZEGGING,
    SOORT_VRAAG,
    STATUS_BEANTWOORD,
    STATUS_OPEN,
    STATUS_TOEGEWEZEN,
    STATUS_VERVALT,
    STATUS_VERWORPEN,
    VERMELDING_ANTWOORD,
    VERMELDING_HERHALING,
    DebatMarkering,
    DebatMarkeringVermelding,
)
from bouwmeester.models.debat_sessie import DebatSpreekbeurt
from bouwmeester.services import debat_vraag_service as service_mod
from bouwmeester.services import debat_vraag_worker as worker_mod
from bouwmeester.services.debat_statusregel import splits, statusregel
from bouwmeester.services.debat_toezegging import (
    MAX_PASSAGE,
    commitment_passages,
    deadline_is_said,
    has_commitment_form,
    may_hold_commitment,
    shares_a_subject,
)
from bouwmeester.services.debat_vraag_reacties import (
    LEGENDA,
    REACTIE_BEANTWOORD,
    REACTIE_GEEN_VRAAG,
    REACTIE_OPGEPAKT,
    REACTIE_VERVALT,
    stand_marker,
)
from bouwmeester.services.debat_vraag_service import (
    AAN_INTERRUPTIE_BINNEN,
    UITKOMST_AL_BEOORDEELD,
    UITKOMST_GEEN_TOEZEGGING,
    UITKOMST_GEMARKEERD,
    UITKOMST_LLM_ONBEREIKBAAR,
    UITKOMST_LLM_ONBRUIKBAAR,
    UITKOMST_OVERGESLAGEN,
    Beurt,
    DebatContext,
    DebatVraagService,
    answer_parts,
    format_thread,
    format_toezegging_thread,
    lees_toezeggingen,
    rol_van,
)
from bouwmeester.services.llm.base import (
    DEBAT_VRAGEN_ONBEREIKBAAR,
    DEBAT_VRAGEN_ONBRUIKBAAR,
    DebatToezegging,
)
from bouwmeester.services.llm.prompts import build_debat_toezeggingen_prompt
from bouwmeester.services.tk_activiteit import Bewindspersoon
from tests import test_debat_vraag_status as status_helpers
from tests import test_debat_vraag_worker as worker_helpers
from tests.test_debat_vragen import (
    CHANNEL,
    MOMENT_URL,
    NOOT,
    FakeLLM,
    FakeMattermost,
    _sessie,
    antwoord,
    vraag,
)

SYN = json.loads(
    (
        Path(__file__).parent / "fixtures" / "debat_markeringen_synthetisch.json"
    ).read_text(encoding="utf-8")
)
TURNS = {turn["nr"]: turn for turn in SYN["beurten"]}
# The first answer of the minister; a member who asks about the budget; the
# minister's short answers to interruptions; the chairman who reads the
# list; a member who asks for a toezegging and the minister who refuses.
ANTWOORD, VRAAGT, KIJKEN, BEREID, ZEGT_TOE, LIJST, VRAAGT_TOEZEGGING, WEIGERT = (
    TURNS[n] for n in (18, 2, 21, 23, 25, 34, 35, 36)
)
MINISTER = ANTWOORD["spreker"]
T_BRIEF = "Dat zeg ik toe: de Kamer krijgt die brief vóór de begrotingsbehandeling."
T_UITZOEKEN = (
    "Ik zal dat laten uitzoeken en kom daar in het voorjaar schriftelijk op terug."
)
T_ZOMER = (
    "Ja, dat kan ik toezeggen. De Kamer hoort vóór de zomer hoe het gesprek is"
    " verlopen."
)
T_EVALUATIE = (
    "Wel stuur ik de Kamer in het eerste kwartaal de evaluatie van de proef met"
    " camera's."
)
N_STRAKS = "op de camera's kom ik straks terug"
N_LOPEND = (
    "wij zijn op dit moment met de handelsplatforms in gesprek over een meldplicht"
)
N_COLLEGA = (
    "Mijn collega van Vervoer heeft de Kamer vorige week toegezegd dat zij de"
    " proef in Dorpstede zal evalueren."
)
N_WEIGERING = "Nee, dat kan ik niet toezeggen"
N_VOORWAARDE = "Als zij ze willen delen, zou ik kunnen overwegen ze door te sturen."

CONTEXT = DebatContext(
    onderwerp=SYN["debat"]["onderwerp"],
    soort=SYN["debat"]["soort"],
    bewindspersonen=(
        Bewindspersoon(naam="Bewindspersoon A", functie="minister van Voorbeelden"),
    ),
    stukken=tuple(SYN["debat"]["stukken"]),
)
MOMENT = datetime(2030, 1, 14, 9, 36, 0, tzinfo=UTC)


def toezegging(citaat: str, **extra) -> dict:
    return {
        "citaat": citaat,
        "samenvatting": "Samenvatting van de toezegging.",
        "termijn": None,
        "bij_vraag": None,
        "hoort_bij": None,
        **extra,
    }


def toegezegd(*toezeggingen: dict) -> str:
    return json.dumps({"toezeggingen": list(toezeggingen)}, ensure_ascii=False)


def _beurt(sessie_id: uuid.UUID, raw: dict, post_id: str | None, **extra) -> Beurt:
    values = {
        "sessie_id": sessie_id,
        "spreekbeurt_id": None,
        "post_id": post_id,
        "channel_id": CHANNEL,
        "soort": raw["soort"],
        "spreker": raw["spreker"],
        "fractie": raw["fractie"],
        "start": datetime.fromisoformat(raw["start"]),
        "moment_url": MOMENT_URL,
        "tekst": raw["tekst"],
        "is_bewindspersoon": raw["is_bewindspersoon"],
        "onderbroken": raw.get("onderbroken"),
        "onderbroken_is_bewindspersoon": raw.get("onderbroken_is_bewindspersoon")
        or False,
    }
    values.update(extra)
    return Beurt(**values)


async def _rows(session, sessie_id: uuid.UUID) -> list[DebatMarkering]:
    return list(
        (
            await session.execute(
                select(DebatMarkering)
                .where(DebatMarkering.sessie_id == sessie_id)
                .order_by(DebatMarkering.volgnummer)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )


async def _vermeldingen(session, sessie_id: uuid.UUID) -> list:
    return list(
        (
            await session.execute(
                select(
                    DebatMarkeringVermelding.soort,
                    DebatMarkering.volgnummer,
                    DebatMarkeringVermelding.citaat,
                    DebatMarkeringVermelding.spreker,
                )
                .join(
                    DebatMarkering,
                    DebatMarkering.id == DebatMarkeringVermelding.markering_id,
                )
                .where(DebatMarkeringVermelding.sessie_id == sessie_id)
                .order_by(DebatMarkeringVermelding.created_at)
            )
        ).all()
    )


def _is_toezeggingen_prompt(prompt: str) -> bool:
    return '{"toezeggingen"' in prompt and '{"vragen"' not in prompt


# --- the form of a commitment ------------------------------------------


class TestDeVormVanEenToezegging:
    @pytest.mark.parametrize(
        "citaat",
        [
            "Dat zeg ik toe.",
            "Ik zeg u dat graag toe.",
            "Dat zeggen wij toe, voorzitter.",
            "Laat ik u toezeggen dat ik dat meeneem in de rapportage.",
            "Ja, dat kan ik toezeggen.",
            "Dat is dan mijn toezegging aan de Kamer.",
            "Ik zal de Kamer daarover vóór het kerstreces informeren.",
            "Dat ga ik doen.",
            "Dat gaan we dus doen.",
            "We gaan dat samen met de gemeenten onderzoeken.",
            "Ik wil daar een proef mee starten.",
            "Ik stuur de Kamer in het eerste kwartaal een brief.",
            "Ik informeer de Kamer zodra het besluit er is.",
            "Ik kom daar vóór de begrotingsbehandeling schriftelijk op terug.",
            "Daar kom ik in het halfjaarbericht op terug.",
            "Ik neem dat mee in de voortgangsrapportage.",
            "Dat neem ik op met mijn collega van Vervoer.",
            "Ik zoek dat voor u uit.",
            "Ik laat het u weten.",
            "Ik zorg dat er een overzicht komt.",
            "Ik ben bereid om daarover met de vervoerders in gesprek te gaan.",
            "U krijgt dat overzicht voor de zomer.",
            "Voor de zomer krijgt u dat overzicht.",
            "De Kamer ontvangt die evaluatie in het voorjaar.",
            "Die evaluatie komt in het voorjaar naar de Kamer.",
            "Het kabinet komt na de zomer met een voorstel.",
            "Ik maak daar volgend jaar twee miljoen voor vrij.",
            # Speech recognition: no capitals, no full stops, dots where a
            # line runs on.
            "dus die cijfers zal ik laten... natrekken en dan kom ik daar in de"
            " voortgangsbrief op terug",
            "ik ga zo'n proef opzetten in drie gemeenten",
            # An effort: unsure by the codebook, and the model's call.
            "Ik ga kijken of dat lukt, maar ik kan het niet beloven.",
        ],
    )
    def test_a_commitment_has_the_form(self, citaat):
        assert has_commitment_form(citaat)
        assert may_hold_commitment(f"Dank, voorzitter. {citaat} Dan het geld.")

    @pytest.mark.parametrize(
        "citaat",
        [
            # Plain statements.
            "Het budget voor bewaakte stallingen wordt niet verlaagd.",
            "Er is volgend jaar 54 miljoen euro beschikbaar.",
            "Dat is een terecht punt van Kamerlid A.",
            # Work that is going on.
            N_LOPEND,
            "Daar wordt op dit moment hard aan gewerkt.",
            "Wij zijn daarmee bezig.",
            # What someone else promised.
            N_COLLEGA,
            "De gemeenten hebben toegezegd dat zij de stallingen openhouden.",
            # A member who asks for one.
            "Kan de minister toezeggen dat hij de Kamer daarover informeert?",
            "Is de minister bereid om dat toe te zeggen?",
            # The chairman who reads the list.
            "De minister zegt toe de Kamer vóór de begrotingsbehandeling een brief"
            " te sturen.",
            # A condition that commits to nothing.
            N_VOORWAARDE,
            "Dat zou ik kunnen overwegen.",
        ],
    )
    def test_a_statement_has_not(self, citaat):
        assert not has_commitment_form(citaat)

    @pytest.mark.parametrize(
        "citaat",
        [
            N_WEIGERING,
            "Dat kan ik niet toezeggen.",
            "Dat zeg ik niet toe.",
            "Dat ga ik niet doen.",
            "Ik zal dat nu niet toezeggen.",
            "Ik wil daar niet op vooruitlopen.",
            "Wij gaan geen nieuwe regeling maken.",
        ],
    )
    def test_a_refusal_is_dropped(self, citaat):
        assert not has_commitment_form(citaat)
        # The words of a commitment are in it: the model would be asked.
        assert may_hold_commitment(citaat)

    @pytest.mark.parametrize(
        "citaat",
        [
            # The negation far behind the wording, in the same clause.
            "ik stuur u daar op dit moment geen brief over",
            "ik zal dat onderzoek op dit moment zeker niet laten doen",
            # What was promised before, by someone else or by the speaker.
            "mijn voorganger heeft toegezegd dat de kamer een brief krijgt",
            "ik heb dat vorige week al toegezegd",
            # A question told back.
            "u vraagt of ik kan toezeggen dat de kamer daarover een brief krijgt",
            # Later in this debate, whatever it comes in.
            "ik kom daar in de tweede termijn schriftelijk op terug",
            # No commitment at all.
            "ik kom uit een gezin met drie kinderen",
        ],
    )
    def test_what_a_reviewer_found_getting_through_is_dropped(self, citaat):
        assert not has_commitment_form(citaat)
        # And the model is not pointed at it either.
        assert commitment_passages(f"Dank, voorzitter. {citaat}. Dan het geld.") == []
        zin = citaat[0].upper() + citaat[1:] + "."
        assert commitment_passages(f"Dank, voorzitter. {zin} Dan het geld.") == []

    @pytest.mark.parametrize(
        "citaat",
        [
            "de kamer wordt daarover voor de zomer geinformeerd",
            "De Kamer wordt daarover vóór de zomer geïnformeerd.",
            "er komt een brief voor de begrotingsbehandeling",
            "bij dezen toegezegd",
            "Dat is toegezegd.",
            "die toezegging doe ik graag",
            "prima doen we",
            # A contrast is no refusal.
            "ik kom daar niet nu maar schriftelijk voor de zomer op terug",
            "Ik stuur die brief niet morgen maar volgende week.",
            # Before the second term, in writing: that is a commitment.
            "Ik kom daar schriftelijk vóór de tweede termijn op terug.",
            # A word between who and the verb, and the cabinet preparing.
            "Wat ik wel wil doen is de regels nog eens nalopen.",
            "Het kabinet bereidt daarover een brief voor.",
            "Ik kom vóór de zomer met een voorstel.",
            # A condition behind it is not its refusal.
            "Ik zal de Kamer informeren als het niet lukt.",
        ],
    )
    def test_forms_that_have_to_reach_the_model(self, citaat):
        assert may_hold_commitment(citaat)
        assert has_commitment_form(citaat)

    @pytest.mark.parametrize(
        "citaat",
        [
            "Dat is vorige week al toegezegd door mijn collega.",
            "De gemeente heeft toegezegd dat er een overzicht komt.",
            "Ik heb vorig jaar toegezegd dat ik de Kamer zou informeren.",
            "De Kamer vroeg of ik wil toezeggen dat er een evaluatie komt.",
        ],
    )
    def test_what_was_promised_or_asked_before_is_not_promised_now(self, citaat):
        assert not has_commitment_form(citaat)

    def test_a_refusal_without_a_comma_does_not_reach_past_maar(self):
        assert has_commitment_form(
            "dat kan ik niet toezeggen maar ik zal het wel laten uitzoeken"
        )
        assert not has_commitment_form(
            "dat kan ik niet toezeggen maar het is een goed idee"
        )

    def test_the_dot_in_a_number_ends_no_sentence(self):
        assert has_commitment_form("Ik maak daar volgend jaar 750.000 euro voor vrij.")

    def test_a_wording_does_not_reach_over_a_full_stop(self):
        assert not has_commitment_form("Daar kom ik vandaan. Terug naar het geld.")
        assert not has_commitment_form("Zo doen. We zijn er bijna.")

    def test_a_negation_in_the_next_sentence_refuses_nothing(self):
        assert has_commitment_form(
            "Ik stuur de Kamer een brief. Dat is niet te veel gevraagd."
        )
        # Nor a dozen words on, where no clause is that long.
        assert has_commitment_form(
            "ik stuur de kamer voor de zomer een brief over de bezetting van alle"
            " bewaakte stallingen per provincie en dat is niet te veel gevraagd"
        )

    def test_a_refusal_does_not_hide_the_commitment_behind_it(self):
        assert has_commitment_form(WEIGERT["tekst"])
        assert has_commitment_form(
            "Dat kan ik niet toezeggen, maar ik zal het wel laten uitzoeken."
        )

    def test_not_only_is_no_refusal(self):
        assert has_commitment_form(
            "Ik zal niet alleen de Kamer informeren, maar ook de gemeenten."
        )

    @pytest.mark.parametrize(
        "citaat",
        [
            N_STRAKS,
            "Daar kom ik zo op terug.",
            "Daar kom ik zo meteen nog op.",
            "Ik ga daar zo op in.",
            "Dat zal ik straks toelichten.",
            # The word that says when can stand in front of the verb.
            "Straks zal ik daar meer over zeggen.",
            "Ik kom daar in de tweede termijn op terug.",
            "Daar zal ik in het volgende blokje iets over zeggen.",
        ],
    )
    def test_later_in_this_debate_is_dropped(self, citaat):
        assert not has_commitment_form(citaat)

    @pytest.mark.parametrize(
        "citaat",
        [
            "Ik kom daarop terug.",
            "Daar kom ik nog op terug.",
            "Ik zal daar op terugkomen.",
        ],
    )
    def test_coming_back_without_a_moment_or_a_product_is_dropped(self, citaat):
        assert not has_commitment_form(citaat)

    @pytest.mark.parametrize(
        "citaat",
        [
            "Ik kom daar voor het kerstreces op terug.",
            "Ik kom daar schriftelijk op terug.",
            "Daar kom ik in een brief op terug.",
            "Ik zal daar zo snel mogelijk op terugkomen.",
            "Ik zal de Kamer die cijfers vóór de tweede termijn doen toekomen.",
        ],
    )
    def test_coming_back_with_one_counts(self, citaat):
        assert has_commitment_form(citaat)

    def test_every_toezegging_of_the_fixture_has_the_form(self):
        for item in SYN["items"]:
            if item["soort"] != "toezegging" or TURNS[item["beurt"]]["soort"] == (
                "chairman"
            ):
                continue
            assert has_commitment_form(item["citaat"]), item["citaat"]

    def test_the_negatives_of_the_fixture_in_an_answer_have_not(self):
        types = {
            "later_in_debat",
            "lopend_beleid",
            "toezegging_van_ander",
            "weigering",
            "voorwaardelijk",
        }
        found = [n for n in SYN["negatieven"] if n["type"] in types]
        assert {n["type"] for n in found} == types
        for negative in found:
            assert not has_commitment_form(negative["citaat"]), negative["citaat"]

    def test_a_turn_without_the_words_is_not_worth_a_call(self):
        assert not may_hold_commitment(TURNS[31]["tekst"])
        assert not may_hold_commitment("Dank u wel, voorzitter.")
        assert may_hold_commitment(ANTWOORD["tekst"])

    def test_what_passes_as_a_quote_passes_as_a_turn(self):
        """The check before the call must never be stricter than the one after."""
        for item in SYN["items"]:
            if has_commitment_form(item["citaat"]):
                assert may_hold_commitment(TURNS[item["beurt"]]["tekst"])

    @pytest.mark.parametrize(
        ("termijn", "citaat", "gezegd"),
        [
            ("vóór de begrotingsbehandeling", T_BRIEF, True),
            ("in het voorjaar", T_UITZOEKEN, True),
            ("in het eerste kwartaal", T_EVALUATIE, True),
            # Short words are a moment too.
            ("in mei", "Ik stuur de Kamer in mei een brief.", True),
            # The wrong way round is not what was said.
            ("voor de zomer", "Ik stuur de Kamer na de zomer een brief.", False),
            ("na de zomer", "Ik stuur de Kamer na de zomer een brief.", True),
            # The words, one after the other; a line that runs on is one line.
            ("voor de zomer", "Ik stuur de Kamer voor... de zomer een brief.", True),
            ("de zomer voor", "Ik stuur de Kamer voor de zomer een brief.", False),
            ("zomer", "Ik stuur de Kamer in de nazomer een brief.", False),
            # Worked out by the model, not said.
            ("eind 2030", T_UITZOEKEN, False),
            ("voor het kerstreces", T_UITZOEKEN, False),
            ("", T_BRIEF, False),
        ],
    )
    def test_a_deadline_has_to_be_in_the_quote(self, termijn, citaat, gezegd):
        assert deadline_is_said(termijn, citaat) is gezegd


class TestWaarHetModelKijkt:
    def test_the_sentences_of_an_answer_that_look_like_a_toezegging(self):
        assert commitment_passages(ANTWOORD["tekst"]) == [T_BRIEF, T_UITZOEKEN]

    def test_a_refusal_is_none_and_what_follows_it_is(self):
        assert commitment_passages(WEIGERT["tekst"]) == [T_EVALUATIE]

    @pytest.mark.parametrize(
        "zin",
        [
            "Ik wil daar drie dingen over zeggen.",
            "Ik ga eerst in op het geld.",
            "Dat zal ik toelichten.",
            "Wij zijn daarmee bezig.",
            "Daar kom ik zo op terug.",
        ],
    )
    def test_what_a_bewindspersoon_says_all_the_time_is_none(self, zin):
        assert commitment_passages(f"Dank, voorzitter. {zin} Dan het geld.") == []

    @pytest.mark.parametrize(
        "zin",
        [
            "Ik zal dat voor de zomer doen.",
            "Ik ga de Kamer daarover een brief sturen.",
            "Het kabinet komt in het voorjaar met een voorstel.",
            "Dat zeg ik toe.",
            "Ik neem dat mee.",
        ],
    )
    def test_with_a_moment_a_product_or_the_word_itself_it_is_one(self, zin):
        assert commitment_passages(f"Dank, voorzitter. {zin} Dan het geld.") == [zin]

    def test_a_line_that_runs_on_stays_one_sentence(self):
        zin = "Ik stuur de Kamer... voor de zomer een brief... over de stallingen."
        assert commitment_passages(f"Dank. {zin} Dan het geld.") == [zin]

    def test_no_more_than_the_limit_and_none_longer_than_a_few_lines(self):
        tekst = "Ik stuur de Kamer een brief. " * 40
        assert len(commitment_passages(tekst, limit=5)) == 5
        lang = "Ik stuur de Kamer een brief over " + "de stallingen en " * 60 + "meer."
        (passage,) = commitment_passages(lang)
        assert len(passage) == MAX_PASSAGE

    def test_every_passage_would_pass_as_a_quote(self):
        for turn in SYN["beurten"]:
            for passage in commitment_passages(turn["tekst"]):
                assert has_commitment_form(passage)


class TestHetzelfdeOnderwerp:
    ONDERWERP = SYN["debat"]["onderwerp"]

    def test_a_toezegging_and_the_question_it_answers(self):
        assert shares_a_subject(
            "Stuurt de Kamer een overzicht van de bezetting per provincie.",
            "Kan de minister de bezetting per provincie in beeld brengen?",
            self.ONDERWERP,
        )

    def test_words_that_start_alike_are_the_same_word(self):
        assert shares_a_subject(
            "Laat onderzoeken of er op de bewaking bezuinigd wordt.",
            "Komt er een onderzoek naar de bezuinigingen op bewakers?",
        )

    def test_the_subject_of_the_debate_is_shared_by_everything(self):
        een = "Stuurt een brief over de fietsenstallingen bij de stations."
        ander = "Wat kosten de fietsenstallingen bij de stations?"
        assert shares_a_subject(een, ander)
        assert not shares_a_subject(een, ander, self.ONDERWERP)

    def test_the_words_of_asking_and_promising_do_not_count(self):
        assert not shares_a_subject(
            "De minister zegt toe de Kamer daarover schriftelijk te informeren.",
            "Kan de minister toezeggen dat hij de Kamer daarover informeert?",
        )

    def test_one_word_is_not_enough(self):
        assert not shares_a_subject(
            "Neemt de uitvoering mee in de rapportage over handhaving.",
            "Wanneer komt de evaluatie van de handhaving?",
        )


# --- what the model answered -------------------------------------------


def _t(citaat: str, **extra) -> DebatToezegging:
    return DebatToezegging(**{"citaat": citaat, "samenvatting": "Kort.", **extra})


class TestLeesToezeggingen:
    TEKST = ANTWOORD["tekst"]
    VRAAG = "Bezetting per provincie? Kan de minister de bezetting per provincie geven?"
    BELOOFD = "Stuurt de Kamer een overzicht van de bezetting per provincie."

    def test_a_new_toezegging(self):
        nieuw, herhaald, afgevallen = lees_toezeggingen(
            [_t(T_BRIEF, termijn="vóór de begrotingsbehandeling")],
            self.TEKST,
            {},
            set(),
        )
        assert (herhaald, afgevallen) == ([], 0)
        (een,) = nieuw
        assert een.soort == SOORT_TOEZEGGING
        assert een.citaat == T_BRIEF
        assert een.termijn == "vóór de begrotingsbehandeling"
        assert een.plek == self.TEKST.index(T_BRIEF)
        assert (een.bij_volgnummer, een.gericht_aan, een.stuk) == (None, "", None)

    def test_a_quote_that_is_not_in_the_turn_is_dropped(self):
        nieuw, _, afgevallen = lees_toezeggingen(
            [_t("Ik stuur de Kamer volgende week een brief over de camera's.")],
            self.TEKST,
            {},
            set(),
        )
        assert (nieuw, afgevallen) == ([], 1)

    @pytest.mark.parametrize("citaat", [N_STRAKS, N_LOPEND, N_COLLEGA])
    def test_what_is_in_the_turn_and_no_commitment_is_dropped(self, citaat):
        nieuw, herhaald, afgevallen = lees_toezeggingen(
            [_t(citaat)], self.TEKST, {}, set()
        )
        assert (nieuw, herhaald, afgevallen) == ([], [], 1)

    def test_a_refusal_and_a_condition_are_dropped_and_the_rest_is_kept(self):
        nieuw, _, afgevallen = lees_toezeggingen(
            [_t(N_WEIGERING), _t(N_VOORWAARDE), _t(T_EVALUATIE)],
            WEIGERT["tekst"],
            {},
            set(),
        )
        assert [n.citaat for n in nieuw] == [T_EVALUATIE]
        assert afgevallen == 2

    def test_the_same_quote_twice_is_one_toezegging(self):
        nieuw, _, afgevallen = lees_toezeggingen(
            [_t(T_BRIEF), _t(T_BRIEF)], self.TEKST, {}, set()
        )
        assert (len(nieuw), afgevallen) == (1, 1)

    def test_one_said_again_is_a_herhaling(self):
        nieuw, herhaald, _ = lees_toezeggingen(
            [_t(T_BRIEF, hoort_bij=4)], self.TEKST, {}, {4}
        )
        assert nieuw == []
        assert [(h.volgnummer, h.citaat, h.soort) for h in herhaald] == [
            (4, T_BRIEF, VERMELDING_HERHALING)
        ]

    def test_two_on_the_same_earlier_one_are_one_herhaling(self):
        nieuw, herhaald, _ = lees_toezeggingen(
            [_t(T_BRIEF, hoort_bij=4), _t(T_UITZOEKEN, hoort_bij=4)],
            self.TEKST,
            {},
            {4},
        )
        assert nieuw == []
        assert [(h.volgnummer, h.citaat) for h in herhaald] == [(4, T_BRIEF)]

    def test_a_number_that_is_no_earlier_toezegging_makes_it_new(self):
        # 7 is a question, not a toezegging of this bewindspersoon.
        nieuw, herhaald, _ = lees_toezeggingen(
            [_t(T_BRIEF, hoort_bij=7)], self.TEKST, {7: self.VRAAG}, {4}
        )
        assert (len(nieuw), herhaald) == (1, [])

    def test_the_question_it_answers_is_kept_when_it_is_open(self):
        nieuw, _, _ = lees_toezeggingen(
            [_t(T_BRIEF, samenvatting=self.BELOOFD, bij_vraag=7)],
            self.TEKST,
            {7: self.VRAAG},
            set(),
            CONTEXT.onderwerp,
        )
        assert nieuw[0].bij_volgnummer == 7

    @pytest.mark.parametrize("nummer", [0, 8, 99, -1])
    def test_a_number_the_model_made_up_is_no_link(self, nummer):
        nieuw, _, _ = lees_toezeggingen(
            [_t(T_BRIEF, samenvatting=self.BELOOFD, bij_vraag=nummer)],
            self.TEKST,
            {7: self.VRAAG},
            {8},
        )
        assert nieuw[0].bij_volgnummer is None

    def test_a_question_about_something_else_is_no_link(self):
        # Both are about the stallingen, as everything in this debate is.
        ander = "Wat kosten de camera's in de stallingen bij de stations?"
        nieuw, _, _ = lees_toezeggingen(
            [_t(T_BRIEF, samenvatting=self.BELOOFD, bij_vraag=7)],
            self.TEKST,
            {7: ander},
            set(),
            CONTEXT.onderwerp,
        )
        assert len(nieuw) == 1
        assert nieuw[0].bij_volgnummer is None

    def test_a_deadline_that_was_not_said_is_left_out(self):
        nieuw, _, _ = lees_toezeggingen(
            [_t(T_UITZOEKEN, termijn="eind 2030")], self.TEKST, {}, set()
        )
        assert nieuw[0].termijn is None

    def test_a_long_summary_and_a_long_deadline_are_cut(self):
        nieuw, _, _ = lees_toezeggingen(
            [_t(T_UITZOEKEN, samenvatting="x" * 500, termijn="voorjaar " * 40)],
            self.TEKST,
            {},
            set(),
        )
        assert len(nieuw[0].samenvatting) == service_mod.MAX_SAMENVATTING
        # A moment that long is not one that was said.
        assert nieuw[0].termijn is None


# --- the prompt and the provider ---------------------------------------


def _prompt(**extra) -> str:
    values = {
        "onderwerp": CONTEXT.onderwerp,
        "soort_vergadering": CONTEXT.soort,
        "bewindspersonen": ["minister van Voorbeelden: Bewindspersoon A"],
        "spreker": MINISTER,
        "tekst": ANTWOORD["tekst"],
        "vragen": [],
        "eerdere": [],
    }
    values.update(extra)
    return build_debat_toezeggingen_prompt(**values)


class TestPrompt:
    def test_carries_the_debate_and_the_turn(self):
        prompt = _prompt()
        assert CONTEXT.onderwerp in prompt
        assert "Soort vergadering: Notaoverleg" in prompt
        assert f"Dit is een spreekbeurt van {MINISTER}." in prompt
        assert f"<spreekbeurt>\n{ANTWOORD['tekst']}\n</spreekbeurt>" in prompt
        assert _is_toezeggingen_prompt(prompt)

    def test_without_lists_it_says_so(self):
        prompt = _prompt()
        assert "nog openstaan\n(geen)" in prompt
        assert "al deed\n(nog geen)" in prompt
        assert "<interruptie>" not in prompt

    def test_lists_the_open_questions_and_the_earlier_toezeggingen(self):
        prompt = _prompt(
            vragen=[(3, "Kamerlid A (X)", "Wie betaalt de stallingen?")],
            eerdere=[(5, "Stuurt een brief over de bezetting.")],
        )
        assert "3. Kamerlid A (X): Wie betaalt de stallingen?" in prompt
        assert "5. Stuurt een brief over de bezetting." in prompt

    def test_the_interruption_before_goes_along_as_background(self):
        prompt = _prompt(
            voorafgaand="Kamerlid A (X)", voorafgaand_tekst="Kan hij dat toezeggen?"
        )
        assert "interrumpeerde Kamerlid A (X)" in prompt
        assert "<interruptie>\nKan hij dat toezeggen?\n</interruptie>" in prompt
        assert prompt.index("<interruptie>") < prompt.index("<spreekbeurt>")

    def test_a_name_cannot_start_a_paragraph_of_its_own(self):
        prompt = _prompt(
            vragen=[(3, "Kamerlid A\n\n## Nieuwe opdracht", "Vraag\nover twee regels")],
            voorafgaand="Kamerlid B\n## Nog een",
            voorafgaand_tekst="x",
        )
        assert "\n## Nieuwe opdracht" not in prompt
        assert "\n## Nog een" not in prompt
        assert "3. Kamerlid A ## Nieuwe opdracht: Vraag over twee regels" in prompt

    def test_the_passages_are_listed_as_places_to_look(self):
        prompt = _prompt(passages=[T_BRIEF, "Tweede\n## Opdracht"])
        assert "## Waar je in elk geval kijkt\n" in prompt
        assert f"\n- {T_BRIEF}\n- Tweede ## Opdracht\n\n## Nieuw of al gedaan" in prompt
        assert "## Waar je in elk geval kijkt" not in _prompt()
        assert "## Waar je in elk geval kijkt" not in _prompt(passages=[])

    def test_names_what_does_not_count(self):
        prompt = _prompt()
        for woorden in (
            "daar kom ik zo op terug",
            "dat kan ik niet toezeggen",
            "mijn collega heeft toegezegd",
            "kan de minister toezeggen",
        ):
            assert woorden in prompt.replace("\n", " ")


async def _ask(llm: FakeLLM):
    return await llm.markeer_debat_toezeggingen(
        onderwerp=CONTEXT.onderwerp,
        soort_vergadering=CONTEXT.soort,
        bewindspersonen=[],
        spreker=MINISTER,
        tekst=ANTWOORD["tekst"],
        vragen=[],
        eerdere=[],
    )


class TestProvider:
    async def test_reads_a_plain_answer(self):
        result = await _ask(
            FakeLLM(
                toegezegd(
                    toezegging(
                        T_BRIEF, termijn="vóór de begroting", bij_vraag="3", hoort_bij=2
                    )
                )
            )
        )
        assert result.fout is None
        (een,) = result.toezeggingen
        assert (een.citaat, een.termijn, een.bij_vraag, een.hoort_bij) == (
            T_BRIEF,
            "vóór de begroting",
            3,
            2,
        )

    async def test_nothing_promised_is_an_answer_not_a_failure(self):
        result = await _ask(FakeLLM(toegezegd()))
        assert (result.toezeggingen, result.fout) == ([], None)

    async def test_an_unreachable_model_is_not_asked_twice(self):
        llm = FakeLLM(RuntimeError("weg"), toegezegd(toezegging(T_BRIEF)))
        result = await _ask(llm)
        assert result.fout == DEBAT_VRAGEN_ONBEREIKBAAR
        assert len(llm.prompts) == 1

    async def test_an_unreadable_answer_gets_a_second_chance(self):
        llm = FakeLLM("geen json", toegezegd(toezegging(T_BRIEF)))
        result = await _ask(llm)
        assert [t.citaat for t in result.toezeggingen] == [T_BRIEF]
        assert len(llm.prompts) == 2

    @pytest.mark.parametrize("onzin", ["geen json", "[]", '{"vragen": []}'])
    async def test_twice_unreadable_is_unusable(self, onzin):
        result = await _ask(FakeLLM(onzin, onzin))
        assert result.fout == DEBAT_VRAGEN_ONBRUIKBAAR

    async def test_one_bad_item_does_not_take_the_rest_along(self):
        raw = json.dumps(
            {
                "toezeggingen": [
                    "geen object",
                    {"samenvatting": "zonder citaat"},
                    {"citaat": "  "},
                    {"citaat": T_BRIEF, "termijn": 2030, "bij_vraag": True},
                ]
            }
        )
        result = await _ask(FakeLLM(raw))
        (een,) = result.toezeggingen
        assert (een.termijn, een.bij_vraag, een.samenvatting) == (None, None, "")


# --- the reply and the status block ------------------------------------


def _thread(**extra) -> str:
    values = {
        "volgnummer": 7,
        "aan": "Kamerlid A (X)",
        "citaat": T_BRIEF,
        "samenvatting": "Stuurt de Kamer een overzicht van de bezetting per provincie.",
        "termijn": "vóór de begrotingsbehandeling",
        "bij_volgnummer": 3,
        "moment": MOMENT,
        "moment_url": None,
    }
    values.update(extra)
    return format_toezegging_thread(**values)


class TestFormatToezeggingThread:
    def test_the_whole_reply(self):
        assert _thread() == (
            "🤝 **Stuurt de Kamer een overzicht van de bezetting per provincie.**\n"
            "Toezegging 7 · aan Kamerlid A (X) · vóór de begrotingsbehandeling ·"
            " bij vraag 3 · 10:36 (begin van de spreekbeurt)\n"
            f"> {T_BRIEF}\n"
            "\n"
            f"{NOOT}"
        )

    def test_what_is_not_known_is_left_out(self):
        regels = _thread(aan="", termijn=None, bij_volgnummer=None).split("\n")
        assert regels[1] == "Toezegging 7 · 10:36 (begin van de spreekbeurt)"

    def test_the_time_links_to_the_moment_it_was_said(self):
        moment = datetime(2030, 1, 14, 9, 41, 5, tzinfo=UTC)
        tekst = _thread(moment_url=MOMENT_URL, vraag_moment=moment)
        assert "· [10:41](https://debatdirect.example/" in tekst
        assert "begin van de spreekbeurt" not in tekst

    def test_a_later_reply_in_the_thread_ends_with_the_quote(self):
        assert _thread(first_in_thread=False).endswith(f"> {T_BRIEF}")

    def test_without_a_summary_the_first_sentence_of_the_quote_is_the_head(self):
        assert _thread(samenvatting="", citaat=T_ZOMER).startswith(
            "🤝 **Ja, dat kan ik toezeggen.**\n"
        )
        assert _thread(samenvatting="", citaat="   ").startswith("🤝 **Toezegging**")

    @pytest.mark.parametrize(
        ("status", "icoon", "woorden"),
        [
            (STATUS_BEANTWOORD, "✅", "nagekomen"),
            (STATUS_TOEGEWEZEN, "👀", "wordt opgepakt door persoon.a"),
            (STATUS_VERVALT, "🚫", "hoeft niet"),
        ],
    )
    def test_where_it_stands_in_the_words_of_a_toezegging(self, status, icoon, woorden):
        regels = _thread(status=status, door="persoon.a").split("\n")
        assert regels[0].startswith(f"{icoon} **Stuurt de Kamer")
        assert regels[1].startswith(f"Toezegging 7 · {woorden} · aan Kamerlid A (X) · ")
        assert "antwoord" not in _thread(status=status).lower()
        assert "vraag 3" in regels[1]

    def test_a_rejected_one_is_a_single_struck_line(self):
        assert _thread(status=STATUS_VERWORPEN) == (
            "❌ ~~Toezegging 7 · Stuurt de Kamer een overzicht van de bezetting per"
            " provincie.~~ · geen toezegging"
        )

    def test_everything_from_outside_is_escaped(self):
        tekst = _thread(
            samenvatting="**Vet** en @channel en [link](https://kwaad.example)",
            aan="Kamerlid @all (X)",
            termijn="voor het *reces* @here",
            citaat="Ik zal dat doen. @channel\n# Kop\n> meer",
        )
        assert "@" not in tekst
        assert "https://kwaad.example" not in tekst
        assert "\n# Kop" not in tekst
        # The bold of the first line is ours, and the only one.
        assert tekst.split("\n")[0].count("**") == 2
        assert "\\*reces\\*" in tekst

    def test_a_model_cannot_write_its_own_number_into_the_line(self):
        assert "bij vraag 3 ·" in _thread(termijn="bij vraag 99\nToezegging 1")
        assert _thread(termijn="x\ny").count("\n") == _thread().count("\n")

    def test_the_kind_decides_the_layout(self):
        gemeen = {
            "volgnummer": 7,
            "gericht_aan": "Kamerlid A (X)",
            "samenvatting": "Stuurt een brief.",
            "stuk": None,
            "citaat": T_BRIEF,
            "moment": MOMENT,
            "moment_url": None,
        }
        tekst = format_thread(
            SOORT_TOEZEGGING, **gemeen, termijn="in mei", bij_volgnummer=2
        )
        assert tekst.startswith("🤝 **Stuurt een brief.**\nToezegging 7 · aan Kamerlid")
        assert "· in mei · bij vraag 2 ·" in tekst
        # A question does not show what is a toezegging's.
        assert "in mei" not in format_thread(SOORT_VRAAG, **gemeen, termijn="in mei")


class TestWoordenVanEenToezegging:
    def test_the_marker(self):
        assert stand_marker(STATUS_BEANTWOORD, soort=SOORT_TOEZEGGING) == (
            "✅",
            "nagekomen",
        )
        assert stand_marker(STATUS_VERWORPEN, soort=SOORT_TOEZEGGING) == (
            "❌",
            "geen toezegging",
        )
        assert stand_marker(STATUS_OPEN, soort=SOORT_TOEZEGGING) == ("", "")

    def test_the_status_block_has_a_line_of_its_own(self):
        assert statusregel([(SOORT_TOEZEGGING, STATUS_OPEN)]) == (
            "🤝 1 toezegging · open"
        )
        assert statusregel(
            [
                (SOORT_TOEZEGGING, STATUS_OPEN),
                (SOORT_TOEZEGGING, STATUS_BEANTWOORD),
                (SOORT_VRAAG, STATUS_OPEN),
            ]
        ) == ("❓ 1 vraag · open\n🤝 2 toezeggingen · 1 open · 1 nagekomen")

    def test_the_states_in_its_own_words(self):
        assert statusregel([(SOORT_TOEZEGGING, STATUS_TOEGEWEZEN)]) == (
            "🤝 1 toezegging · wordt opgepakt"
        )
        assert statusregel([(SOORT_TOEZEGGING, STATUS_VERVALT)]) == (
            "🤝 1 toezegging · hoeft niet"
        )
        assert statusregel([(SOORT_TOEZEGGING, STATUS_VERWORPEN)]) == ""

    def test_the_icon_is_no_other_kind_s(self):
        from bouwmeester.services import debat_statusregel as regel

        iconen = list(regel._SOORT_ICOON.values())
        assert len(set(iconen)) == len(iconen)

    def test_the_pinned_message_says_what_the_reactions_mean(self):
        for woorden in ("nagekomen", "hoeft niet", "geen toezegging"):
            assert woorden in LEGENDA
        assert "\n" not in LEGENDA


# --- the service -------------------------------------------------------


async def _judge(
    db_session, raw, *answers, sessie_id=None, mm=None, context=CONTEXT, **extra
):
    sessie_id = sessie_id or await _sessie(db_session)
    mm = mm or FakeMattermost()
    llm = FakeLLM(*answers)
    post_id = mm.turn(f"**{raw['spreker']}** · 10:36\n{raw['tekst'][:60].strip()}")
    result = await DebatVraagService(db_session, mm, llm).beoordeel_beurt(
        _beurt(sessie_id, raw, post_id, **extra), context
    )
    return sessie_id, mm, llm, post_id, result


class TestToezeggingMarkeren:
    async def test_a_toezegging_becomes_a_row_a_thread_and_a_status_line(
        self, db_session
    ):
        sessie_id, mm, llm, post_id, result = await _judge(
            db_session,
            ANTWOORD,
            toegezegd(
                toezegging(
                    T_BRIEF,
                    samenvatting="Stuurt de Kamer de bezetting per provincie.",
                    termijn="vóór de begrotingsbehandeling",
                )
            ),
        )

        assert result.uitkomst == UITKOMST_GEMARKEERD
        assert (result.toezeggingen, result.moties, result.threads) == (1, 0, 1)
        (row,) = await _rows(db_session, sessie_id)
        assert row.id in result.markering_ids
        assert (row.soort, row.status, row.volgnummer) == (
            SOORT_TOEZEGGING,
            STATUS_OPEN,
            1,
        )
        assert row.citaat == T_BRIEF
        assert row.samenvatting == "Stuurt de Kamer de bezetting per provincie."
        assert row.termijn == "vóór de begrotingsbehandeling"
        # In a long answer nobody says who it is promised to.
        assert (row.gericht_aan, row.bij_volgnummer, row.stuk) == ("", None, None)
        assert (row.spreker, row.fractie) == (MINISTER, None)
        assert row.beurt_post_id == post_id

        (reply,) = mm.replies
        assert reply[1] == post_id
        assert reply[2] == (
            "🤝 **Stuurt de Kamer de bezetting per provincie.**\n"
            "Toezegging 1 · vóór de begrotingsbehandeling ·"
            f" [10:36]({MOMENT_URL}) (begin van de spreekbeurt)\n"
            f"> {T_BRIEF}\n"
            "\n"
            f"{NOOT}"
        )
        assert splits(mm.messages[post_id])[1] == "🤝 1 toezegging · open"

    async def test_the_model_is_asked_for_toezeggingen_only(self, db_session):
        _, _, llm, _, _ = await _judge(
            db_session, ANTWOORD, toegezegd(toezegging(T_BRIEF))
        )
        (prompt,) = llm.prompts
        assert _is_toezeggingen_prompt(prompt)
        assert ANTWOORD["tekst"] in prompt
        assert CONTEXT.onderwerp in prompt
        # With the sentences the code found, as places to look.
        assert f"\n- {T_BRIEF}\n- {T_UITZOEKEN}\n\n## Nieuw of al gedaan" in prompt

    async def test_two_in_one_answer_are_numbered_as_they_were_said(self, db_session):
        sessie_id, mm, _, post_id, result = await _judge(
            db_session,
            ANTWOORD,
            toegezegd(toezegging(T_UITZOEKEN), toezegging(T_BRIEF)),
        )
        rows = await _rows(db_session, sessie_id)
        assert [(r.volgnummer, r.citaat) for r in rows] == [
            (1, T_BRIEF),
            (2, T_UITZOEKEN),
        ]
        assert result.toezeggingen == 2
        assert splits(mm.messages[post_id])[1] == "🤝 2 toezeggingen · open"
        # The note about the transcript once, under the first reply.
        assert [NOOT in reply[2] for reply in mm.replies] == [True, False]

    async def test_what_the_model_calls_a_toezegging_and_is_none_leaves_nothing(
        self, db_session
    ):
        sessie_id, mm, llm, _, result = await _judge(
            db_session,
            ANTWOORD,
            toegezegd(
                toezegging(N_STRAKS),
                toezegging(N_LOPEND),
                toezegging(N_COLLEGA),
                toezegging("Ik stuur de Kamer morgen alle cijfers."),
            ),
        )
        assert result.uitkomst == UITKOMST_GEEN_TOEZEGGING
        assert result.afgevallen == 4
        assert await _rows(db_session, sessie_id) == []
        assert mm.replies == []

    async def test_a_refusal_is_not_marked_and_what_follows_it_is(self, db_session):
        sessie_id, _, _, _, result = await _judge(
            db_session,
            WEIGERT,
            toegezegd(
                toezegging(N_WEIGERING),
                toezegging(N_VOORWAARDE),
                toezegging(T_EVALUATIE, termijn="in het eerste kwartaal"),
            ),
        )
        (row,) = await _rows(db_session, sessie_id)
        assert (row.citaat, row.termijn) == (T_EVALUATIE, "in het eerste kwartaal")
        assert result.afgevallen == 2

    async def test_an_answer_without_the_words_of_a_commitment_costs_no_call(
        self, db_session
    ):
        sessie_id, _, llm, _, result = await _judge(db_session, TURNS[31])
        assert (result.uitkomst, result.reden) == (
            UITKOMST_OVERGESLAGEN,
            "bewindspersoon",
        )
        assert llm.prompts == []
        assert await _rows(db_session, sessie_id) == []

    async def test_an_answer_of_a_few_words_costs_no_call(self, db_session):
        _, _, llm, _, result = await _judge(
            db_session, {**ZEGT_TOE, "tekst": "Dat ga ik doen."}
        )
        assert result.uitkomst == UITKOMST_OVERGESLAGEN
        assert llm.prompts == []

    async def test_the_dictum_a_minister_repeats_is_no_motie(self, db_session):
        raw = {
            **TURNS[31],
            "tekst": TURNS[31]["tekst"] + " Ik zal de Kamer daarover informeren.",
        }
        sessie_id, _, llm, _, result = await _judge(db_session, raw, toegezegd())
        assert result.uitkomst == UITKOMST_GEEN_TOEZEGGING
        assert len(llm.prompts) == 1
        assert await _rows(db_session, sessie_id) == []

    async def test_a_bewindspersoon_known_by_surname_only_is_read_too(self, db_session):
        sessie_id, _, llm, _, result = await _judge(
            db_session,
            ANTWOORD,
            toegezegd(toezegging(T_BRIEF)),
            is_bewindspersoon=False,
            spreker="Bob Bewindspersoon (minister van Voorbeelden)",
            context=DebatContext(
                onderwerp=CONTEXT.onderwerp,
                bewindspersonen=(
                    Bewindspersoon(naam="B. Bewindspersoon", functie="minister"),
                ),
            ),
        )
        assert result.toezeggingen == 1
        assert _is_toezeggingen_prompt(llm.prompts[0])

    async def test_a_second_call_for_the_same_turn_does_not_ask_again(self, db_session):
        sessie_id = await _sessie(db_session)
        mm = FakeMattermost()
        post_id = mm.turn()
        beurt = _beurt(sessie_id, ANTWOORD, post_id)
        llm = FakeLLM(
            toegezegd(toezegging(T_BRIEF)), toegezegd(toezegging(T_UITZOEKEN))
        )
        service = DebatVraagService(db_session, mm, llm)

        first = await service.beoordeel_beurt(beurt, CONTEXT)
        again = await service.beoordeel_beurt(beurt, CONTEXT)

        assert again.uitkomst == UITKOMST_AL_BEOORDEELD
        assert again.markering_ids == first.markering_ids
        assert len(llm.prompts) == 1
        assert len(await _rows(db_session, sessie_id)) == 1
        assert len(mm.replies) == 1

    @pytest.mark.parametrize(
        ("answers", "uitkomst", "opnieuw"),
        [
            ((RuntimeError("weg"),), UITKOMST_LLM_ONBEREIKBAAR, True),
            (("geen json", "nog steeds niet"), UITKOMST_LLM_ONBRUIKBAAR, False),
        ],
    )
    async def test_a_model_that_fails_stores_nothing(
        self, db_session, answers, uitkomst, opnieuw
    ):
        sessie_id, mm, _, _, result = await _judge(db_session, ANTWOORD, *answers)
        assert result.uitkomst == uitkomst
        assert result.opnieuw_proberen is opnieuw
        assert await _rows(db_session, sessie_id) == []
        assert mm.replies == []

    async def test_after_a_model_that_was_away_the_turn_is_read_again(self, db_session):
        sessie_id = await _sessie(db_session)
        mm = FakeMattermost()
        beurt = _beurt(sessie_id, ANTWOORD, mm.turn())
        llm = FakeLLM(RuntimeError("weg"), toegezegd(toezegging(T_BRIEF)))
        service = DebatVraagService(db_session, mm, llm)

        assert (await service.beoordeel_beurt(beurt, CONTEXT)).opnieuw_proberen
        assert (await service.beoordeel_beurt(beurt, CONTEXT)).toezeggingen == 1

    async def test_a_thread_that_could_not_be_posted_is_tried_again(self, db_session):
        sessie_id = await _sessie(db_session)
        mm = FakeMattermost()
        mm.fail_sends = 1
        post_id = mm.turn()
        llm = FakeLLM(toegezegd(toezegging(T_BRIEF)))
        service = DebatVraagService(db_session, mm, llm)

        first = await service.beoordeel_beurt(
            _beurt(sessie_id, ANTWOORD, post_id), CONTEXT
        )
        assert (first.toezeggingen, first.threads) == (1, 0)
        assert splits(mm.messages[post_id])[1] == ""

        service.nieuwe_ronde()
        later = await service.beoordeel_beurt(
            _beurt(sessie_id, TURNS[31], mm.turn()), CONTEXT
        )
        assert later.threads == 1
        assert splits(mm.messages[post_id])[1] == "🤝 1 toezegging · open"

    async def test_what_the_model_wrote_is_escaped_in_the_channel(self, db_session):
        _, mm, _, _, _ = await _judge(
            db_session,
            ANTWOORD,
            toegezegd(
                toezegging(
                    T_UITZOEKEN,
                    samenvatting="@channel **lees** dit: https://kwaad.example",
                    termijn="in het voorjaar @all",
                )
            ),
        )
        tekst = mm.replies[0][2]
        assert "@" not in tekst
        assert "https://kwaad.example" not in tekst
        # A moment with anything in it that was not said is not shown at all.
        assert "voorjaar @" not in tekst and " · in het voorjaar" not in tekst


class TestWieNietWordtGelezenVoorToezeggingen:
    async def test_a_member_who_asks_for_one_stays_a_question(self, db_session):
        citaat = VRAAGT_TOEZEGGING["tekst"].removeprefix("Dank, voorzitter. ")
        sessie_id, mm, llm, post_id, result = await _judge(
            db_session, VRAAGT_TOEZEGGING, antwoord(vraag(citaat))
        )
        (prompt,) = llm.prompts
        assert not _is_toezeggingen_prompt(prompt)
        (row,) = await _rows(db_session, sessie_id)
        assert (row.soort, row.citaat) == (SOORT_VRAAG, citaat)
        assert result.toezeggingen == 0
        assert splits(mm.messages[post_id])[1] == "❓ 1 vraag · open"

    async def test_a_member_who_recalls_one_is_not_asked_about_it(self, db_session):
        # "Ik hoor de minister nu iets toezeggen": the model for questions
        # gets the turn, the one for toezeggingen never does.
        _, _, llm, _, result = await _judge(db_session, TURNS[24], antwoord())
        assert all(not _is_toezeggingen_prompt(p) for p in llm.prompts)
        assert result.toezeggingen == 0

    async def test_the_list_the_chairman_reads_is_not_read(self, db_session):
        sessie_id, _, llm, _, result = await _judge(
            db_session,
            LIJST,
            toegezegd(toezegging("De minister zegt toe de Kamer")),
        )
        assert (result.uitkomst, result.reden) == (UITKOMST_OVERGESLAGEN, "voorzitter")
        assert llm.prompts == []
        assert await _rows(db_session, sessie_id) == []

    async def test_a_sentence_of_the_minister_in_the_turn_of_a_member_is_not_found(
        self, db_session
    ):
        """By time alone a line can land in the turn of whoever interrupted.

        The voices put most of those right before the turn is read. What is
        left is not marked: the turn of a member is read for questions and
        moties only.
        """
        sessie_id, _, llm, _, result = await _judge(db_session, TURNS[22], antwoord())
        assert all(not _is_toezeggingen_prompt(p) for p in llm.prompts)
        assert result.toezeggingen == 0
        assert await _rows(db_session, sessie_id) == []


class TestBijWelkeVraag:
    BELOOFD = "Stuurt de Kamer de bezetting per provincie."

    async def _with_question(self, db_session, **extra):
        """A member asks; the question is open as number 1."""
        sessie_id = await _sessie(db_session)
        mm = FakeMattermost()
        citaat = "Kan de minister de bezetting per provincie in beeld brengen?"
        raw = {**VRAAGT, "tekst": f"Voorzitter, dank u wel voor het woord. {citaat}"}
        await _judge(
            db_session,
            raw,
            antwoord(vraag(citaat, samenvatting="Bezetting per provincie?", **extra)),
            sessie_id=sessie_id,
            mm=mm,
        )
        return sessie_id, mm

    async def test_the_model_gets_the_open_questions_with_who_asked(self, db_session):
        sessie_id, mm = await self._with_question(db_session)
        _, _, llm, _, _ = await _judge(
            db_session, ANTWOORD, toegezegd(), sessie_id=sessie_id, mm=mm
        )
        assert "1. Kamerlid A (X): Bezetting per provincie?" in llm.prompts[0]

    async def test_a_toezegging_that_answers_a_question_is_linked_to_it(
        self, db_session
    ):
        sessie_id, mm = await self._with_question(db_session)
        _, _, _, _, result = await _judge(
            db_session,
            ANTWOORD,
            toegezegd(toezegging(T_BRIEF, samenvatting=self.BELOOFD, bij_vraag=1)),
            sessie_id=sessie_id,
            mm=mm,
        )

        vraag_row, toezegging_row = await _rows(db_session, sessie_id)
        assert toezegging_row.bij_volgnummer == 1
        # Promised to whoever asked the question it answers.
        assert toezegging_row.gericht_aan == "Kamerlid A (X)"
        assert "Toezegging 2 · aan Kamerlid A (X) · bij vraag 1 · " in mm.replies[-1][2]
        assert await _vermeldingen(db_session, sessie_id) == [
            (VERMELDING_ANTWOORD, 1, T_BRIEF, MINISTER)
        ]
        # The question stays where it stood: people say when it is answered.
        assert vraag_row.status == STATUS_OPEN
        assert vraag_row.status_at is None
        assert splits(mm.messages[vraag_row.beurt_post_id])[1] == "❓ 1 vraag · open"
        # A link is no herhaling.
        assert result.herhaald == ()

    async def test_a_question_that_is_only_near_it_is_not_linked(self, db_session):
        """The model says it answers question 1; the words say it does not."""
        sessie_id, mm = await self._with_question(db_session)
        await _judge(
            db_session,
            ANTWOORD,
            toegezegd(
                toezegging(
                    T_UITZOEKEN,
                    samenvatting="Laat de besteding van het geld uitzoeken.",
                    bij_vraag=1,
                )
            ),
            sessie_id=sessie_id,
            mm=mm,
        )
        _, toezegging_row = await _rows(db_session, sessie_id)
        assert (toezegging_row.bij_volgnummer, toezegging_row.gericht_aan) == (None, "")
        assert await _vermeldingen(db_session, sessie_id) == []

    async def test_a_number_that_is_no_open_question_links_nothing(self, db_session):
        sessie_id, mm = await self._with_question(db_session)
        await _judge(
            db_session,
            ANTWOORD,
            toegezegd(toezegging(T_BRIEF, samenvatting=self.BELOOFD, bij_vraag=5)),
            sessie_id=sessie_id,
            mm=mm,
        )
        _, toezegging_row = await _rows(db_session, sessie_id)
        assert (toezegging_row.bij_volgnummer, toezegging_row.gericht_aan) == (None, "")
        assert await _vermeldingen(db_session, sessie_id) == []
        assert "bij vraag" not in mm.replies[-1][2]

    async def test_a_question_someone_ticked_off_is_no_longer_offered(self, db_session):
        sessie_id, mm = await self._with_question(db_session)
        (vraag_row,) = await _rows(db_session, sessie_id)
        vraag_row.status = STATUS_BEANTWOORD
        await db_session.commit()

        _, _, llm, _, _ = await _judge(
            db_session,
            ANTWOORD,
            toegezegd(toezegging(T_BRIEF, samenvatting=self.BELOOFD, bij_vraag=1)),
            sessie_id=sessie_id,
            mm=mm,
        )
        assert "nog openstaan\n(geen)" in llm.prompts[0]
        assert (await _rows(db_session, sessie_id))[1].bij_volgnummer is None

    async def test_a_question_to_the_other_bewindspersoon_is_not_this_one_s(
        self, db_session
    ):
        sessie_id, mm = await self._with_question(
            db_session, gericht_aan="de staatssecretaris"
        )
        _, _, llm, _, _ = await _judge(
            db_session,
            ANTWOORD,
            toegezegd(toezegging(T_BRIEF, samenvatting=self.BELOOFD, bij_vraag=1)),
            sessie_id=sessie_id,
            mm=mm,
        )
        assert "nog openstaan\n(geen)" in llm.prompts[0]
        assert (await _rows(db_session, sessie_id))[1].bij_volgnummer is None

    @pytest.mark.parametrize(
        ("spreker", "rol"),
        [
            ("Bewindspersoon A (minister van Voorbeelden)", "de minister"),
            ("Iemand (Staatssecretaris van Voorbeelden)", "de staatssecretaris"),
            ("Iemand Anders", None),
        ],
    )
    def test_what_a_bewindspersoon_is(self, spreker, rol):
        assert rol_van(spreker) == rol

    async def test_two_toezeggingen_on_one_question_are_two_links(self, db_session):
        sessie_id, mm = await self._with_question(db_session)
        await _judge(
            db_session,
            ANTWOORD,
            toegezegd(
                toezegging(T_BRIEF, samenvatting=self.BELOOFD, bij_vraag=1),
                toezegging(
                    T_UITZOEKEN,
                    samenvatting="Zoekt de bezetting per provincie uit.",
                    bij_vraag=1,
                ),
            ),
            sessie_id=sessie_id,
            mm=mm,
        )
        assert [v[:3] for v in await _vermeldingen(db_session, sessie_id)] == [
            (VERMELDING_ANTWOORD, 1, T_BRIEF),
            (VERMELDING_ANTWOORD, 1, T_UITZOEKEN),
        ]


class TestAanWie:
    async def test_the_member_who_interrupted_right_before(self, db_session):
        sessie_id, mm, llm, _, _ = await _judge(
            db_session,
            ZEGT_TOE,
            toegezegd(toezegging(T_ZOMER, termijn="vóór de zomer")),
            voorafgaand="Kamerlid A (X)",
            voorafgaand_tekst=TURNS[24]["tekst"],
        )
        (row,) = await _rows(db_session, sessie_id)
        assert row.gericht_aan == "Kamerlid A (X)"
        assert (
            "Toezegging 1 · aan Kamerlid A (X) · vóór de zomer · " in mm.replies[0][2]
        )
        assert f"<interruptie>\n{TURNS[24]['tekst']}\n</interruptie>" in llm.prompts[0]

    async def test_not_when_it_comes_far_into_the_answer(self, db_session):
        opvulling = "Het budget is dit jaar gelijk gebleven. " * 20
        assert len(opvulling) > AAN_INTERRUPTIE_BINNEN
        raw = {**ZEGT_TOE, "tekst": f"{opvulling}{T_ZOMER}"}
        sessie_id, _, _, _, _ = await _judge(
            db_session,
            raw,
            toegezegd(toezegging(T_ZOMER)),
            voorafgaand="Kamerlid A (X)",
            voorafgaand_tekst="Kan hij dat toezeggen?",
        )
        (row,) = await _rows(db_session, sessie_id)
        assert row.gericht_aan == ""

    async def test_without_an_interruption_before_nobody_is_named(self, db_session):
        sessie_id, mm, _, _, _ = await _judge(
            db_session, ZEGT_TOE, toegezegd(toezegging(T_ZOMER))
        )
        (row,) = await _rows(db_session, sessie_id)
        assert row.gericht_aan == ""
        assert " aan " not in mm.replies[0][2].split("\n")[1]


class TestHerhaald:
    async def _first(self, db_session):
        return await _judge(
            db_session,
            ANTWOORD,
            toegezegd(toezegging(T_BRIEF, samenvatting="Stuurt de brief.")),
        )

    async def test_the_next_answer_gets_what_was_promised_before(self, db_session):
        sessie_id, mm, _, _, _ = await self._first(db_session)
        _, _, llm, _, _ = await _judge(
            db_session, ZEGT_TOE, toegezegd(), sessie_id=sessie_id, mm=mm
        )
        assert "al deed\n1. Stuurt de brief." in llm.prompts[0]

    async def test_another_bewindspersoon_does_not_get_them(self, db_session):
        sessie_id, mm, _, _, _ = await self._first(db_session)
        _, _, llm, _, _ = await _judge(
            db_session,
            ZEGT_TOE,
            toegezegd(),
            sessie_id=sessie_id,
            mm=mm,
            spreker="Iemand Anders (staatssecretaris van Voorbeelden)",
        )
        assert "al deed\n(nog geen)" in llm.prompts[0]

    async def test_only_toezeggingen_are_what_was_promised_before(self, db_session):
        """Whatever else stands on the name of the bewindspersoon is not."""
        sessie_id = await _sessie(db_session)
        db_session.add(
            DebatMarkering(
                sessie_id=sessie_id,
                beurt_sleutel="post:eerder",
                volgnummer=1,
                soort=SOORT_VRAAG,
                channel_id=CHANNEL,
                spreker=MINISTER,
                gericht_aan="de minister",
                citaat="Wat vindt de Kamer daar zelf van?",
                samenvatting="Wat de Kamer vindt.",
                moment=MOMENT,
            )
        )
        await db_session.flush()
        _, _, llm, _, _ = await _judge(
            db_session, ZEGT_TOE, toegezegd(), sessie_id=sessie_id
        )
        assert "al deed\n(nog geen)" in llm.prompts[0]

    async def test_one_said_again_is_a_vermelding_not_a_thread(self, db_session):
        sessie_id, mm, _, _, _ = await self._first(db_session)
        _, _, _, post_id, result = await _judge(
            db_session,
            ZEGT_TOE,
            toegezegd(toezegging(T_ZOMER, hoort_bij=1)),
            sessie_id=sessie_id,
            mm=mm,
        )
        assert result.uitkomst == UITKOMST_GEMARKEERD
        assert (result.herhaald, result.toezeggingen) == ((1,), 0)
        assert len(await _rows(db_session, sessie_id)) == 1
        assert len(mm.replies) == 1
        assert await _vermeldingen(db_session, sessie_id) == [
            (VERMELDING_HERHALING, 1, T_ZOMER, MINISTER)
        ]
        assert splits(mm.messages[post_id])[1] == ""

    async def test_a_rejected_one_is_not_offered_again(self, db_session):
        sessie_id, mm, _, _, _ = await self._first(db_session)
        (row,) = await _rows(db_session, sessie_id)
        row.status = STATUS_VERWORPEN
        await db_session.commit()
        _, _, llm, _, _ = await _judge(
            db_session,
            ZEGT_TOE,
            toegezegd(toezegging(T_ZOMER, hoort_bij=1)),
            sessie_id=sessie_id,
            mm=mm,
        )
        assert "al deed\n(nog geen)" in llm.prompts[0]
        assert len(await _rows(db_session, sessie_id)) == 2


class TestEenLangAntwoord:
    def test_an_ordinary_answer_is_one_part(self):
        assert answer_parts(ANTWOORD["tekst"]) == [ANTWOORD["tekst"]]

    def test_an_answer_without_the_words_is_no_part(self):
        assert answer_parts(TURNS[31]["tekst"]) == []

    def _lang(self) -> str:
        vulling = "Het budget is dit jaar gelijk gebleven aan dat van vorig jaar. "
        blok = vulling * (service_mod.MAX_ANTWOORD_DEEL // len(vulling) - 3)
        return f"{T_BRIEF} {blok}{blok}{T_UITZOEKEN}"

    def test_a_long_one_is_cut_and_only_parts_with_the_words_are_asked_about(self):
        delen = answer_parts(self._lang())
        assert len(delen) == 2
        assert all(len(deel) <= service_mod.MAX_ANTWOORD_DEEL for deel in delen)
        assert T_BRIEF in delen[0]
        assert T_UITZOEKEN in delen[1]

    def test_no_more_parts_than_the_limit(self):
        zin = "Ik zal de Kamer daarover vóór de zomer informeren. "
        delen = service_mod.MAX_ANTWOORD_DELEN + 2
        tekst = zin * (service_mod.MAX_ANTWOORD_DEEL * delen // len(zin))
        assert len(answer_parts(tekst)) == service_mod.MAX_ANTWOORD_DELEN

    T_OPNIEUW = "Ik stuur die brief over de bezetting dus vóór de begroting."

    async def _call(self, db_session, sessie_id, mm, post_id, tekst, llm, gelezen=0):
        return await DebatVraagService(db_session, mm, llm).beoordeel_beurt(
            _beurt(
                sessie_id, {**ANTWOORD, "tekst": tekst}, post_id, delen_gelezen=gelezen
            ),
            CONTEXT,
        )

    async def test_one_call_reads_one_part_and_stores_it(self, db_session):
        tekst = self._lang()
        sessie_id, mm = await _sessie(db_session), FakeMattermost()
        post_id = mm.turn()
        llm = FakeLLM(
            toegezegd(toezegging(T_BRIEF, samenvatting="Stuurt de brief.")),
            toegezegd(toezegging(T_UITZOEKEN)),
        )

        first = await self._call(db_session, sessie_id, mm, post_id, tekst, llm)

        assert (first.uitkomst, first.meer, first.delen_gelezen) == (
            UITKOMST_GEMARKEERD,
            True,
            1,
        )
        assert len(llm.prompts) == 1
        # The start of a long answer is read: the prompt keeps only the end
        # of a text that is too long for it.
        assert T_BRIEF in llm.prompts[0]
        assert T_UITZOEKEN not in llm.prompts[0]
        # Stored and in the channel before the next part is asked about.
        assert [r.citaat for r in await _rows(db_session, sessie_id)] == [T_BRIEF]
        assert len(mm.replies) == 1

        second = await self._call(
            db_session, sessie_id, mm, post_id, tekst, llm, first.delen_gelezen
        )

        assert (second.meer, second.delen_gelezen, second.toezeggingen) == (False, 2, 1)
        assert len(llm.prompts) == 2
        assert T_BRIEF not in llm.prompts[1].split("<spreekbeurt>")[1]
        # What the first part promised is on the list the second part gets.
        assert "al deed\n1. Stuurt de brief." in llm.prompts[1]
        assert [r.citaat for r in await _rows(db_session, sessie_id)] == [
            T_BRIEF,
            T_UITZOEKEN,
        ]
        assert splits(mm.messages[post_id])[1] == "🤝 2 toezeggingen · open"

    async def test_an_answer_that_was_read_to_the_end_is_not_asked_about_again(
        self, db_session
    ):
        tekst = self._lang()
        sessie_id, mm = await _sessie(db_session), FakeMattermost()
        llm = FakeLLM(toegezegd(toezegging(T_BRIEF)))
        done = await self._call(db_session, sessie_id, mm, mm.turn(), tekst, llm, 2)
        assert (done.uitkomst, done.meer, done.delen_gelezen) == (
            UITKOMST_AL_BEOORDEELD,
            False,
            2,
        )
        assert llm.prompts == []

    async def test_a_part_that_fails_keeps_the_parts_before_it(self, db_session):
        tekst = self._lang()
        sessie_id, mm = await _sessie(db_session), FakeMattermost()
        post_id = mm.turn()
        llm = FakeLLM(
            toegezegd(toezegging(T_BRIEF)),
            RuntimeError("weg"),
            toegezegd(toezegging(T_UITZOEKEN)),
        )
        first = await self._call(db_session, sessie_id, mm, post_id, tekst, llm)

        failed = await self._call(
            db_session, sessie_id, mm, post_id, tekst, llm, first.delen_gelezen
        )

        assert failed.uitkomst == UITKOMST_LLM_ONBEREIKBAAR
        assert failed.opnieuw_proberen
        # Still at the part that failed, not back at the first.
        assert (failed.delen_gelezen, failed.meer) == (1, True)
        assert [r.citaat for r in await _rows(db_session, sessie_id)] == [T_BRIEF]

        again = await self._call(
            db_session, sessie_id, mm, post_id, tekst, llm, failed.delen_gelezen
        )
        assert (again.delen_gelezen, again.meer) == (2, False)
        assert len(llm.prompts) == 3
        # The first part was asked about once.
        assert sum(T_BRIEF in p.split("<spreekbeurt>")[1] for p in llm.prompts) == 1
        assert len(await _rows(db_session, sessie_id)) == 2

    async def test_an_unreadable_part_counts_as_read_and_the_rest_goes_on(
        self, db_session
    ):
        tekst = self._lang()
        sessie_id, mm = await _sessie(db_session), FakeMattermost()
        post_id = mm.turn()
        llm = FakeLLM("geen json", "ook niet", toegezegd(toezegging(T_UITZOEKEN)))

        first = await self._call(db_session, sessie_id, mm, post_id, tekst, llm)
        assert (first.uitkomst, first.delen_gelezen, first.meer) == (
            UITKOMST_LLM_ONBRUIKBAAR,
            1,
            True,
        )
        assert not first.opnieuw_proberen

        second = await self._call(db_session, sessie_id, mm, post_id, tekst, llm, 1)
        assert (second.toezeggingen, second.meer) == (1, False)
        assert [r.citaat for r in await _rows(db_session, sessie_id)] == [T_UITZOEKEN]

    async def test_a_part_without_a_toezegging_still_counts_as_read(self, db_session):
        tekst = self._lang()
        sessie_id, mm = await _sessie(db_session), FakeMattermost()
        first = await self._call(
            db_session, sessie_id, mm, mm.turn(), tekst, FakeLLM(toegezegd())
        )
        assert (first.uitkomst, first.delen_gelezen, first.meer) == (
            UITKOMST_GEEN_TOEZEGGING,
            1,
            True,
        )

    @pytest.mark.parametrize(
        "opnieuw",
        [
            T_BRIEF,
            # The model cut the same sentence shorter the second time.
            "de Kamer krijgt die brief vóór de begrotingsbehandeling.",
        ],
    )
    async def test_a_part_that_is_handed_in_twice_is_stored_once(
        self, db_session, opnieuw
    ):
        """After a restart between storing a part and noting that it was read."""
        tekst = self._lang()
        sessie_id, mm = await _sessie(db_session), FakeMattermost()
        post_id = mm.turn()
        llm = FakeLLM(
            toegezegd(toezegging(T_BRIEF)),
            toegezegd(toezegging(opnieuw)),
        )
        await self._call(db_session, sessie_id, mm, post_id, tekst, llm)
        again = await self._call(db_session, sessie_id, mm, post_id, tekst, llm)

        assert len(llm.prompts) == 2
        assert (again.delen_gelezen, again.meer) == (1, True)
        assert [r.citaat for r in await _rows(db_session, sessie_id)] == [T_BRIEF]
        assert len(mm.replies) == 1

    async def test_one_said_again_in_a_later_part_is_a_herhaling_on_the_first(
        self, db_session
    ):
        tekst = f"{self._lang()} {self.T_OPNIEUW}"
        sessie_id, mm = await _sessie(db_session), FakeMattermost()
        post_id = mm.turn()
        llm = FakeLLM(
            toegezegd(
                toezegging(T_BRIEF, samenvatting="Stuurt een brief over de bezetting.")
            ),
            toegezegd(toezegging(self.T_OPNIEUW, hoort_bij=1)),
            toegezegd(toezegging(self.T_OPNIEUW, hoort_bij=1)),
        )
        await self._call(db_session, sessie_id, mm, post_id, tekst, llm)
        second = await self._call(db_session, sessie_id, mm, post_id, tekst, llm, 1)

        assert (second.toezeggingen, second.herhaald) == (0, (1,))
        assert [r.citaat for r in await _rows(db_session, sessie_id)] == [T_BRIEF]
        assert await _vermeldingen(db_session, sessie_id) == [
            (VERMELDING_HERHALING, 1, self.T_OPNIEUW, MINISTER)
        ]
        # And that part handed in once more writes no second vermelding.
        await self._call(db_session, sessie_id, mm, post_id, tekst, llm, 1)
        assert len(await _vermeldingen(db_session, sessie_id)) == 1

    async def test_the_link_of_a_part_is_written_once(self, db_session):
        tekst = self._lang()
        sessie_id, mm = await _sessie(db_session), FakeMattermost()
        vraag_citaat = "Kan de minister de bezetting per provincie in beeld brengen?"
        await _judge(
            db_session,
            {
                **VRAAGT,
                "tekst": f"Voorzitter, dank u wel voor het woord. {vraag_citaat}",
            },
            antwoord(vraag(vraag_citaat, samenvatting="Bezetting per provincie?")),
            sessie_id=sessie_id,
            mm=mm,
        )
        post_id = mm.turn()
        beloofd = toegezegd(
            toezegging(
                T_BRIEF, samenvatting="Stuurt de bezetting per provincie.", bij_vraag=1
            )
        )
        llm = FakeLLM(beloofd, beloofd)
        await self._call(db_session, sessie_id, mm, post_id, tekst, llm)
        await self._call(db_session, sessie_id, mm, post_id, tekst, llm)
        assert await _vermeldingen(db_session, sessie_id) == [
            (VERMELDING_ANTWOORD, 1, T_BRIEF, MINISTER)
        ]


# --- reactions ---------------------------------------------------------


class TestEenReactieOpEenToezegging:
    @pytest.mark.parametrize(
        ("emoji", "status", "begin", "blok"),
        [
            (
                REACTIE_BEANTWOORD,
                STATUS_BEANTWOORD,
                "✅ **Stuurt een brief.**\nToezegging 1 · nagekomen · ",
                "🤝 1 toezegging · nagekomen",
            ),
            (
                REACTIE_OPGEPAKT,
                STATUS_TOEGEWEZEN,
                "👀 **Stuurt een brief.**\nToezegging 1 · wordt opgepakt door"
                " persoon.a · ",
                "🤝 1 toezegging · wordt opgepakt",
            ),
            (
                REACTIE_VERVALT,
                STATUS_VERVALT,
                "🚫 **Stuurt een brief.**\nToezegging 1 · hoeft niet · ",
                "🤝 1 toezegging · hoeft niet",
            ),
            (
                REACTIE_GEEN_VRAAG,
                STATUS_VERWORPEN,
                "❌ ~~Toezegging 1 · Stuurt een brief.~~ · geen toezegging",
                "",
            ),
        ],
    )
    async def test_it_is_said_in_the_words_of_a_toezegging(
        self, db_session, emoji, status, begin, blok
    ):
        h = status_helpers
        mm = h.FakeMattermost()
        mm.usernames[h.PERSOON_A] = "persoon.a"
        sessie_id = await h._sessie(db_session)
        values = {
            "gericht_aan": "Kamerlid A (X)",
            "samenvatting": "Stuurt een brief.",
            "citaat": T_BRIEF,
            "termijn": "vóór de begroting",
            "bij_volgnummer": 4,
        }
        open_tekst = format_thread(
            SOORT_TOEZEGGING,
            volgnummer=1,
            stuk=None,
            moment=h.MOMENT,
            moment_url=None,
            **values,
        )
        markering = await h._markering(
            db_session,
            mm,
            sessie_id,
            soort=SOORT_TOEZEGGING,
            spreker=MINISTER,
            fractie=None,
            thread_post_id=mm.post("reply", open_tekst),
            **values,
        )

        await h._reageer(db_session, mm, markering.thread_post_id, h.PERSOON_A, emoji)
        await h._ronde(db_session, mm)

        row = await h._lees(db_session, markering.id)
        assert row.status == status
        tekst = mm.messages[row.thread_post_id]
        assert tekst.startswith(begin)
        if status != STATUS_VERWORPEN:
            # What the reply said about when and which question, it still says.
            assert "· aan Kamerlid A (X) · vóór de begroting · bij vraag 4 · " in tekst
        assert splits(mm.messages[row.beurt_post_id])[1] == blok

        # Taking the reaction away brings the open reply back, whole.
        await h._haal_weg(db_session, mm, markering.thread_post_id, h.PERSOON_A, emoji)
        await h._ronde(db_session, mm)
        assert mm.messages[row.thread_post_id] == open_tekst
        assert splits(mm.messages[row.beurt_post_id])[1] == "🤝 1 toezegging · open"


# --- the worker --------------------------------------------------------


@pytest.mark.asyncio
class TestDeWerker:
    """An answer of the bewindspersoon goes through the same round as any turn."""

    VRAAG = "Kan de minister toezeggen dat de Kamer dat overzicht krijgt?"
    ANTWOORD = "Ja, dat zeg ik toe. U krijgt dat overzicht voor de zomer."

    async def _debat(self, db_session, mm, *, voorzitter: bool = False):
        w = worker_helpers
        s = await w._running(db_session)
        a = await w._row(
            db_session, s, "speaker", 60, "a", tekst=f"{w.OPENING} {w.Q_WANNEER}"
        )
        m1 = await w._row(
            db_session,
            s,
            "speaker",
            120,
            "m",
            tekst="Dank, voorzitter. Het budget is gelijk gebleven.",
        )
        b = await w._row(db_session, s, "interrupter", 180, "b", tekst=self.VRAAG)
        rows = [a, m1, b]
        if voorzitter:
            rows.append(
                await w._row(db_session, s, "chairman", 200, tekst="Kort graag.")
            )
        m2 = await w._row(db_session, s, "speaker", 240, "m", tekst=self.ANTWOORD)
        rows.append(m2)
        await w._row(db_session, s, "debate_end", 300)
        w._in_channel(mm, *(row for row in rows if row.kop))
        return s, a, m1, b, m2

    @pytest.mark.parametrize("voorzitter", [False, True])
    async def test_an_answer_is_read_for_toezeggingen(
        self, db_session, monkeypatch, handed, voorzitter
    ):
        w = worker_helpers
        w.Outside(monkeypatch)
        mm = w.Chat()
        llm = FakeLLM(
            antwoord(vraag(w.Q_WANNEER)),
            antwoord(vraag(self.VRAAG)),
            toegezegd(toezegging(self.ANTWOORD, termijn="voor de zomer", bij_vraag=2)),
        )
        s, a, m1, b, m2 = await self._debat(db_session, mm, voorzitter=voorzitter)

        result = await w._tick(db_session, mm, llm)

        assert (result.beoordeeld, result.vragen, result.toezeggingen) == (4, 2, 1)
        assert result.fouten == 0
        assert "2 vragen, 0 moties, 1 toezeggingen, 0 fouten" in result.summary()
        by_row = {beurt.spreekbeurt_id: beurt for beurt, _ in handed}
        # The first answer follows a term, not an interruption.
        assert by_row[m1.id].is_bewindspersoon is True
        assert by_row[m1.id].voorafgaand is None
        # The second follows an interruption of a member, with or without
        # the chairman's words in between.
        assert by_row[m2.id].voorafgaand == "Kamerlid B (Y)"
        assert by_row[m2.id].voorafgaand_tekst == self.VRAAG
        # A member gets none of that.
        assert by_row[b.id].voorafgaand is None
        # Three calls: the answer without a commitment cost none.
        assert len(llm.prompts) == 3
        assert _is_toezeggingen_prompt(llm.prompts[2])

        rows = await _rows(db_session, s.id)
        assert [r.soort for r in rows] == [SOORT_VRAAG, SOORT_VRAAG, SOORT_TOEZEGGING]
        toezegging_row = rows[2]
        assert toezegging_row.spreekbeurt_id == m2.id
        assert toezegging_row.gericht_aan == "Kamerlid B (Y)"
        assert (toezegging_row.termijn, toezegging_row.bij_volgnummer) == (
            "voor de zomer",
            2,
        )
        # The reply hangs under the message of the answer.
        assert mm.threads[-1][0] == m2.post_id
        assert mm.threads[-1][1].startswith("🤝 **")
        for row in (m1, m2):
            assert await w._at(db_session, row) is not None

    async def test_a_member_who_carries_on_after_an_interruption_gets_none_of_it(
        self, db_session, monkeypatch, handed
    ):
        w = worker_helpers
        w.Outside(monkeypatch)
        mm = w.Chat()
        s = await w._running(db_session)
        b = await w._row(
            db_session, s, "interrupter", 60, "b", tekst=f"{w.OPENING} {w.Q_BUDGET}"
        )
        a = await w._row(
            db_session, s, "speaker", 120, "a", tekst=f"{w.OPENING} {w.Q_WANNEER}"
        )
        await w._row(db_session, s, "debate_end", 180)
        w._in_channel(mm, b, a)

        await w._tick(db_session, mm, FakeLLM())

        by_row = {beurt.spreekbeurt_id: beurt for beurt, _ in handed}
        assert (by_row[a.id].voorafgaand, by_row[a.id].voorafgaand_tekst) == (None, "")

    async def test_an_interruption_by_someone_without_a_party_names_nobody(
        self, db_session, monkeypatch, handed
    ):
        """Only a member asks. Whoever else spoke before is not who the
        toezegging is made to."""
        w = worker_helpers
        w.Outside(monkeypatch)
        mm = w.Chat()
        llm = FakeLLM(toegezegd(toezegging(self.ANTWOORD)))
        s = await w._running(db_session)
        ander = await w._row(
            db_session, s, "interrupter", 60, "m", tekst="Het budget is gelijk."
        )
        m = await w._row(db_session, s, "speaker", 120, "m", tekst=self.ANTWOORD)
        await w._row(db_session, s, "debate_end", 180)
        w._in_channel(mm, ander, m)

        await w._tick(db_session, mm, llm)

        by_row = {beurt.spreekbeurt_id: beurt for beurt, _ in handed}
        assert (by_row[m.id].voorafgaand, by_row[m.id].voorafgaand_tekst) == (None, "")
        (row,) = await _rows(db_session, s.id)
        assert (row.soort, row.gericht_aan) == (SOORT_TOEZEGGING, "")

    async def test_an_answer_that_was_read_is_not_read_again(
        self, db_session, monkeypatch, handed
    ):
        w = worker_helpers
        w.Outside(monkeypatch)
        mm = w.Chat()
        llm = FakeLLM(antwoord(), antwoord(), toegezegd())
        await self._debat(db_session, mm)

        await w._tick(db_session, mm, llm)
        again = await w._tick(db_session, mm, llm, 715)

        assert len(handed) == 4
        assert again.beoordeeld == 0
        assert len(llm.prompts) == 3

    async def test_a_model_that_is_away_counts_an_attempt_and_pauses_the_debate(
        self, db_session, monkeypatch, handed
    ):
        w = worker_helpers
        w.Outside(monkeypatch)
        monkeypatch.setattr(db_session, "rollback", w._nothing)
        mm = w.Chat()
        llm = FakeLLM(antwoord(), antwoord(), RuntimeError("weg"))
        s, a, m1, b, m2 = await self._debat(db_session, mm)

        result = await w._tick(db_session, mm, llm)

        assert (result.beoordeeld, result.fouten) == (3, 1)
        assert await w._at(db_session, m2) is None
        attempts = await db_session.scalar(
            select(DebatSpreekbeurt.beoordeel_pogingen).where(
                DebatSpreekbeurt.id == m2.id
            )
        )
        assert attempts == 1
        # Left alone for a while: the next round does not ask again.
        paused = await w._tick(db_session, mm, llm, 705)
        assert paused.beoordeeld == 0
        assert len(llm.prompts) == 3
        # After the pause the same turn is read, once.
        llm.answers.append(toegezegd(toezegging(self.ANTWOORD)))
        later = await w._tick(
            db_session, mm, llm, 700 + worker_mod.PAUSE_FIRST.total_seconds() + 1
        )
        assert (later.beoordeeld, later.toezeggingen) == (1, 1)

    async def test_an_answer_that_is_still_going_on_waits(
        self, db_session, monkeypatch, handed
    ):
        w = worker_helpers
        w.Outside(monkeypatch)
        mm = w.Chat()
        s = await w._running(db_session)
        m = await w._row(db_session, s, "speaker", 60, "m", tekst=self.ANTWOORD)
        w._in_channel(mm, m)

        result = await w._tick(db_session, mm, FakeLLM(toegezegd()))

        assert result.beoordeeld == 0
        assert handed == []

    async def test_someone_the_list_does_not_have_is_not_read(
        self, db_session, monkeypatch, handed
    ):
        w = worker_helpers
        w.Outside(monkeypatch)
        mm = w.Chat()
        llm = FakeLLM(toegezegd(toezegging(self.ANTWOORD)))
        s = await w._running(db_session)
        gast = await w._row(db_session, s, "speaker", 60, "gast", tekst=self.ANTWOORD)
        await w._row(db_session, s, "debate_end", 120)
        w._in_channel(mm, gast)

        result = await w._tick(db_session, mm, llm)

        assert handed == []
        assert llm.prompts == []
        assert result.toezeggingen == 0
        assert await w._at(db_session, gast) is not None
        assert await _rows(db_session, s.id) == []


class PerKind(FakeLLM):
    """A model with answers of its own for an answer of the bewindspersoon.

    `toezeggingen` are handed out in order to the prompts for toezeggingen:
    a reply, an error to raise, or `SLOW` for a call that does not come
    back in time. Every other prompt gets "no question" at once.
    """

    SLOW = "slow"

    def __init__(self, *toezeggingen) -> None:
        super().__init__()
        self.toezeggingen = list(toezeggingen)
        self.asked: list[str] = []

    async def _complete(self, prompt: str, max_tokens: int = 1024) -> str:
        self.prompts.append(prompt)
        if not _is_toezeggingen_prompt(prompt):
            return antwoord()
        self.asked.append(prompt)
        answer = self.toezeggingen.pop(0) if self.toezeggingen else toegezegd()
        if answer == self.SLOW:
            await asyncio.sleep(30)
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.mark.asyncio
class TestEenTraagOfLangAntwoord:
    """One answer of the bewindspersoon must not cost the members their turn."""

    KORT = "Ja, dat zeg ik toe. U krijgt dat overzicht voor de zomer."

    def _lang(self) -> str:
        vulling = "Het budget is dit jaar gelijk gebleven aan dat van vorig jaar. "
        blok = vulling * (service_mod.MAX_ANTWOORD_DEEL // len(vulling) - 3)
        return f"{T_BRIEF} {blok}{blok}{T_UITZOEKEN}"

    async def _debat(self, db_session, mm, antwoord_tekst: str, *, leden: int = 2):
        """An answer of the minister, and after it turns of members."""
        w = worker_helpers
        s = await w._running(db_session)
        m = await w._row(db_session, s, "speaker", 60, "m", tekst=antwoord_tekst)
        rows = [m]
        for i in range(leden):
            rows.append(
                await w._row(
                    db_session,
                    s,
                    "speaker",
                    120 + 10 * i,
                    "ab"[i % 2],
                    tekst=f"{w.OPENING} {w.Q_WANNEER}",
                )
            )
        await w._row(db_session, s, "debate_end", 300)
        w._in_channel(mm, *rows)
        return s, m, rows[1:]

    async def _parts(self, db_session, row) -> int:
        return await db_session.scalar(
            select(DebatSpreekbeurt.antwoord_delen_gelezen).where(
                DebatSpreekbeurt.id == row.id
            )
        )

    async def _attempts(self, db_session, row) -> int:
        return await db_session.scalar(
            select(DebatSpreekbeurt.beoordeel_pogingen).where(
                DebatSpreekbeurt.id == row.id
            )
        )

    async def test_the_turns_of_members_are_read_before_an_answer(
        self, db_session, monkeypatch, handed
    ):
        w = worker_helpers
        w.Outside(monkeypatch)
        mm = w.Chat()
        s, m, leden = await self._debat(db_session, mm, self.KORT)

        await w._tick(db_session, mm, PerKind())

        # Spoken first, read last.
        assert [beurt.spreekbeurt_id for beurt, _ in handed] == [
            leden[0].id,
            leden[1].id,
            m.id,
        ]

    @pytest.mark.parametrize("wat", ["weg", "traag"])
    async def test_an_answer_that_fails_or_hangs_does_not_hold_up_the_members(
        self, db_session, monkeypatch, handed, wat
    ):
        w = worker_helpers
        w.Outside(monkeypatch)
        monkeypatch.setattr(db_session, "rollback", w._nothing)
        monkeypatch.setattr(worker_mod, "JUDGE_TIMEOUT", 0.2)
        mm = w.Chat()
        llm = PerKind(RuntimeError("weg") if wat == "weg" else PerKind.SLOW)
        s, m, leden = await self._debat(db_session, mm, self.KORT)

        result = await w._tick(db_session, mm, llm)

        # Both members were read in the same round, and the debate is not
        # left alone for it.
        assert (result.beoordeeld, result.fouten) == (2, 1)
        for lid in leden:
            assert await w._at(db_session, lid) is not None
        now = (w.START + timedelta(seconds=700)).astimezone(UTC)
        assert not worker_mod._pause.waiting(s.id, now)
        assert await w._at(db_session, m) is None
        assert await self._attempts(db_session, m) == 1

        # A member who speaks next is read in the very next round, while
        # the answer itself waits its turn.
        later = await w._row(
            db_session, s, "speaker", 200, "c", tekst=f"{w.OPENING} {w.Q_BUDGET}"
        )
        w._in_channel(mm, later)
        again = await w._tick(db_session, mm, llm, 705)
        assert again.beoordeeld == 1
        assert await w._at(db_session, later) is not None
        assert len(llm.asked) == 1

        # After its own pause the answer is tried again, and read.
        llm.toezeggingen.append(toegezegd(toezegging(self.KORT)))
        after = 700 + worker_mod.PAUSE_FIRST.total_seconds() + 1
        done = await w._tick(db_session, mm, llm, after)
        assert (done.beoordeeld, done.toezeggingen) == (1, 1)
        assert await w._at(db_session, m) is not None

    async def test_a_member_whose_turn_fails_still_pauses_the_debate(
        self, db_session, monkeypatch, handed
    ):
        """That is a model that is away, and every turn would find the same."""
        w = worker_helpers
        w.Outside(monkeypatch)
        monkeypatch.setattr(db_session, "rollback", w._nothing)
        mm = w.Chat()
        s, m, leden = await self._debat(db_session, mm, self.KORT)

        result = await w._tick(db_session, mm, FakeLLM(RuntimeError("weg")))

        assert (result.beoordeeld, result.fouten) == (0, 1)
        now = (w.START + timedelta(seconds=700)).astimezone(UTC)
        assert worker_mod._pause.waiting(s.id, now)
        # The answer was not even tried.
        assert [beurt.spreekbeurt_id for beurt, _ in handed] == [leden[0].id]

    async def test_a_long_answer_is_read_a_part_per_round_and_kept_in_between(
        self, db_session, monkeypatch, handed
    ):
        w = worker_helpers
        w.Outside(monkeypatch)
        mm = w.Chat()
        llm = PerKind(
            toegezegd(toezegging(T_BRIEF)), toegezegd(toezegging(T_UITZOEKEN))
        )
        s, m, _ = await self._debat(db_session, mm, self._lang(), leden=0)

        first = await w._tick(db_session, mm, llm)

        assert len(llm.asked) == 1
        assert (first.beoordeeld, first.toezeggingen, first.fouten) == (0, 1, 0)
        assert await self._parts(db_session, m) == 1
        assert await w._at(db_session, m) is None
        assert [r.citaat for r in await _rows(db_session, s.id)] == [T_BRIEF]

        second = await w._tick(db_session, mm, llm, 715)

        assert len(llm.asked) == 2
        assert (second.beoordeeld, second.toezeggingen) == (1, 1)
        assert await self._parts(db_session, m) == 2
        assert await w._at(db_session, m) is not None
        assert [r.citaat for r in await _rows(db_session, s.id)] == [
            T_BRIEF,
            T_UITZOEKEN,
        ]
        # And it is done: a third round asks nothing.
        await w._tick(db_session, mm, llm, 730)
        assert len(llm.asked) == 2

    async def test_a_part_that_fails_is_tried_again_and_not_the_parts_before_it(
        self, db_session, monkeypatch, handed
    ):
        w = worker_helpers
        w.Outside(monkeypatch)
        monkeypatch.setattr(db_session, "rollback", w._nothing)
        mm = w.Chat()
        llm = PerKind(
            toegezegd(toezegging(T_BRIEF)),
            RuntimeError("weg"),
            toegezegd(toezegging(T_UITZOEKEN)),
        )
        s, m, _ = await self._debat(db_session, mm, self._lang(), leden=0)

        await w._tick(db_session, mm, llm)
        failed = await w._tick(db_session, mm, llm, 715)

        assert failed.fouten == 1
        assert await self._parts(db_session, m) == 1
        assert [r.citaat for r in await _rows(db_session, s.id)] == [T_BRIEF]

        after = 715 + worker_mod.PAUSE_FIRST.total_seconds() + 1
        await w._tick(db_session, mm, llm, after)

        assert len(llm.asked) == 3
        assert sum(T_BRIEF in p.split("<spreekbeurt>")[1] for p in llm.asked) == 1
        assert await self._parts(db_session, m) == 2
        assert await w._at(db_session, m) is not None
        assert len(await _rows(db_session, s.id)) == 2

    async def test_an_answer_that_is_given_up_on_keeps_what_was_stored(
        self, db_session, monkeypatch, handed
    ):
        w = worker_helpers
        w.Outside(monkeypatch)
        monkeypatch.setattr(db_session, "rollback", w._nothing)
        mm = w.Chat()
        llm = PerKind(toegezegd(toezegging(T_BRIEF)), RuntimeError("weg"))
        s, m, _ = await self._debat(db_session, mm, self._lang(), leden=0)
        await w._tick(db_session, mm, llm)
        m.beoordeel_pogingen = worker_mod.MAX_ATTEMPTS - 1
        await db_session.flush()

        await w._tick(db_session, mm, llm, 715)

        assert await w._at(db_session, m) is not None
        assert [r.citaat for r in await _rows(db_session, s.id)] == [T_BRIEF]

    async def test_no_more_parts_of_answers_in_a_round_than_the_limit(
        self, db_session, monkeypatch, handed
    ):
        w = worker_helpers
        w.Outside(monkeypatch)
        mm = w.Chat()
        llm = PerKind()
        s = await w._running(db_session)
        answers = [
            await w._row(db_session, s, "speaker", 60 + 10 * i, "m", tekst=self.KORT)
            for i in range(worker_mod.MAX_ANSWER_PARTS_PER_ROUND + 2)
        ]
        lid = await w._row(
            db_session, s, "speaker", 200, "a", tekst=f"{w.OPENING} {w.Q_WANNEER}"
        )
        await w._row(db_session, s, "debate_end", 300)
        w._in_channel(mm, *answers, lid)

        await w._tick(db_session, mm, llm)

        assert len(llm.asked) == worker_mod.MAX_ANSWER_PARTS_PER_ROUND
        assert await w._at(db_session, lid) is not None
        # The rest follows in the rounds after, oldest first.
        await w._tick(db_session, mm, llm, 715)
        assert len(llm.asked) == len(answers)

    async def test_answers_set_aside_do_not_use_up_the_round_of_the_members(
        self, db_session, monkeypatch, handed
    ):
        w = worker_helpers
        w.Outside(monkeypatch)
        monkeypatch.setattr(worker_mod, "MAX_TURNS", 2)
        mm = w.Chat()
        s = await w._running(db_session)
        answers = [
            await w._row(db_session, s, "speaker", 60 + 10 * i, "m", tekst=self.KORT)
            for i in range(3)
        ]
        leden = [
            await w._row(
                db_session,
                s,
                "speaker",
                150 + 10 * i,
                "abc"[i],
                tekst=f"{w.OPENING} {w.Q_WANNEER}",
            )
            for i in range(3)
        ]
        await w._row(db_session, s, "debate_end", 300)
        w._in_channel(mm, *answers, *leden)

        await w._tick(db_session, mm, PerKind())

        read = [await w._at(db_session, lid) is not None for lid in leden]
        assert read == [True, True, False]


@pytest.fixture
def handed(monkeypatch):
    """Every turn that was handed to the marking, with its context."""
    seen: list = []
    original = DebatVraagService.beoordeel_beurt

    async def record(self, beurt, context):
        seen.append((beurt, context))
        return await original(self, beurt, context)

    monkeypatch.setattr(DebatVraagService, "beoordeel_beurt", record)
    return seen


@pytest.fixture(autouse=True)
def _no_pause_left_over():
    """The pause after a failure lives in the process; a test starts clean."""
    worker_mod._pause.reset()
    worker_mod._answer_pause.reset()
    yield
    worker_mod._pause.reset()
    worker_mod._answer_pause.reset()
