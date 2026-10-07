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
    AT_START,
    MAX_PASSAGE,
    SAID_BEFORE,
    Interruption,
    Link,
    asks_something,
    commitment_passages,
    deadline_is_said,
    has_commitment_form,
    link_to_question,
    may_hold_commitment,
    names_someone_else,
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
    UITKOMST_AL_BEOORDEELD,
    UITKOMST_GEEN_TOEZEGGING,
    UITKOMST_GEMARKEERD,
    UITKOMST_LLM_ONBEREIKBAAR,
    UITKOMST_LLM_ONBRUIKBAAR,
    UITKOMST_OVERGESLAGEN,
    Beurt,
    DebatContext,
    DebatVraagService,
    answer_window,
    format_thread,
    format_toezegging_thread,
    lees_toezeggingen,
    next_window,
    rol_van,
    skip_window,
)
from bouwmeester.services.debat_vraag_status_service import verworpen_markeringen
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
        assert has_commitment_form("Ik neem dat mee naar het overleg.")
        assert not has_commitment_form("Ik neem dat aan. Mee naar het overleg hoeft.")

    def test_a_refusal_behind_maar_is_not_of_the_wording_in_front_of_it(self):
        assert has_commitment_form(
            "ik stuur de kamer een brief maar meer kan ik niet doen"
        )

    def test_the_dots_of_a_line_that_runs_on_do_not_end_a_clause(self):
        assert not has_commitment_form("Ik stuur de Kamer... daarover geen brief.")

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
            "Stuurt de Kamer een overzicht van de bezetting van de beugels.",
            "Kan de minister de bezetting van de beugels in beeld brengen?",
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

    def test_who_every_debate_is_about_does_not_make_a_subject(self):
        assert not shares_a_subject(
            "Informeert de Kamer over de gesprekken met gemeenten en provincies",
            "Wil de minister de bezuiniging op gemeenten en provincies terugdraaien",
        )
        assert not shares_a_subject(
            "Het kabinet stuurt de Kamer een brief over het beleid van de regering.",
            "Wat vindt het kabinet van het beleid van de regering in Nederland?",
        )
        # With what it is about next to it, it does.
        assert shares_a_subject(
            "Informeert de Kamer over de bezuiniging op het gemeentefonds.",
            "Wil de minister de bezuiniging op het gemeentefonds terugdraaien?",
        )

    def test_coming_back_to_it_is_no_subject(self):
        """Every other toezegging comes back to something."""
        assert not shares_a_subject(
            "De minister zegt toe op de kelders terug te komen; hij komt terug.",
            "Zal terugkomen op de daken. Ik kom op de daken terug, terugkomend dus.",
        )
        # With what it comes back to, it is one.
        assert shares_a_subject(
            "De minister zegt toe op de verlichting in de kelders terug te komen.",
            "Zal terugkomen op de verlichting. Ik kom op de kelders terug.",
        )

    def test_one_word_is_not_enough(self):
        assert not shares_a_subject(
            "Neemt de uitvoering mee in de rapportage over handhaving.",
            "Wanneer komt de evaluatie van de handhaving?",
        )


class TestBijWelkeVraagRegel:
    """`link_to_question`: where a toezegging stands first, the model's
    number as confirmation."""

    ONDERWERP = SYN["debat"]["onderwerp"]
    A, B = "Kamerlid A (X)", "Kamerlid B (Y)"
    # Three questions of the first term: two of A, one of B.
    VRAGEN = {
        3: "Verlichting in de kelders? Is de verlichting in de kelders op orde?",
        4: "Toezicht in de nacht? Komt er toezicht in de nacht bij de kelders?",
        5: "Verlichting bij de ingang? Wie betaalt de verlichting in de kelders"
        " en bij de ingang?",
    }
    VRAGERS = {3: A, 4: A, 5: B}
    INTERRUPTIE = (
        "Kan de minister toezeggen dat hij de verlichting in de kelders nakijkt?"
    )
    BELOFTE = "Dat zeg ik toe, ik laat de verlichting nakijken."
    KORT = "Laat de verlichting in de kelders nakijken."

    def _link(self, **extra) -> Link:
        values = {
            "quote": self.BELOFTE,
            "said_before": "",
            "summary": self.KORT,
            "named": None,
            "questions": self.VRAGEN,
            "askers": self.VRAGERS,
            "onderwerp": self.ONDERWERP,
            "interruption": Interruption(self.A, self.INTERRUPTIE, (3,)),
            "at_start": True,
        }
        values.update(extra)
        return link_to_question(**values)

    def test_the_question_of_the_interruption_before_it(self):
        """Marked in the interruption, asked there or asked again: that is
        what the answer is to, also when the model names no number."""
        assert self._link() == Link(3, self.A)

    def test_another_question_of_the_same_member_does_not_win(self):
        """The model points at another question of the member's first
        term. Where the toezegging stands says which it is."""
        assert self._link(named=4) == Link(3, self.A)

    def test_the_question_of_another_member_does_not_win(self):
        assert self._link(named=5) == Link(3, self.A)
        # Nor when nothing was marked in the interruption: the answer is to
        # who interrupted, and the question of another member is not theirs.
        nothing = Interruption(self.A, self.INTERRUPTIE)
        assert self._link(named=5, interruption=nothing) == Link(None, self.A)

    def test_a_marked_question_about_something_else_is_no_link(self):
        """An interruption can hold two questions and be filed under one;
        the toezegging is to the other."""
        andere = Interruption(self.A, self.INTERRUPTIE, (4,))
        vragen = {**self.VRAGEN, 4: "Kosten van de camera's? Wat kosten de camera's?"}
        assert self._link(interruption=andere, questions=vragen) == Link(None, self.A)
        # Then the model's number counts, for a question of the same member
        # that the interruption and the toezegging are about.
        assert self._link(interruption=andere, questions=vragen, named=3) == Link(
            3, self.A
        )

    def test_of_two_marked_questions_the_model_s_number_chooses(self):
        both = Interruption(self.A, self.INTERRUPTIE, (3, 4))
        vragen = {**self.VRAGEN, 4: "Verlichting in de nacht? Brandt de verlichting?"}
        assert self._link(interruption=both, questions=vragen) == Link(None, self.A)
        assert self._link(interruption=both, questions=vragen, named=4) == Link(
            4, self.A
        )
        # A third question of the member is not one of the two.
        derde = {**vragen, 6: self.VRAGEN[3]}
        vragers = {**self.VRAGERS, 6: self.A}
        assert self._link(
            interruption=both, questions=derde, askers=vragers, named=6
        ) == Link(None, self.A)

    def test_a_question_marked_in_it_makes_it_an_interruption_that_asks(self):
        """Whatever the form of what the member said around it."""
        remark = Interruption(self.A, "De kelders zijn donker.", (3,))
        assert self._link(interruption=remark) == Link(3, self.A)

    def test_the_summary_alone_does_not_tie_it_to_the_marked_question(self):
        """A bare yes after an interruption that names nothing: the only
        word shared with the question is one the model wrote."""
        kaal = Interruption(self.A, "Kan hij dat toezeggen?", (3,))
        bare = {"quote": "Ja, dat zeg ik toe.", "summary": self.KORT}
        assert self._link(interruption=kaal, **bare) == Link(None, self.A)
        # With a word of the question in what the member said, it is tied.
        assert self._link(**bare) == Link(3, self.A)
        # Unless the model says the toezegging is about something else.
        anders = {**bare, "summary": "Stuurt een brief over de camera's."}
        assert self._link(**anders) == Link(None, self.A)
        # Or in what the bewindspersoon said in front of it.
        assert self._link(
            interruption=kaal, said_before="Over de kelders dan.", **bare
        ) == Link(3, self.A)

    def test_a_question_that_is_not_open_is_no_link(self):
        closed = Interruption(self.A, self.INTERRUPTIE, (9,))
        assert self._link(interruption=closed) == Link(None, self.A)

    def test_without_a_marked_question_the_same_member_s_question_needs_two_words(
        self,
    ):
        nothing = Interruption(self.A, self.INTERRUPTIE)
        assert self._link(interruption=nothing, named=3) == Link(3, self.A)
        # Question 4 shares "kelders" with the interruption and no more.
        assert self._link(interruption=nothing, named=4) == Link(None, self.A)

    def test_what_the_member_asked_says_what_a_bare_yes_is_about(self):
        """ "Dat zeg ik toe" has no word of its own; the interruption has."""
        nothing = Interruption(self.A, self.INTERRUPTIE)
        bare = {"quote": "Ja, dat zeg ik toe.", "summary": "Zegt het toe."}
        assert self._link(interruption=nothing, named=3, **bare) == Link(3, self.A)
        # The words of the interruption do not make any question its answer.
        assert self._link(interruption=nothing, named=4, **bare) == Link(None, self.A)
        # And the summary does not count here: the model writes it with the
        # question it names in front of it.
        geleend = {**bare, "summary": "Zegt toezicht in de nacht toe."}
        assert self._link(interruption=nothing, named=4, **geleend) == Link(
            None, self.A
        )

    def test_an_interruption_that_asks_nothing_is_not_what_the_answer_is_to(self):
        """The words of the bewindspersoon under the name of a member, or
        a remark: nobody is named for it."""
        remark = Interruption(
            self.A, "De stalling in Dorpstede is vorig jaar al opgeknapt."
        )
        assert self._link(interruption=remark) == Link()
        # The model's number then counts as anywhere else in an answer.
        said = "Kamerlid B vroeg naar de verlichting bij de ingang van de stalling."
        assert self._link(
            interruption=remark,
            named=5,
            said_before=said,
            summary="Laat de verlichting bij de ingang nakijken.",
        ) == Link(5, self.B)

    def test_a_quote_that_names_other_members_is_not_to_who_interrupted(self):
        quote = (
            "Ik stuur de Kamer een brief, en die gaat ook over de fietsen van de heer"
            " Voorbeeld en mevrouw Proef mee."
        )
        assert self._link(quote=quote) == Link()
        assert names_someone_else(quote, self.A)
        # Who interrupted, named: still theirs.
        eigen = "Dat zeg ik mevrouw A graag toe."
        assert not names_someone_else(eigen, self.A)
        assert self._link(quote=f"{eigen} Ik laat de verlichting nakijken.") == Link(
            3, self.A
        )
        assert not names_someone_else("Dat zeg ik toe.", self.A)

    def test_further_into_the_answer_it_is_no_longer_to_the_interruption(self):
        assert self._link(at_start=False) == Link()

    def test_in_a_long_answer_the_model_s_number_needs_what_was_said(self):
        said = "Kamerlid A vroeg of de verlichting in de kelders op orde is."
        long_answer = {"interruption": None, "at_start": False}
        assert self._link(**long_answer, named=3, said_before=said) == Link(3, self.A)
        # Two words in the quote itself are as good.
        quote = "Ik laat de verlichting in de kelders nakijken."
        assert self._link(**long_answer, named=3, quote=quote) == Link(3, self.A)
        # One word is a subject, not a question.
        assert self._link(**long_answer, named=3) == Link()
        # And one of the words has to be in the quote itself: a toezegging
        # without a word of its own is not tied to what was said before it.
        bare = "Dat zeg ik toe, daar doen we een evaluatie naar."
        assert (
            self._link(**long_answer, named=3, said_before=said, quote=bare) == Link()
        )
        # No number, no link.
        assert self._link(**long_answer, said_before=said) == Link()
        # A number that is no open question.
        assert self._link(**long_answer, named=9, said_before=said) == Link()

    def test_words_only_the_summary_shares_are_the_model_s(self):
        """The model writes the summary with the questions in front of it.
        What the bewindspersoon said has to point at the question too."""
        long_answer = {"interruption": None, "at_start": False}
        assert (
            self._link(
                **long_answer,
                named=3,
                quote="Dat zeg ik toe, ik kom daar schriftelijk op terug.",
                summary="Komt terug op de verlichting in de kelders.",
            )
            == Link()
        )
        # And the other way round: said, but summarised as something else.
        assert (
            self._link(
                **long_answer,
                named=3,
                quote="Ik laat de verlichting in de kelders nakijken.",
                summary="Stuurt een brief over de camera's.",
            )
            == Link()
        )

    def test_who_asked_is_unknown(self):
        long_answer = {"interruption": None, "at_start": False}
        quote = "Ik laat de verlichting in de kelders nakijken."
        assert self._link(**long_answer, named=3, quote=quote, askers={}) == Link(3, "")

    @pytest.mark.parametrize(
        "tekst",
        [
            "Kan hij dat toezeggen?",
            "Kan hij ook iets zeggen over de fietsen buiten de stalling",
            "maar zou het niet beter zijn om eerst de kelders te tellen",
            "Ik miste een antwoord. Wat doet de minister met de kelders?",
        ],
    )
    def test_an_interruption_that_asks(self, tekst):
        assert asks_something(tekst)

    @pytest.mark.parametrize(
        "tekst",
        [
            "Ja. De stalling in Dorpstede is vorig jaar al opgeknapt.",
            "Een telling per station lijkt mij ook goed. Dat is een mooi begin.",
            "Dank voor dit antwoord.",
            # The verb in front of its subject, and nothing asked.
            "Dan kan het dus niet.",
            "Dat is mooi, dan is het voor de zomer geregeld.",
            "",
        ],
    )
    def test_an_interruption_that_does_not(self, tekst):
        assert not asks_something(tekst)


# --- what the model answered -------------------------------------------


def _t(citaat: str, **extra) -> DebatToezegging:
    return DebatToezegging(**{"citaat": citaat, "samenvatting": "Kort.", **extra})


class TestLeesToezeggingen:
    TEKST = ANTWOORD["tekst"]
    VRAAG = (
        "Overzicht van de bezetting? Kan de minister vóór de begrotingsbehandeling"
        " een overzicht geven van de bezetting van de stallingen?"
    )
    BELOOFD = "Stuurt de Kamer een overzicht van de bezetting van de beugels."
    # What was promised before, in words both toezeggingen of the turn share.
    EERDER = (
        "Krijgt een brief vóór de begrotingsbehandeling; laat het uitzoeken in het"
        " voorjaar."
    )

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
            [_t(T_BRIEF, hoort_bij=4)], self.TEKST, {}, {4: self.EERDER}
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
            {4: self.EERDER},
        )
        assert nieuw == []
        assert [(h.volgnummer, h.citaat) for h in herhaald] == [(4, T_BRIEF)]

    def test_another_promise_the_model_calls_a_repeat_is_new(self):
        """A herhaling leaves nothing in the channel, so it is not taken on
        the model's word alone."""
        nieuw, herhaald, _ = lees_toezeggingen(
            [_t(T_BRIEF, hoort_bij=4)],
            self.TEKST,
            {},
            {4: "Gaat in gesprek met de vervoerders over de camera's."},
        )
        assert herhaald == []
        assert [n.citaat for n in nieuw] == [T_BRIEF]

    def test_a_moment_named_with_a_repeat_goes_along(self):
        _, herhaald, _ = lees_toezeggingen(
            [_t(T_BRIEF, hoort_bij=4, termijn="vóór de begrotingsbehandeling")],
            self.TEKST,
            {},
            {4: self.EERDER},
        )
        assert [h.termijn for h in herhaald] == ["vóór de begrotingsbehandeling"]
        # Not one the quote does not name.
        _, herhaald, _ = lees_toezeggingen(
            [_t(T_BRIEF, hoort_bij=4, termijn="voor de zomer")],
            self.TEKST,
            {},
            {4: self.EERDER},
        )
        assert [h.termijn for h in herhaald] == [None]

    def test_a_number_that_is_no_earlier_toezegging_makes_it_new(self):
        # 7 is a question, not a toezegging of this bewindspersoon.
        nieuw, herhaald, _ = lees_toezeggingen(
            [_t(T_BRIEF, hoort_bij=7)],
            self.TEKST,
            {7: self.VRAAG},
            {4: self.EERDER},
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

    def test_who_asked_the_linked_question_is_who_it_was_promised_to(self):
        nieuw, _, _ = lees_toezeggingen(
            [_t(T_BRIEF, samenvatting=self.BELOOFD, bij_vraag=7)],
            self.TEKST,
            {7: self.VRAAG},
            set(),
            CONTEXT.onderwerp,
            vragenstellers={7: "Kamerlid A (X)"},
        )
        assert (nieuw[0].bij_volgnummer, nieuw[0].gericht_aan) == (7, "Kamerlid A (X)")

    def test_what_the_bewindspersoon_said_before_the_quote_counts(self):
        """The quote itself shares one word with the question; the sentence
        in front of it, where the question is repeated, has the others."""
        citaat = "Ik zal de verlichting laten nakijken en meld de Kamer hoe het staat."
        tekst = (
            "Kamerlid A vroeg naar de verlichting in de kelders van de"
            f" stallingen. {citaat}"
        )
        vraag_tekst = (
            "Verlichting in de kelders? Is de verlichting in de kelders op orde?"
        )
        toezeggingen = [
            _t(citaat, samenvatting="Zoekt de verlichting uit.", bij_vraag=7)
        ]
        nieuw, _, _ = lees_toezeggingen(
            toezeggingen, tekst, {7: vraag_tekst}, set(), CONTEXT.onderwerp
        )
        assert nieuw[0].bij_volgnummer == 7
        # A quote without a word of the question is no answer to it,
        # whatever was said in front of it.
        leeg = "Ik zal dat laten uitzoeken en meld de Kamer hoe het staat."
        nieuw, _, _ = lees_toezeggingen(
            [_t(leeg, samenvatting="Zoekt de verlichting uit.", bij_vraag=7)],
            tekst.replace(citaat, leeg),
            {7: vraag_tekst},
            set(),
            CONTEXT.onderwerp,
        )
        assert nieuw[0].bij_volgnummer is None
        # Further away than what counts as said with it, it does not.
        ver = tekst.replace(citaat, "Dat is een ander onderwerp. " * 20 + citaat)
        assert ver.index(citaat) - ver.index("kelders") > SAID_BEFORE
        nieuw, _, _ = lees_toezeggingen(
            toezeggingen, ver, {7: vraag_tekst}, set(), CONTEXT.onderwerp
        )
        assert nieuw[0].bij_volgnummer is None

    def test_an_answer_to_an_interruption_is_to_who_interrupted(self):
        """Without a question to link it to."""
        nieuw, _, _ = lees_toezeggingen(
            [_t(T_ZOMER)],
            ZEGT_TOE["tekst"],
            {},
            set(),
            interruptie=Interruption("Kamerlid A (X)", "Kan hij dat toezeggen?"),
        )
        assert (nieuw[0].bij_volgnummer, nieuw[0].gericht_aan) == (
            None,
            "Kamerlid A (X)",
        )

    def test_a_long_name_is_cut(self):
        naam = "Kamerlid " + "A" * 200
        nieuw, _, _ = lees_toezeggingen(
            [_t(T_ZOMER)],
            ZEGT_TOE["tekst"],
            {},
            set(),
            interruptie=Interruption(naam, "Kan hij dat toezeggen?"),
        )
        assert len(nieuw[0].gericht_aan) == service_mod.MAX_GERICHT_AAN

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

    async def test_a_dense_window_gets_room_to_answer(self):
        """A reply that is cut off is no JSON, the second time either."""
        asked: list[int] = []

        class Counting(FakeLLM):
            async def _complete(self, prompt: str, max_tokens: int = 1024) -> str:
                asked.append(max_tokens)
                return await super()._complete(prompt, max_tokens)

        await _ask(Counting(toegezegd()))
        assert asked == [4096]

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
            "🤝 1 toezegging · **open**"
        )
        assert statusregel(
            [
                (SOORT_TOEZEGGING, STATUS_OPEN),
                (SOORT_TOEZEGGING, STATUS_BEANTWOORD),
                (SOORT_VRAAG, STATUS_OPEN),
            ]
        ) == ("❓ 1 vraag · **open**\n🤝 2 toezeggingen · **1 open** · ✅ 1 nagekomen")

    def test_the_states_in_its_own_words(self):
        assert statusregel([(SOORT_TOEZEGGING, STATUS_TOEGEWEZEN)]) == (
            "🤝 1 toezegging · 👀 wordt opgepakt"
        )
        assert statusregel([(SOORT_TOEZEGGING, STATUS_VERVALT)]) == (
            "🤝 1 toezegging · 🚫 hoeft niet"
        )
        assert statusregel([(SOORT_TOEZEGGING, STATUS_VERWORPEN)]) == ""

    def test_the_icon_is_no_other_kind_s(self):
        from bouwmeester.services import debat_statusregel as regel

        iconen = list(regel._SOORT_ICOON.values())
        assert len(set(iconen)) == len(iconen)

    def test_the_pinned_message_is_one_short_line_for_every_kind(self):
        """Spelled out per kind it was a block of text nobody could read."""
        assert LEGENDA == (
            "**Reageer op een markering:** ✅ afgehandeld · 👀 ik pak dit op · "
            "🚫 hoeft niet · ❌ klopt niet"
        )
        assert "\n" not in LEGENDA
        assert len(LEGENDA) < 100


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
                    samenvatting="Stuurt de Kamer de bezetting van de beugels.",
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
        assert row.samenvatting == "Stuurt de Kamer de bezetting van de beugels."
        assert row.termijn == "vóór de begrotingsbehandeling"
        # In a long answer nobody says who it is promised to.
        assert (row.gericht_aan, row.bij_volgnummer, row.stuk) == ("", None, None)
        assert (row.spreker, row.fractie) == (MINISTER, None)
        assert row.beurt_post_id == post_id

        (reply,) = mm.replies
        assert reply[1] == post_id
        assert reply[2] == (
            "🤝 **Stuurt de Kamer de bezetting van de beugels.**\n"
            "Toezegging 1 · vóór de begrotingsbehandeling ·"
            f" [10:36]({MOMENT_URL}) (begin van de spreekbeurt)\n"
            f"> {T_BRIEF}\n"
            "\n"
            f"{NOOT}"
        )
        assert splits(mm.messages[post_id])[1] == "🤝 1 toezegging · **open**"

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
        assert splits(mm.messages[post_id])[1] == "🤝 2 toezeggingen · **open**"
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
        assert splits(mm.messages[post_id])[1] == "🤝 1 toezegging · **open**"

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
        assert splits(mm.messages[post_id])[1] == "❓ 1 vraag · **open**"

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
    BELOOFD = "Stuurt de Kamer een overzicht van de bezetting."

    async def _with_question(self, db_session, **extra):
        """A member asks; the question is open as number 1."""
        sessie_id = await _sessie(db_session)
        mm = FakeMattermost()
        citaat = (
            "Kan de minister vóór de begrotingsbehandeling een overzicht geven van"
            " de bezetting per provincie?"
        )
        raw = {**VRAAGT, "tekst": f"Voorzitter, dank u wel voor het woord. {citaat}"}
        await _judge(
            db_session,
            raw,
            antwoord(
                vraag(citaat, samenvatting="Overzicht van de bezetting?", **extra)
            ),
            sessie_id=sessie_id,
            mm=mm,
        )
        return sessie_id, mm

    async def test_the_model_gets_the_open_questions_with_who_asked(self, db_session):
        sessie_id, mm = await self._with_question(db_session)
        _, _, llm, _, _ = await _judge(
            db_session, ANTWOORD, toegezegd(), sessie_id=sessie_id, mm=mm
        )
        assert "1. Kamerlid A (X): Overzicht van de bezetting?" in llm.prompts[0]

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
        assert (
            splits(mm.messages[vraag_row.beurt_post_id])[1] == "❓ 1 vraag · **open**"
        )
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

    async def test_a_question_from_after_the_answer_is_not_offered(self, db_session):
        """The turns of members are read first in a round, so a question
        can be stored before the answer that came before it is read."""
        sessie_id, mm = await self._with_question(db_session)
        eerder = datetime.fromisoformat(VRAAGT["start"]) - timedelta(minutes=5)
        _, _, llm, _, _ = await _judge(
            db_session,
            ANTWOORD,
            toegezegd(toezegging(T_BRIEF, samenvatting=self.BELOOFD, bij_vraag=1)),
            sessie_id=sessie_id,
            mm=mm,
            start=eerder,
        )
        assert "nog openstaan\n(geen)" in llm.prompts[0]
        assert (await _rows(db_session, sessie_id))[1].bij_volgnummer is None

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
        ook = "Ik stuur dat overzicht vóór de begrotingsbehandeling ook naar de leden."
        await _judge(
            db_session,
            {**ANTWOORD, "tekst": f"{ANTWOORD['tekst']} {ook}"},
            toegezegd(
                toezegging(T_BRIEF, samenvatting=self.BELOOFD, bij_vraag=1),
                toezegging(
                    ook,
                    samenvatting="Stuurt het overzicht ook naar de leden.",
                    bij_vraag=1,
                ),
            ),
            sessie_id=sessie_id,
            mm=mm,
        )
        assert [v[:3] for v in await _vermeldingen(db_session, sessie_id)] == [
            (VERMELDING_ANTWOORD, 1, T_BRIEF),
            (VERMELDING_ANTWOORD, 1, ook),
        ]


class TestNaEenInterruptie:
    """An answer right after an interruption is to that interruption."""

    EERSTE = (
        "Kan de minister zeggen wanneer de Kamer de uitkomst van het gesprek hoort?"
    )
    ANDERE = "Kan de minister zeggen wat het gesprek met de vervoerders kost?"

    async def _first_term(self, db_session):
        """A member asks two questions in the first term: numbers 1 and 2."""
        sessie_id = await _sessie(db_session)
        mm = FakeMattermost()
        raw = {**VRAAGT, "tekst": f"Voorzitter. {self.EERSTE} {self.ANDERE}"}
        await _judge(
            db_session,
            raw,
            antwoord(
                vraag(self.EERSTE, samenvatting="Wanneer hoort de Kamer de uitkomst?"),
                vraag(self.ANDERE, samenvatting="Wat kost het gesprek?"),
            ),
            sessie_id=sessie_id,
            mm=mm,
        )
        return sessie_id, mm

    async def _interruption(self, db_session, sessie_id, mm, answer):
        _, _, _, post_id, _ = await _judge(
            db_session, TURNS[24], answer, sessie_id=sessie_id, mm=mm
        )
        return f"post:{post_id}"

    async def _answer(self, db_session, sessie_id, mm, sleutel, **extra):
        await _judge(
            db_session,
            ZEGT_TOE,
            toegezegd(
                toezegging(
                    T_ZOMER,
                    samenvatting="Meldt vóór de zomer de uitkomst van het gesprek.",
                    **extra,
                )
            ),
            sessie_id=sessie_id,
            mm=mm,
            voorafgaand="Kamerlid A (X)",
            voorafgaand_tekst=TURNS[24]["tekst"],
            voorafgaand_sleutel=sleutel,
        )
        return (await _rows(db_session, sessie_id))[-1]

    async def test_a_question_asked_again_in_the_interruption_is_the_link(
        self, db_session
    ):
        """The member comes back to a question of the first term, which is
        stored as a vermelding on it. The model names the other question of
        that member; where the toezegging stands says which it is."""
        sessie_id, mm = await self._first_term(db_session)
        sleutel = await self._interruption(
            db_session,
            sessie_id,
            mm,
            antwoord(vraag("Kan hij dat toezeggen?", hoort_bij=1)),
        )
        row = await self._answer(db_session, sessie_id, mm, sleutel, bij_vraag=2)
        assert (row.bij_volgnummer, row.gericht_aan) == (1, "Kamerlid A (X)")
        assert "aan Kamerlid A (X) · bij vraag 1 · " in mm.replies[-1][2]
        assert (VERMELDING_ANTWOORD, 1, T_ZOMER, MINISTER) in await _vermeldingen(
            db_session, sessie_id
        )

    async def test_a_question_asked_in_the_interruption_is_the_link(self, db_session):
        sessie_id, mm = await self._first_term(db_session)
        nieuw = "Als hij ook toezegt dat de Kamer vóór de zomer de uitkomst hoort"
        sleutel = await self._interruption(
            db_session,
            sessie_id,
            mm,
            antwoord(
                vraag(
                    f"{nieuw}, dan scheelt dat mij een motie. Kan hij dat toezeggen?",
                    samenvatting="Hoort de Kamer vóór de zomer de uitkomst?",
                )
            ),
        )
        # No number from the model at all.
        row = await self._answer(db_session, sessie_id, mm, sleutel)
        assert (row.bij_volgnummer, row.gericht_aan) == (3, "Kamerlid A (X)")

    async def test_without_a_question_marked_in_it_only_the_member_is_named(
        self, db_session
    ):
        sessie_id, mm = await self._first_term(db_session)
        sleutel = await self._interruption(db_session, sessie_id, mm, antwoord())
        row = await self._answer(db_session, sessie_id, mm, sleutel)
        assert (row.bij_volgnummer, row.gericht_aan) == (None, "Kamerlid A (X)")
        assert "bij vraag" not in mm.replies[-1][2]

    async def test_the_interruption_is_not_known_by_its_key(self, db_session):
        """A caller that does not say which turn the interruption was."""
        sessie_id, mm = await self._first_term(db_session)
        await self._interruption(
            db_session,
            sessie_id,
            mm,
            antwoord(vraag("Kan hij dat toezeggen?", hoort_bij=1)),
        )
        row = await self._answer(db_session, sessie_id, mm, None)
        assert (row.bij_volgnummer, row.gericht_aan) == (None, "Kamerlid A (X)")

    async def test_a_motie_in_the_interruption_is_no_question(self, db_session):
        sessie_id, mm = await self._first_term(db_session)
        raw = {**TURNS[24], "tekst": "Daar dien ik een motie over in. Kan hij dat?"}
        _, _, _, post_id, _ = await _judge(
            db_session, raw, antwoord(), sessie_id=sessie_id, mm=mm
        )
        assert [r.soort for r in await _rows(db_session, sessie_id)][-1] == "motie"
        service = DebatVraagService(db_session, mm, FakeLLM())
        assert await service._vragen_in(sessie_id, f"post:{post_id}") == ()

    async def test_a_question_that_was_answered_in_a_turn_was_not_asked_in_it(
        self, db_session
    ):
        """The vermelding a toezegging leaves on the question it answers
        carries the key of the answer, and is no question of that turn."""
        sessie_id, mm = await self._first_term(db_session)
        sleutel = await self._interruption(
            db_session,
            sessie_id,
            mm,
            antwoord(vraag("Kan hij dat toezeggen?", hoort_bij=1)),
        )
        await self._answer(db_session, sessie_id, mm, sleutel)
        answer_key = (await _rows(db_session, sessie_id))[-1].beurt_sleutel
        service = DebatVraagService(db_session, mm, FakeLLM())
        assert await service._vragen_in(sessie_id, sleutel) == (1,)
        assert await service._vragen_in(sessie_id, answer_key) == ()


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
        assert len(opvulling) > AT_START
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
            toegezegd(
                toezegging(
                    T_BRIEF, samenvatting="Meldt vóór de zomer hoe het verlopen is."
                )
            ),
        )

    async def test_the_next_answer_gets_what_was_promised_before(self, db_session):
        sessie_id, mm, _, _, _ = await self._first(db_session)
        _, _, llm, _, _ = await _judge(
            db_session, ZEGT_TOE, toegezegd(), sessie_id=sessie_id, mm=mm
        )
        assert "al deed\n1. Meldt vóór de zomer hoe het verlopen is." in llm.prompts[0]

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

    async def test_another_promise_filed_as_a_repeat_gets_a_thread_of_its_own(
        self, db_session
    ):
        sessie_id, mm, _, _, _ = await self._first(db_session)
        _, _, _, _, result = await _judge(
            db_session,
            WEIGERT,
            toegezegd(toezegging(T_EVALUATIE, hoort_bij=1)),
            sessie_id=sessie_id,
            mm=mm,
        )
        assert (result.toezeggingen, result.herhaald) == (1, ())
        assert [r.citaat for r in await _rows(db_session, sessie_id)] == [
            T_BRIEF,
            T_EVALUATIE,
        ]
        assert len(mm.replies) == 2
        assert await _vermeldingen(db_session, sessie_id) == []

    async def test_a_repeat_with_a_moment_gives_the_first_one_its_moment(
        self, db_session
    ):
        """Said without a moment first, and with one when asked again."""
        sessie_id, mm, _, _, _ = await self._first(db_session)
        (row,) = await _rows(db_session, sessie_id)
        assert (row.termijn, row.reacties_gewijzigd_at) == (None, None)

        await _judge(
            db_session,
            ZEGT_TOE,
            toegezegd(toezegging(T_ZOMER, hoort_bij=1, termijn="vóór de zomer")),
            sessie_id=sessie_id,
            mm=mm,
        )

        (row,) = await _rows(db_session, sessie_id)
        assert row.termijn == "vóór de zomer"
        # Marked for the round that writes a reply again from its row.
        assert row.reacties_gewijzigd_at is not None
        assert "· vóór de zomer ·" in format_thread(
            row.soort,
            volgnummer=row.volgnummer,
            gericht_aan=row.gericht_aan,
            citaat=row.citaat,
            samenvatting=row.samenvatting,
            stuk=row.stuk,
            moment=row.moment,
            moment_url=row.moment_url,
            termijn=row.termijn,
        )

    async def test_a_repeat_does_not_change_a_moment_that_was_named(self, db_session):
        sessie_id, mm, _, _, _ = await _judge(
            db_session,
            ANTWOORD,
            toegezegd(
                toezegging(
                    T_UITZOEKEN,
                    samenvatting="Meldt hoe het verlopen is, zomer of voorjaar.",
                    termijn="in het voorjaar",
                )
            ),
        )
        await _judge(
            db_session,
            ZEGT_TOE,
            toegezegd(toezegging(T_ZOMER, hoort_bij=1, termijn="vóór de zomer")),
            sessie_id=sessie_id,
            mm=mm,
        )
        (row,) = await _rows(db_session, sessie_id)
        assert row.termijn == "in het voorjaar"
        assert row.reacties_gewijzigd_at is None

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


VULZIN = "Het budget is dit jaar gelijk gebleven aan dat van vorig jaar. "


def vul(zinnen: int) -> str:
    """Sentences of an answer in which nothing is promised."""
    return VULZIN * zinnen


# Two windows: a toezegging at the start, one in the second window.
LANG = f"{T_BRIEF} {vul(70)}{T_UITZOEKEN} {vul(30)}".strip()
# Three windows, and nothing that looks like a commitment in the middle one.
LANG_MET_GAT = f"{T_BRIEF} {vul(150)}{T_UITZOEKEN} {vul(30)}".strip()
# A toezegging of two sentences, with the end of the first window between
# them: 63 sentences of 63 characters and one of 25 are 3,994 characters,
# and the second sentence does not fit in 4,000 any more.
T_HALF = "Ja, dat kan ik toezeggen."
OP_DE_GRENS = f"{vul(63)}{T_ZOMER} {vul(30)}".strip()


def _windows(tekst: str) -> list[tuple[int, int, int]]:
    """Every window of a text, as (read up to, begin, end)."""
    found, vanaf = [], 0
    while (venster := answer_window(tekst, vanaf)) is not None:
        found.append((vanaf, *venster))
        vanaf = venster[1]
    return found


class TestVensters:
    def test_an_ordinary_answer_is_one_window(self):
        tekst = ANTWOORD["tekst"]
        assert answer_window(tekst, 0) == (0, len(tekst))
        assert answer_window(tekst, len(tekst)) is None
        assert next_window(tekst, 0) == (0, 0, len(tekst))

    def test_an_answer_without_the_words_needs_no_window(self):
        assert next_window(TURNS[31]["tekst"], 0) is None
        assert next_window("", 0) is None

    def test_a_long_answer_is_cut_where_a_sentence_ends(self):
        vensters = _windows(LANG)
        assert len(vensters) == 2
        (_, begin1, einde1), (vanaf2, begin2, einde2) = vensters
        assert (begin1, vanaf2, einde2) == (0, einde1, len(LANG))
        assert einde1 <= service_mod.ANTWOORD_VENSTER
        assert einde1 >= service_mod.ANTWOORD_VENSTER // 2
        assert LANG[:einde1].endswith("vorig jaar.")
        assert T_BRIEF in LANG[begin1:einde1]
        assert T_UITZOEKEN in LANG[begin2:einde2]

    def test_a_window_begins_two_sentences_before_where_the_last_one_ended(self):
        _, (vanaf, begin, _) = _windows(LANG)
        assert LANG[begin:vanaf].strip() == vul(2).strip()

    def test_a_sentence_without_an_end_is_not_carried_along(self):
        zonder = "dat is zo " * 500
        tekst = f"{zonder}. {T_BRIEF} {vul(20)}"
        vanaf = len(zonder) + 1
        assert answer_window(tekst, vanaf)[0] == vanaf

    def test_the_dots_of_a_line_that_runs_on_are_no_end_of_a_sentence(self):
        tekst = f"{vul(5)}Ik stuur de Kamer... voor de zomer een brief. {vul(3)}"
        vanaf = tekst.index("Het budget", tekst.index("een brief."))
        begin, _ = answer_window(tekst, vanaf)
        assert tekst[begin:vanaf].startswith(VULZIN.strip())
        assert "Ik stuur de Kamer... voor de zomer een brief." in tekst[begin:vanaf]

    def test_the_windows_cover_the_text_and_never_go_back(self):
        for tekst in (LANG, LANG_MET_GAT, OP_DE_GRENS, vul(400)):
            vensters = _windows(tekst)
            assert vensters[0][0] == 0
            assert vensters[-1][2] == len(tekst)
            for (_, _, einde), (vanaf, begin, verder) in zip(
                vensters, vensters[1:], strict=False
            ):
                assert vanaf == einde
                assert vanaf - service_mod.MAX_OVERLAP <= begin <= vanaf < verder
            nieuw = [einde - vanaf for vanaf, _, einde in vensters]
            limiet = service_mod.ANTWOORD_VENSTER + service_mod.MIN_STAART
            assert max(nieuw) <= limiet
            # No last window of a sentence or two.
            assert len(vensters) == 1 or min(nieuw) >= service_mod.MIN_STAART

    def test_a_long_sentence_in_front_is_not_a_reason_to_go_far_back(self):
        lang = "dat is zo " * 70 + "en niet anders. "
        assert len(lang) > service_mod.MAX_OVERLAP
        tekst = f"{vul(3)}{lang}{T_BRIEF} {vul(20)}"
        vanaf = tekst.index(T_BRIEF)
        assert answer_window(tekst, vanaf)[0] == vanaf

    def test_a_tail_of_a_few_sentences_goes_into_the_window_before_it(self):
        tekst = vul(68).strip()
        assert service_mod.ANTWOORD_VENSTER < len(tekst)
        assert len(tekst) < service_mod.ANTWOORD_VENSTER + service_mod.MIN_STAART
        assert answer_window(tekst, 0) == (0, len(tekst))
        langer = vul(80).strip()
        assert answer_window(langer, 0)[1] < len(langer)

    def test_the_same_text_gives_the_same_windows(self):
        assert _windows(LANG_MET_GAT) == _windows(LANG_MET_GAT)

    def test_no_more_of_an_answer_than_the_limit_is_read(self):
        tekst = vul(1200)
        assert len(tekst) > service_mod.MAX_ANTWOORD
        vensters = _windows(tekst)
        assert vensters[-1][2] == service_mod.MAX_ANTWOORD
        assert len(vensters) <= 13
        assert answer_window(tekst, service_mod.MAX_ANTWOORD) is None

    def test_a_window_without_the_words_is_passed_over(self):
        assert len(_windows(LANG_MET_GAT)) == 3
        eerste = next_window(LANG_MET_GAT, 0)
        tweede = next_window(LANG_MET_GAT, eerste[2])
        # Read up to the start of the third window without asking.
        assert tweede[0] > eerste[2] + service_mod.ANTWOORD_VENSTER // 2
        assert T_UITZOEKEN in LANG_MET_GAT[tweede[0] : tweede[2]]
        assert next_window(LANG_MET_GAT, tweede[2]) is None

    def test_whether_a_window_goes_to_the_model_is_decided_on_what_is_new_in_it(
        self,
    ):
        # The only wording stands in the two sentences the second window
        # shares with the first. That is not a reason to ask twice.
        tekst = f"{vul(61)}{T_BRIEF} {VULZIN}{vul(40)}".strip()
        eerste = next_window(tekst, 0)
        assert T_BRIEF in tekst[: eerste[2]]
        assert T_BRIEF in tekst[answer_window(tekst, eerste[2])[0] : eerste[2] + 200]
        assert next_window(tekst, eerste[2]) is None

    def test_giving_up_on_a_window_goes_on_behind_it(self):
        eerste = next_window(LANG, 0)
        assert skip_window(LANG, 0) == eerste[2]
        assert skip_window(LANG, eerste[2]) == len(LANG)
        assert skip_window(LANG, len(LANG)) == len(LANG)


BELOOFD_UITZOEKEN = "Laat de besteding uitzoeken en meldt dat in het voorjaar."


class TestEenLangAntwoord:
    T_OPNIEUW = "Ik stuur die brief over de bezetting dus vóór de begroting."

    async def _call(self, db_session, sessie_id, mm, post_id, tekst, llm, gelezen=0):
        return await DebatVraagService(db_session, mm, llm).beoordeel_beurt(
            _beurt(
                sessie_id, {**ANTWOORD, "tekst": tekst}, post_id, gelezen_tot=gelezen
            ),
            CONTEXT,
        )

    async def test_one_call_reads_one_window_and_stores_it(self, db_session):
        sessie_id, mm = await _sessie(db_session), FakeMattermost()
        post_id = mm.turn()
        llm = FakeLLM(
            toegezegd(toezegging(T_BRIEF, samenvatting="Stuurt de brief.")),
            toegezegd(toezegging(T_UITZOEKEN)),
        )
        einde = next_window(LANG, 0)[2]

        first = await self._call(db_session, sessie_id, mm, post_id, LANG, llm)

        assert (first.uitkomst, first.meer, first.gelezen_tot) == (
            UITKOMST_GEMARKEERD,
            True,
            einde,
        )
        assert len(llm.prompts) == 1
        # The start of a long answer is read, and only a window of it.
        gevraagd = llm.prompts[0].split("<spreekbeurt>\n")[1].split("\n</spreek")[0]
        assert gevraagd == LANG[:einde]
        # Stored and in the channel before the next window is asked about.
        assert [r.citaat for r in await _rows(db_session, sessie_id)] == [T_BRIEF]
        assert len(mm.replies) == 1

        second = await self._call(
            db_session, sessie_id, mm, post_id, LANG, llm, first.gelezen_tot
        )

        assert (second.meer, second.gelezen_tot, second.toezeggingen) == (
            False,
            len(LANG),
            1,
        )
        assert len(llm.prompts) == 2
        tweede = llm.prompts[1].split("<spreekbeurt>\n")[1].split("\n</spreek")[0]
        assert T_BRIEF not in tweede
        # It begins with the two sentences the first window ended with.
        assert tweede.startswith(vul(2).strip())
        assert tweede.endswith(LANG[einde:])
        # What the first window promised is on the list the second gets.
        assert "al deed\n1. Stuurt de brief." in llm.prompts[1]
        assert [r.citaat for r in await _rows(db_session, sessie_id)] == [
            T_BRIEF,
            T_UITZOEKEN,
        ]
        assert splits(mm.messages[post_id])[1] == "🤝 2 toezeggingen · **open**"

    async def test_an_answer_that_was_read_to_the_end_is_not_asked_about_again(
        self, db_session
    ):
        sessie_id, mm = await _sessie(db_session), FakeMattermost()
        llm = FakeLLM(toegezegd(toezegging(T_BRIEF)))
        done = await self._call(
            db_session, sessie_id, mm, mm.turn(), LANG, llm, len(LANG)
        )
        assert (done.uitkomst, done.meer, done.gelezen_tot) == (
            UITKOMST_AL_BEOORDEELD,
            False,
            len(LANG),
        )
        assert llm.prompts == []

    async def test_a_window_without_the_words_costs_no_call(self, db_session):
        sessie_id, mm = await _sessie(db_session), FakeMattermost()
        post_id = mm.turn()
        llm = FakeLLM(
            toegezegd(toezegging(T_BRIEF)), toegezegd(toezegging(T_UITZOEKEN))
        )
        first = await self._call(db_session, sessie_id, mm, post_id, LANG_MET_GAT, llm)
        second = await self._call(
            db_session, sessie_id, mm, post_id, LANG_MET_GAT, llm, first.gelezen_tot
        )
        # Three windows, two calls.
        assert len(llm.prompts) == 2
        assert (second.meer, second.gelezen_tot) == (False, len(LANG_MET_GAT))
        assert len(await _rows(db_session, sessie_id)) == 2

    async def test_with_nothing_left_to_ask_the_answer_is_read_to_its_end(
        self, db_session
    ):
        tekst = f"{T_BRIEF} {vul(150)}".strip()
        sessie_id, mm = await _sessie(db_session), FakeMattermost()
        only = await self._call(
            db_session,
            sessie_id,
            mm,
            mm.turn(),
            tekst,
            FakeLLM(toegezegd(toezegging(T_BRIEF))),
        )
        assert (only.meer, only.gelezen_tot) == (False, len(tekst))

    @pytest.mark.parametrize(
        "opnieuw",
        [
            toezegging(T_UITZOEKEN, samenvatting=BELOOFD_UITZOEKEN, hoort_bij=2),
            toezegging(T_UITZOEKEN, samenvatting=BELOOFD_UITZOEKEN, bij_vraag=1),
        ],
    )
    async def test_what_two_windows_share_is_not_said_again_and_not_linked_again(
        self, db_session, opnieuw
    ):
        """The second window sees a sentence of the first once more. What
        the model then says about it changes nothing."""
        tekst = f"{vul(61)}{T_UITZOEKEN} {VULZIN}{vul(40)}{T_BRIEF}".strip()
        sessie_id, mm = await _sessie(db_session), FakeMattermost()
        vraag_citaat = "Kan de minister de besteding laten uitzoeken?"
        await _judge(
            db_session,
            {
                **VRAAGT,
                "tekst": f"Voorzitter, dank u wel voor het woord. {vraag_citaat}",
            },
            antwoord(vraag(vraag_citaat, samenvatting="Besteding uitzoeken?")),
            sessie_id=sessie_id,
            mm=mm,
        )
        post_id = mm.turn()
        beloofd = BELOOFD_UITZOEKEN
        llm = FakeLLM(
            toegezegd(toezegging(T_UITZOEKEN, samenvatting=beloofd)),
            toegezegd(opnieuw),
        )
        first = await self._call(db_session, sessie_id, mm, post_id, tekst, llm)
        assert T_UITZOEKEN in tekst[: first.gelezen_tot]
        await self._call(
            db_session, sessie_id, mm, post_id, tekst, llm, first.gelezen_tot
        )

        assert T_UITZOEKEN in llm.prompts[1].split("<spreekbeurt>")[1]
        rows = await _rows(db_session, sessie_id)
        assert [r.soort for r in rows] == [SOORT_VRAAG, SOORT_TOEZEGGING]
        assert rows[1].bij_volgnummer is None
        assert await _vermeldingen(db_session, sessie_id) == []

    async def test_a_window_that_fails_keeps_the_windows_before_it(self, db_session):
        sessie_id, mm = await _sessie(db_session), FakeMattermost()
        post_id = mm.turn()
        llm = FakeLLM(
            toegezegd(toezegging(T_BRIEF)),
            RuntimeError("weg"),
            toegezegd(toezegging(T_UITZOEKEN)),
        )
        first = await self._call(db_session, sessie_id, mm, post_id, LANG, llm)

        failed = await self._call(
            db_session, sessie_id, mm, post_id, LANG, llm, first.gelezen_tot
        )

        assert failed.uitkomst == UITKOMST_LLM_ONBEREIKBAAR
        assert failed.opnieuw_proberen
        # Still at the window that failed, not back at the first.
        assert (failed.gelezen_tot, failed.meer) == (first.gelezen_tot, True)
        assert [r.citaat for r in await _rows(db_session, sessie_id)] == [T_BRIEF]

        again = await self._call(
            db_session, sessie_id, mm, post_id, LANG, llm, failed.gelezen_tot
        )
        assert (again.gelezen_tot, again.meer) == (len(LANG), False)
        assert len(llm.prompts) == 3
        # The first window was asked about once.
        assert sum(T_BRIEF in p.split("<spreekbeurt>")[1] for p in llm.prompts) == 1
        assert len(await _rows(db_session, sessie_id)) == 2

    async def test_an_unreadable_window_counts_as_read_and_the_rest_goes_on(
        self, db_session
    ):
        sessie_id, mm = await _sessie(db_session), FakeMattermost()
        post_id = mm.turn()
        llm = FakeLLM("geen json", "ook niet", toegezegd(toezegging(T_UITZOEKEN)))

        first = await self._call(db_session, sessie_id, mm, post_id, LANG, llm)
        assert (first.uitkomst, first.meer) == (UITKOMST_LLM_ONBRUIKBAAR, True)
        assert first.gelezen_tot == next_window(LANG, 0)[2]
        assert not first.opnieuw_proberen

        second = await self._call(
            db_session, sessie_id, mm, post_id, LANG, llm, first.gelezen_tot
        )
        assert (second.toezeggingen, second.meer) == (1, False)
        assert [r.citaat for r in await _rows(db_session, sessie_id)] == [T_UITZOEKEN]

    async def test_a_window_without_a_toezegging_still_counts_as_read(self, db_session):
        sessie_id, mm = await _sessie(db_session), FakeMattermost()
        first = await self._call(
            db_session, sessie_id, mm, mm.turn(), LANG, FakeLLM(toegezegd())
        )
        assert (first.uitkomst, first.gelezen_tot, first.meer) == (
            UITKOMST_GEEN_TOEZEGGING,
            next_window(LANG, 0)[2],
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
    async def test_a_window_that_is_handed_in_twice_is_stored_once(
        self, db_session, opnieuw
    ):
        """After a restart between storing a window and noting how far it got."""
        sessie_id, mm = await _sessie(db_session), FakeMattermost()
        post_id = mm.turn()
        llm = FakeLLM(
            toegezegd(toezegging(T_BRIEF)),
            toegezegd(toezegging(opnieuw)),
        )
        await self._call(db_session, sessie_id, mm, post_id, LANG, llm)
        again = await self._call(db_session, sessie_id, mm, post_id, LANG, llm)

        assert len(llm.prompts) == 2
        assert again.meer
        assert [r.citaat for r in await _rows(db_session, sessie_id)] == [T_BRIEF]
        assert len(mm.replies) == 1

    @pytest.mark.parametrize(
        ("eerste", "tweede"),
        [
            # Seen in halves by the first window, whole by the second.
            (toezegging(T_HALF), toezegging(T_ZOMER)),
            # Not marked by the first, marked whole by the second.
            (None, toezegging(T_ZOMER)),
            # Marked by the first, and by the second from the sentences the
            # two share.
            (toezegging(T_HALF), toezegging(T_HALF)),
            # Or called "said again" there, pointing at itself.
            (toezegging(T_HALF), toezegging(T_HALF, hoort_bij=1)),
        ],
    )
    async def test_a_toezegging_on_the_boundary_of_two_windows_is_stored_once(
        self, db_session, eerste, tweede
    ):
        sessie_id, mm = await _sessie(db_session), FakeMattermost()
        post_id = mm.turn()
        llm = FakeLLM(toegezegd(*([eerste] if eerste else [])), toegezegd(tweede))
        einde = next_window(OP_DE_GRENS, 0)[2]
        # The end of the first window falls between its two sentences.
        assert OP_DE_GRENS[:einde].endswith(T_HALF)

        first = await self._call(db_session, sessie_id, mm, post_id, OP_DE_GRENS, llm)
        await self._call(
            db_session, sessie_id, mm, post_id, OP_DE_GRENS, llm, first.gelezen_tot
        )

        # The second window was shown the toezegging whole.
        assert T_ZOMER in llm.prompts[1].split("<spreekbeurt>")[1]
        rows = await _rows(db_session, sessie_id)
        assert len(rows) == 1
        assert rows[0].citaat in (T_HALF, T_ZOMER)
        assert len(mm.replies) == 1
        assert await _vermeldingen(db_session, sessie_id) == []

    async def test_one_said_again_in_a_later_window_is_a_herhaling_on_the_first(
        self, db_session
    ):
        tekst = f"{LANG} {self.T_OPNIEUW}"
        sessie_id, mm = await _sessie(db_session), FakeMattermost()
        post_id = mm.turn()
        llm = FakeLLM(
            toegezegd(
                toezegging(T_BRIEF, samenvatting="Stuurt een brief over de bezetting.")
            ),
            toegezegd(toezegging(self.T_OPNIEUW, hoort_bij=1)),
            toegezegd(toezegging(self.T_OPNIEUW, hoort_bij=1)),
        )
        first = await self._call(db_session, sessie_id, mm, post_id, tekst, llm)
        second = await self._call(
            db_session, sessie_id, mm, post_id, tekst, llm, first.gelezen_tot
        )

        assert (second.toezeggingen, second.herhaald) == (0, (1,))
        assert [r.citaat for r in await _rows(db_session, sessie_id)] == [T_BRIEF]
        assert await _vermeldingen(db_session, sessie_id) == [
            (VERMELDING_HERHALING, 1, self.T_OPNIEUW, MINISTER)
        ]
        # And that window handed in once more writes no second vermelding.
        await self._call(
            db_session, sessie_id, mm, post_id, tekst, llm, first.gelezen_tot
        )
        assert len(await _vermeldingen(db_session, sessie_id)) == 1

    async def test_the_link_of_a_window_is_written_once(self, db_session):
        sessie_id, mm = await _sessie(db_session), FakeMattermost()
        vraag_citaat = (
            "Kan de minister zorgen dat de Kamer het overzicht vóór de"
            " begrotingsbehandeling krijgt?"
        )
        await _judge(
            db_session,
            {
                **VRAAGT,
                "tekst": f"Voorzitter, dank u wel voor het woord. {vraag_citaat}",
            },
            antwoord(
                vraag(
                    vraag_citaat,
                    samenvatting="Overzicht vóór de begrotingsbehandeling?",
                )
            ),
            sessie_id=sessie_id,
            mm=mm,
        )
        post_id = mm.turn()
        beloofd = toegezegd(
            toezegging(
                T_BRIEF,
                samenvatting="Stuurt het overzicht vóór de begrotingsbehandeling.",
                bij_vraag=1,
            )
        )
        llm = FakeLLM(beloofd, beloofd)
        await self._call(db_session, sessie_id, mm, post_id, LANG, llm)
        await self._call(db_session, sessie_id, mm, post_id, LANG, llm)
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
                "🤝 1 toezegging · ✅ nagekomen",
            ),
            (
                REACTIE_OPGEPAKT,
                STATUS_TOEGEWEZEN,
                "👀 **Stuurt een brief.**\nToezegging 1 · wordt opgepakt door"
                " persoon.a · ",
                "🤝 1 toezegging · 👀 wordt opgepakt",
            ),
            (
                REACTIE_VERVALT,
                STATUS_VERVALT,
                "🚫 **Stuurt een brief.**\nToezegging 1 · hoeft niet · ",
                "🤝 1 toezegging · 🚫 hoeft niet",
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
        assert splits(mm.messages[row.beurt_post_id])[1] == "🤝 1 toezegging · **open**"


class TestVerworpenToezeggingen:
    async def test_rejected_toezeggingen_can_be_asked_for(self, db_session):
        h = status_helpers
        mm = h.FakeMattermost()
        sessie_id = await h._sessie(db_session)
        vraag_row = await h._markering(
            db_session, mm, sessie_id, 1, status=STATUS_VERWORPEN
        )
        toezegging_row = await h._markering(
            db_session,
            mm,
            sessie_id,
            2,
            soort=SOORT_TOEZEGGING,
            status=STATUS_VERWORPEN,
            gericht_aan="",
            citaat=T_BRIEF,
        )
        await h._markering(db_session, mm, sessie_id, 3, soort=SOORT_TOEZEGGING)

        async def ids(**extra) -> list:
            found = await verworpen_markeringen(
                db_session, sessie_id=sessie_id, **extra
            )
            return [m.id for m in found]

        # A question, as before, unless another kind is asked for.
        assert await ids() == [vraag_row.id]
        assert await ids(soort=SOORT_TOEZEGGING) == [toezegging_row.id]


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
        # And which turn that interruption was: the questions marked in it
        # are what the answer is to.
        assert by_row[m2.id].voorafgaand_sleutel == by_row[b.id].sleutel
        assert by_row[m1.id].voorafgaand_sleutel is None
        # A member gets none of that.
        assert by_row[b.id].voorafgaand is None
        assert by_row[b.id].voorafgaand_sleutel is None
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

    async def test_an_interruption_from_before_a_suspension_is_not_what_is_answered(
        self, db_session, monkeypatch, handed
    ):
        w = worker_helpers
        w.Outside(monkeypatch)
        mm = w.Chat()
        s = await w._running(db_session)
        b = await w._row(db_session, s, "interrupter", 60, "b", tekst=self.VRAAG)
        # No message of its own: the chairman said nothing first.
        await w._row(db_session, s, "suspended", 100, post=False)
        await w._row(db_session, s, "continued", 130, post=False)
        m = await w._row(db_session, s, "speaker", 140, "m", tekst=self.ANTWOORD)
        await w._row(db_session, s, "debate_end", 200)
        w._in_channel(mm, b, m)

        await w._tick(db_session, mm, PerKind(toegezegd(toezegging(self.ANTWOORD))))

        by_row = {beurt.spreekbeurt_id: beurt for beurt, _ in handed}
        assert (by_row[m.id].voorafgaand, by_row[m.id].voorafgaand_tekst) == (None, "")
        rows = [r for r in await _rows(db_session, s.id) if r.soort == SOORT_TOEZEGGING]
        assert [r.gericht_aan for r in rows] == [""]

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

    async def _position(self, db_session, row) -> int | None:
        return await db_session.scalar(
            select(DebatSpreekbeurt.antwoord_gelezen_tot).where(
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
        monkeypatch.setattr(worker_mod, "WINDOW_TIMEOUT", 0.2)
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

    async def test_a_window_has_less_time_than_a_turn_of_a_member(self):
        assert worker_mod.WINDOW_TIMEOUT < worker_mod.JUDGE_TIMEOUT

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

    async def test_a_long_answer_is_read_a_window_per_round_and_kept_in_between(
        self, db_session, monkeypatch, handed
    ):
        w = worker_helpers
        w.Outside(monkeypatch)
        monkeypatch.setattr(worker_mod, "MAX_ANSWER_WINDOWS_PER_ROUND", 1)
        mm = w.Chat()
        llm = PerKind(
            toegezegd(toezegging(T_BRIEF)), toegezegd(toezegging(T_UITZOEKEN))
        )
        s, m, _ = await self._debat(db_session, mm, LANG, leden=0)
        assert await self._position(db_session, m) is None

        first = await w._tick(db_session, mm, llm)

        assert len(llm.asked) == 1
        assert (first.beoordeeld, first.toezeggingen, first.fouten) == (0, 1, 0)
        assert await self._position(db_session, m) == next_window(LANG, 0)[2]
        assert await w._at(db_session, m) is None
        assert [r.citaat for r in await _rows(db_session, s.id)] == [T_BRIEF]

        second = await w._tick(db_session, mm, llm, 715)

        assert len(llm.asked) == 2
        assert (second.beoordeeld, second.toezeggingen) == (1, 1)
        assert await self._position(db_session, m) == len(LANG)
        assert await w._at(db_session, m) is not None
        assert [r.citaat for r in await _rows(db_session, s.id)] == [
            T_BRIEF,
            T_UITZOEKEN,
        ]
        # And it is done: a third round asks nothing.
        await w._tick(db_session, mm, llm, 730)
        assert len(llm.asked) == 2

    async def test_a_window_that_fails_is_tried_again_alone_and_counted_alone(
        self, db_session, monkeypatch, handed
    ):
        w = worker_helpers
        w.Outside(monkeypatch)
        monkeypatch.setattr(db_session, "rollback", w._nothing)
        monkeypatch.setattr(worker_mod, "MAX_ANSWER_WINDOWS_PER_ROUND", 1)
        mm = w.Chat()
        llm = PerKind(
            RuntimeError("weg"),
            toegezegd(toezegging(T_BRIEF)),
            RuntimeError("weg"),
            toegezegd(toezegging(T_UITZOEKEN)),
        )
        s, m, _ = await self._debat(db_session, mm, LANG, leden=0)
        pauze = worker_mod.PAUSE_FIRST.total_seconds() + 1

        await w._tick(db_session, mm, llm)
        assert await self._attempts(db_session, m) == 1
        await w._tick(db_session, mm, llm, 700 + pauze)
        # Read further: the tries of the next window start at none.
        assert await self._attempts(db_session, m) == 0
        einde = next_window(LANG, 0)[2]
        assert await self._position(db_session, m) == einde

        failed = await w._tick(db_session, mm, llm, 715 + pauze)

        assert failed.fouten == 1
        assert await self._attempts(db_session, m) == 1
        assert await self._position(db_session, m) == einde
        assert [r.citaat for r in await _rows(db_session, s.id)] == [T_BRIEF]

        await w._tick(db_session, mm, llm, 715 + 2 * pauze)

        assert len(llm.asked) == 4
        # The first window went to the model twice, once for each try, and
        # not again when the second window failed.
        assert sum(T_BRIEF in p.split("<spreekbeurt>")[1] for p in llm.asked) == 2
        assert await self._position(db_session, m) == len(LANG)
        assert await w._at(db_session, m) is not None
        assert len(await _rows(db_session, s.id)) == 2

    async def test_a_window_that_keeps_failing_is_given_up_on_and_the_rest_is_read(
        self, db_session, monkeypatch, handed, caplog
    ):
        w = worker_helpers
        w.Outside(monkeypatch)
        monkeypatch.setattr(db_session, "rollback", w._nothing)
        mm = w.Chat()
        llm = PerKind(
            *[RuntimeError("weg")] * worker_mod.WINDOW_ATTEMPTS,
            toegezegd(toezegging(T_UITZOEKEN)),
        )
        s, m, _ = await self._debat(db_session, mm, LANG, leden=0)

        at = 700.0
        for _ in range(worker_mod.WINDOW_ATTEMPTS):
            await w._tick(db_session, mm, llm, at)
            at += worker_mod.PAUSE_MAX.total_seconds() + 1

        # The first window is passed, with a line in the log, and the turn
        # is not written off.
        assert len(llm.asked) == worker_mod.WINDOW_ATTEMPTS
        assert await self._position(db_session, m) == next_window(LANG, 0)[2]
        assert await self._attempts(db_session, m) == 0
        assert await w._at(db_session, m) is None
        assert "overgeslagen, verder vanaf" in caplog.text

        done = await w._tick(db_session, mm, llm, at)

        assert (done.beoordeeld, done.toezeggingen) == (1, 1)
        assert [r.citaat for r in await _rows(db_session, s.id)] == [T_UITZOEKEN]
        assert await w._at(db_session, m) is not None

    async def test_giving_up_on_the_last_window_ends_the_turn_and_keeps_the_rest(
        self, db_session, monkeypatch, handed
    ):
        w = worker_helpers
        w.Outside(monkeypatch)
        monkeypatch.setattr(db_session, "rollback", w._nothing)
        monkeypatch.setattr(worker_mod, "MAX_ANSWER_WINDOWS_PER_ROUND", 1)
        mm = w.Chat()
        llm = PerKind(
            toegezegd(toezegging(T_BRIEF)),
            *[RuntimeError("weg")] * worker_mod.WINDOW_ATTEMPTS,
        )
        s, m, _ = await self._debat(db_session, mm, LANG, leden=0)

        at = 700.0
        for _ in range(1 + worker_mod.WINDOW_ATTEMPTS):
            await w._tick(db_session, mm, llm, at)
            at += worker_mod.PAUSE_MAX.total_seconds() + 1

        assert await w._at(db_session, m) is not None
        assert await self._position(db_session, m) == len(LANG)
        assert [r.citaat for r in await _rows(db_session, s.id)] == [T_BRIEF]
        # Nothing is asked after that.
        await w._tick(db_session, mm, llm, at)
        assert len(llm.asked) == 1 + worker_mod.WINDOW_ATTEMPTS

    async def test_no_more_windows_of_answers_in_a_round_than_the_limit(
        self, db_session, monkeypatch, handed
    ):
        w = worker_helpers
        w.Outside(monkeypatch)
        mm = w.Chat()
        llm = PerKind()
        s = await w._running(db_session)
        answers = [
            await w._row(db_session, s, "speaker", 60 + 10 * i, "m", tekst=self.KORT)
            for i in range(worker_mod.MAX_ANSWER_WINDOWS_PER_ROUND + 2)
        ]
        lid = await w._row(
            db_session, s, "speaker", 200, "a", tekst=f"{w.OPENING} {w.Q_WANNEER}"
        )
        await w._row(db_session, s, "debate_end", 300)
        w._in_channel(mm, *answers, lid)

        await w._tick(db_session, mm, llm)

        assert len(llm.asked) == worker_mod.MAX_ANSWER_WINDOWS_PER_ROUND
        assert await w._at(db_session, lid) is not None
        # The rest follows in the rounds after, oldest first.
        await w._tick(db_session, mm, llm, 715)
        assert len(llm.asked) == len(answers)

    async def test_an_answer_that_fails_does_not_stop_the_answer_after_it(
        self, db_session, monkeypatch, handed
    ):
        w = worker_helpers
        w.Outside(monkeypatch)
        monkeypatch.setattr(db_session, "rollback", w._nothing)
        mm = w.Chat()
        llm = PerKind(RuntimeError("weg"), toegezegd(toezegging(self.KORT)))
        s = await w._running(db_session)
        een = await w._row(db_session, s, "speaker", 60, "m", tekst=self.KORT)
        twee = await w._row(db_session, s, "speaker", 90, "m", tekst=self.KORT)
        await w._row(db_session, s, "debate_end", 200)
        w._in_channel(mm, een, twee)

        result = await w._tick(db_session, mm, llm)

        assert (result.fouten, result.beoordeeld, result.toezeggingen) == (1, 1, 1)
        assert await w._at(db_session, een) is None
        assert await w._at(db_session, twee) is not None

    async def test_one_long_answer_does_not_take_more_than_the_limit_either(
        self, db_session, monkeypatch, handed
    ):
        w = worker_helpers
        w.Outside(monkeypatch)
        mm = w.Chat()
        llm = PerKind()
        tekst = f"{LANG} {LANG} {LANG}"
        s, m, _ = await self._debat(db_session, mm, tekst, leden=0)

        await w._tick(db_session, mm, llm)

        assert len(llm.asked) == 1
        # One window of one turn per round; the turn comes back next round.
        await w._tick(db_session, mm, llm, 715)
        assert len(llm.asked) == 2

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
