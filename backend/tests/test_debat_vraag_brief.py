"""Tests for a question that asks for something on paper.

The rule is pure and tested as such, on made-up sentences and on the
synthetic debate of the fixture. That the property reaches the row and the
reply, and that a question and the toezegging that answers it read as a
pair, runs against a real database with a fake Mattermost that keeps
messages and reactions the way the real one does.

No names of people: the speakers are "Kamerlid A (X)" and "Bewindspersoon
A", every sentence is made up.
"""

from __future__ import annotations

import itertools

import pytest
from sqlalchemy import select, update

from bouwmeester.models.debat_markering import (
    SOORT_TOEZEGGING,
    SOORT_VRAAG,
    STATUS_BEANTWOORD,
    STATUS_OPEN,
    STATUS_TOEGEWEZEN,
    STATUS_VERWORPEN,
    VERMELDING_ANTWOORD,
    DebatMarkering,
    DebatMarkeringVermelding,
)
from bouwmeester.services.debat_statusregel import splits
from bouwmeester.services.debat_vraag_brief import (
    MAX_MOMENT,
    PRODUCT_ACTIEPLAN,
    PRODUCT_BERICHT,
    PRODUCT_BRIEF,
    PRODUCT_EVALUATIE,
    PRODUCT_INFORMATIE,
    PRODUCT_NOTITIE,
    PRODUCT_OP_PAPIER,
    PRODUCT_OVERZICHT,
    PRODUCT_PLAN,
    PRODUCT_PLANNING,
    PRODUCT_RAPPORTAGE,
    PRODUCT_ROUTEKAART,
    PRODUCT_SCHRIFTELIJK,
    PRODUCT_TIJDPAD,
    PRODUCTS,
    PaperRequest,
    paper_request,
)
from bouwmeester.services.debat_vraag_reacties import (
    REACTIE_GEEN_VRAAG,
    REACTIE_OPGEPAKT,
)
from bouwmeester.services.debat_vraag_service import (
    LATER_GEVRAAGD,
    MAX_TERMIJN,
    MAX_TOEGEZEGD,
    UITKOMST_GEMARKEERD,
    DebatVraagService,
    format_thread,
    format_vraag_thread,
    later_op_papier,
    lees_antwoord,
    next_window,
    toezeggingen_bij,
)
from bouwmeester.services.debat_vraag_vorm import has_question_form
from bouwmeester.services.llm.base import DebatVraag
from tests import test_debat_vraag_status as status_helpers
from tests.test_debat_toezegging import (
    ANTWOORD,
    CONTEXT,
    SYN,
    T_BRIEF,
    VRAAGT,
    _beurt,
    toegezegd,
    toezegging,
    vul,
)
from tests.test_debat_vragen import FakeLLM, antwoord, vraag

MOMENT = status_helpers.MOMENT

# --- the rule ----------------------------------------------------------

# Statements that hold a word for paper and a word for sending or getting.
# None of them asks anything, and none has the form of a question.
STATEMENTS = [
    "we krijgen steeds een overzicht dat niet klopt",
    "een brief sturen lost niets op",
    "gemeenten krijgen geen overzicht van de kosten",
    "de wethouder stuurt ouders een brief met een boete",
    "het actieplan is naar de kamer gestuurd wat is er sindsdien gebeurd",
    "dat staat schriftelijk vast",
    "wij ontvangen signalen dat de gegevens niet kloppen",
    "bij het debat van vorige week heeft de minister de kamer verkeerd geinformeerd",
]
# Questions in which a letter or an overview is spoken of, not asked for.
QUESTIONS_ABOUT = [
    "waarom krijgen ouders een brief zonder uitleg",
    "is de minister bereid het overzicht dat er ligt serieus te nemen",
    "waarom is de brief zo laat naar de kamer gestuurd",
    "de minister schrijft in een brief dat het goed gaat is dat zo",
]


class TestWatOpPapierWordtGevraagd:
    @pytest.mark.parametrize(
        ("citaat", "product", "moment"),
        [
            # A form of answering.
            (
                "Kan de staatssecretaris ons per brief laten weten hoe dat zit?",
                PRODUCT_BRIEF,
                None,
            ),
            (
                "Kan de minister daar schriftelijk op terugkomen?",
                PRODUCT_SCHRIFTELIJK,
                None,
            ),
            (
                "Is de staatssecretaris bereid de vragen schriftelijk te"
                " beantwoorden vóór het commissiedebat?",
                PRODUCT_SCHRIFTELIJK,
                "vóór het commissiedebat",
            ),
            ("wil de staatssecretaris dat op papier zetten", PRODUCT_OP_PAPIER, None),
            ("Graag schriftelijk, voorzitter.", PRODUCT_SCHRIFTELIJK, None),
            # The bewindspersoon is asked to send it.
            (
                "Wil de staatssecretaris een overzicht van de kosten naar de Kamer"
                " sturen?",
                PRODUCT_OVERZICHT,
                None,
            ),
            (
                "Kan de minister toezeggen dat hij de Kamer vóór het kerstreces"
                " een overzicht stuurt van de kosten per station?",
                PRODUCT_OVERZICHT,
                "vóór het kerstreces",
            ),
            ("Kan het kabinet daar een notitie over sturen?", PRODUCT_NOTITIE, None),
            (
                "Is de minister bereid daar een brief over te schrijven?",
                PRODUCT_BRIEF,
                None,
            ),
            (
                "Ik vraag de minister een overzicht van de kosten te sturen.",
                PRODUCT_OVERZICHT,
                None,
            ),
            ("Stuurt de minister ons daar een brief over?", PRODUCT_BRIEF, None),
            # Given by a moment: not something that is said on the spot.
            (
                "Kan de minister vóór de begrotingsbehandeling een overzicht"
                " geven van de bezetting per provincie?",
                PRODUCT_OVERZICHT,
                "vóór de begrotingsbehandeling",
            ),
            # The member wants to get it.
            (
                "Ik zou graag vóór de begrotingsbehandeling een brief van de"
                " minister ontvangen.",
                PRODUCT_BRIEF,
                "vóór de begrotingsbehandeling",
            ),
            (
                "Wij verwachten deze maand nog een briefje waarin staat hoeveel"
                " stallingen er zijn.",
                PRODUCT_BRIEF,
                None,
            ),
            (
                "Krijgen wij daar elk jaar een rapportage over?",
                PRODUCT_RAPPORTAGE,
                None,
            ),
            (
                "Ik ga de minister om een brief vragen, graag vóór de zomer.",
                PRODUCT_BRIEF,
                "vóór de zomer",
            ),
            # Named as where an answer can come.
            ("kan dat in een brief", PRODUCT_BRIEF, None),
            (
                "Dat mag wat mij betreft in een volgende brief, als de minister"
                " er dan uitgebreider op terugkomt.",
                PRODUCT_BRIEF,
                None,
            ),
            # A plan, an evaluatie or a tijdpad on its way to the Kamer, each
            # by the word the member used.
            (
                "Kan de minister het plan vóór 1 maart naar de Kamer sturen?",
                PRODUCT_PLAN,
                "vóór 1 maart",
            ),
            (
                "Kunnen wij de evaluatie nog dit jaar ontvangen?",
                PRODUCT_EVALUATIE,
                "nog dit jaar",
            ),
            (
                "Kan de staatssecretaris een tijdpad naar de Kamer sturen?",
                PRODUCT_TIJDPAD,
                None,
            ),
            (
                "Kan de minister de planning naar de Kamer sturen?",
                PRODUCT_PLANNING,
                None,
            ),
            (
                "Wil de minister ons een routekaart toesturen?",
                PRODUCT_ROUTEKAART,
                None,
            ),
            (
                "Kan het kabinet het actieplan aan de Kamer toezenden?",
                PRODUCT_ACTIEPLAN,
                None,
            ),
            # The Kamer informed by a moment.
            (
                "Wil zij de Kamer voorafgaand aan het commissiedebat... informeren"
                " over de stand van het fonds?",
                PRODUCT_BERICHT,
                "voorafgaand aan het commissiedebat",
            ),
            (
                "Wil de minister ons daar binnen twee weken over informeren?",
                PRODUCT_BERICHT,
                "binnen twee weken",
            ),
            (
                "kan de minister de kamer in maart informeren",
                PRODUCT_BERICHT,
                "in maart",
            ),
            # Information to receive.
            (
                "Wij ontvangen graag de gegevens over de bezetting van de stallingen.",
                PRODUCT_INFORMATIE,
                None,
            ),
        ],
    )
    def test_a_request_for_paper_is_named(self, citaat, product, moment):
        assert paper_request(citaat) == PaperRequest(product, moment)
        assert product in PRODUCTS

    @pytest.mark.parametrize("citaat", STATEMENTS)
    def test_a_statement_with_paper_and_sending_in_it_asks_nothing(self, citaat):
        assert not has_question_form(citaat)
        assert paper_request(citaat) is None

    @pytest.mark.parametrize("citaat", QUESTIONS_ABOUT)
    def test_a_question_about_paper_that_is_there_asks_for_none(self, citaat):
        assert paper_request(citaat) is None

    @pytest.mark.parametrize(
        "citaat",
        [
            # An answer on the spot.
            "Kan de minister daar iets over zeggen?",
            "Graag een reactie van de minister.",
            "Wat gaat dat kosten?",
            "Kan de minister een overzicht geven van de maatregelen?",
            # "Informeren" without a moment, or not the Kamer.
            "Kan de minister de Kamer daarover informeren?",
            "Kan de minister ons informeren over wat er dit jaar is gebeurd?",
            "Wil de minister de gemeenten vóór de zomer informeren over de regeling?",
            # A moment without anything on paper.
            "Kan de minister vóór de zomer met de vervoerders in gesprek gaan?",
            # About a letter that exists.
            "In de brief van vorige week staat dat de proef is verlengd. Kan de"
            " minister zeggen waarom?",
            "Het kabinet schrijft in zijn brief dat de gemeenten aan zet zijn. Waarom?",
            "Wat vindt de minister van het overzicht dat de vervoerders hebben"
            " gemaakt?",
            "Uit de laatste rapportage blijkt dat het aantal diefstallen stijgt."
            " Hoe kan dat?",
            "De brief van 3 maart noemt geen bedrag. Wat gaat het kosten?",
            "Graag een reactie op de brief van de vervoerders.",
            "Kan de minister ingaan op de brief van vorige week?",
            "Wij krijgen de laatste rapportage steeds te laat. Hoe komt dat?",
            "Die notitie noemt geen bedrag. Stuurt de minister ons nog een aanvulling?",
            # A member announcing something of their own.
            "Ik zal zelf een brief sturen aan de vervoerders. Wat vindt de"
            " minister daarvan?",
            "Ik zal de minister een brief sturen met onze bezwaren.",
            "Wij komen daarover met een eigen notitie. Kan de minister wachten?",
            # When or why is answered on the spot.
            "Wanneer komt de evaluatie naar de Kamer?",
            "Wanneer kunnen wij de brief verwachten?",
            "Waarom kan de minister daar geen brief over sturen?",
            # A condition: it announces a motie and asks for nothing yet.
            "ik overweeg een motie tenzij de minister een brief toezegt",
            "Ik dien een motie in, tenzij de minister een brief wil sturen.",
            "Ik overweeg een motie, tenzij de minister graag een brief stuurt.",
            # Policy, not paper.
            "Komt de minister met een plan voor de kleine stations?",
            "Kan de minister een plan maken voor de kleine stations?",
            "Is de minister bereid de proef te laten evalueren?",
            "Hoe kijkt de minister aan tegen de planning van de vervoerders?",
            # The procedure, and what was done in writing before.
            "In het schriftelijk overleg heeft de minister dit ontkend. Klopt dat?",
            "Kan de minister in het schriftelijk overleg daarop ingaan?",
            "De minister heeft schriftelijk laten weten dat het geld op is. Hoe"
            " kan dat?",
            # What only exists on paper.
            "Bestaat dat toezicht ook buiten wat er op papier staat?",
            "Kan de minister zeggen of dat toezicht alleen op papier bestaat?",
            # Receiving something else than information.
            "Wij ontvangen graag een reactie van de minister.",
            "Hoeveel brieven heeft de minister voor de zomer nog gekregen?",
            "",
        ],
    )
    def test_what_asks_for_nothing_on_paper(self, citaat):
        assert paper_request(citaat) is None

    def test_the_moment_of_the_sending_is_not_the_moment_it_is_for(self):
        found = paper_request(
            "Kan de minister na de zomer een brief sturen zodat we die voor de"
            " begrotingsbehandeling kunnen bespreken?"
        )
        assert found == PaperRequest(PRODUCT_BRIEF, "na de zomer")

    def test_a_moment_in_another_sentence_is_not_by_when(self):
        found = paper_request(
            "Vóór de zomer zijn de regels veranderd. Kan de minister daar een"
            " brief over sturen?"
        )
        assert found == PaperRequest(PRODUCT_BRIEF, None)

    def test_a_moment_in_front_of_the_request_is_not_by_when(self):
        found = paper_request(
            "Vóór de zomer zijn de regels veranderd en kan de minister daar een"
            " brief over sturen?"
        )
        assert found == PaperRequest(PRODUCT_BRIEF, None)

    def test_when_in_one_sentence_does_not_undo_a_request_in_the_next(self):
        found = paper_request(
            "Wanneer is de telling klaar? Kan de minister daar een brief over sturen?"
        )
        assert found == PaperRequest(PRODUCT_BRIEF, None)

    def test_what_the_letter_is_about_is_not_by_when(self):
        assert paper_request(
            "Kan de minister de Kamer schriftelijk laten weten hoeveel beugels er"
            " voor het kerstreces zijn bijgekomen?"
        ) == PaperRequest(PRODUCT_SCHRIFTELIJK, None)
        assert paper_request(
            "Kan de minister een brief sturen over wat er vóór de zomer is gebeurd?"
        ) == PaperRequest(PRODUCT_BRIEF, None)

    def test_of_two_moments_none_is_shown(self):
        found = paper_request(
            "Kan de minister, liefst vóór het kerstreces en anders uiterlijk vóór"
            " de zomer, een brief sturen?"
        )
        assert found == PaperRequest(PRODUCT_BRIEF, None)

    def test_a_moment_right_behind_the_request_belongs_to_it(self):
        found = paper_request("Graag een brief, uiterlijk vóór   het Zomerreces!")
        assert found == PaperRequest(PRODUCT_BRIEF, "uiterlijk vóór het zomerreces")

    def test_a_moment_is_never_longer_than_its_cap(self):
        found = paper_request(
            "Kan de minister binnen " + "x" * 200 + " weken een brief sturen?"
        )
        assert found is not None
        assert found.moment is None or len(found.moment) <= MAX_MOMENT

    def test_punctuation_and_case_do_not_matter(self):
        assert paper_request("KAN DE MINISTER... EEN BRIEF STUREN") == PaperRequest(
            PRODUCT_BRIEF, None
        )

    def test_the_first_sentence_that_asks_decides(self):
        found = paper_request(
            "De gemeenten krijgen geen overzicht. Kan de minister dat overzicht"
            " naar de Kamer sturen? En graag ook een notitie."
        )
        assert found == PaperRequest(PRODUCT_OVERZICHT, None)


class TestOpHetVerzonnenDebat:
    """The fixture says what each request asks for; the rule has to agree."""

    def test_every_request_for_a_letter_is_named_as_the_fixture_has_it(self):
        requests = [i for i in SYN["items"] if i["soort"] == "verzoek_om_brief"]
        assert len(requests) == 3
        for item in requests:
            assert paper_request(item["citaat"]) == PaperRequest(
                item["vraagt_om"], item["termijn"]
            ), item["citaat"]

    def test_no_other_question_asks_for_paper(self):
        for item in SYN["items"]:
            if item["soort"] == SOORT_VRAAG:
                assert paper_request(item["citaat"]) is None, item["citaat"]

    def test_nothing_that_should_not_be_marked_asks_for_paper(self):
        # Not the chairman's turns: nothing of the chairman is a question.
        chairman = {t["nr"] for t in SYN["beurten"] if t["soort"] == "chairman"}
        for negative in SYN["negatieven"]:
            if negative["beurt"] not in chairman:
                assert paper_request(negative["citaat"]) is None, negative["citaat"]
        assert [n for n in SYN["negatieven"] if n["type"] == "eigen_brief"]


# --- from the answer of the model to the row ---------------------------

Q_OVERZICHT = (
    "Kan de minister vóór de begrotingsbehandeling een overzicht sturen van de"
    " bezetting per provincie?"
)
Q_GEWOON = "Kan de minister zeggen wat de bewaking van een stalling kost?"
Q_BESTAAND = (
    "In de brief van vorige week schrijft de minister dat de telling loopt. Kan"
    " de minister zeggen wat daar uit komt?"
)
DICTUM = (
    "verzoekt de regering een overzicht van de kosten naar de Kamer te sturen,"
    " en gaat over tot de orde van de dag."
)
VOOR_DE_BEGROTING = "vóór de begrotingsbehandeling"


def _vraag(citaat: str, **extra) -> DebatVraag:
    return DebatVraag(
        **{"citaat": citaat, "gericht_aan": "de minister", "samenvatting": "S", **extra}
    )


class TestLeesAntwoord:
    def test_a_question_that_asks_for_paper_carries_what_and_when(self):
        tekst = f"Voorzitter. {Q_OVERZICHT} {Q_GEWOON}"
        nieuw, _, afgevallen = lees_antwoord(
            [_vraag(Q_OVERZICHT), _vraag(Q_GEWOON)], tekst, [], set()
        )
        assert afgevallen == 0
        assert [(n.vraagt_om, n.termijn) for n in nieuw] == [
            (PRODUCT_OVERZICHT, VOOR_DE_BEGROTING),
            (None, None),
        ]
        # A question still: the property makes no kind of its own.
        assert {n.soort for n in nieuw} == {SOORT_VRAAG}

    def test_a_question_about_a_letter_that_exists_asks_for_none(self):
        (een,), _, _ = lees_antwoord([_vraag(Q_BESTAAND)], Q_BESTAAND, [], set())
        assert (een.vraagt_om, een.termijn) == (None, None)

    # Not the last of them: it has no form the check for questions knows,
    # and was dropped before this rule existed.
    @pytest.mark.parametrize("citaat", QUESTIONS_ABOUT[:3])
    def test_a_question_about_paper_stays_a_question_without_the_property(self, citaat):
        (een,), _, afgevallen = lees_antwoord([_vraag(citaat)], citaat, [], set())
        assert (een.vraagt_om, een.termijn, afgevallen) == (None, None, 0)

    def test_the_dictum_of_a_motie_never_becomes_a_request(self):
        nieuw, _, afgevallen = lees_antwoord([_vraag(DICTUM)], DICTUM, [], set())
        assert (nieuw, afgevallen) == ([], 1)

    @pytest.mark.parametrize(
        "citaat",
        [
            "Wij verwachten deze maand nog een briefje waarin staat hoeveel"
            " stallingen er zijn.",
            "Ik zou graag vóór de begrotingsbehandeling een brief van de minister"
            " ontvangen met de bezetting per provincie.",
        ],
    )
    def test_a_request_for_paper_is_kept_in_a_form_no_question_has(self, citaat):
        assert not has_question_form(citaat)
        (een,), _, afgevallen = lees_antwoord([_vraag(citaat)], citaat, [], set())
        assert (een.vraagt_om, afgevallen) == (PRODUCT_BRIEF, 0)

    @pytest.mark.parametrize(
        "citaat",
        [*STATEMENTS, "In de brief van vorige week staat dat de proef is verlengd."],
    )
    def test_a_statement_is_dropped_whatever_it_says_about_paper(self, citaat):
        # Also when the model hands it in as a question to the minister.
        assert lees_antwoord([_vraag(citaat)], citaat, [], set()) == ([], [], 1)

    def test_a_question_asked_again_says_whether_it_asks_for_paper_now(self):
        _, (again,), _ = lees_antwoord(
            [_vraag(Q_OVERZICHT, hoort_bij=4)], Q_OVERZICHT, [], {4}
        )
        assert (again.volgnummer, again.op_papier, again.termijn) == (4, True, None)
        _, (plain,), _ = lees_antwoord(
            [_vraag(Q_GEWOON, hoort_bij=4)], Q_GEWOON, [], {4}
        )
        assert plain.op_papier is False

    def test_the_property_is_read_from_the_quote_and_not_from_the_summary(self):
        # A model that writes "vraagt om een brief" over a plain question
        # does not make it one: only what stands in the turn counts.
        (een,), _, _ = lees_antwoord(
            [_vraag(Q_GEWOON, samenvatting="Vraagt om een brief vóór de zomer.")],
            Q_GEWOON,
            [],
            set(),
        )
        assert (een.vraagt_om, een.termijn) == (None, None)


# --- the reply ---------------------------------------------------------


def _thread(**extra) -> str:
    values = {
        "volgnummer": 12,
        "gericht_aan": "de minister",
        "citaat": Q_OVERZICHT,
        "samenvatting": "Een overzicht van de bezetting per provincie?",
        "stuk": None,
        "moment": MOMENT,
        "moment_url": None,
        "vraag_moment": MOMENT,
    }
    values.update(extra)
    return format_vraag_thread(**values)


def _meta(tekst: str) -> str:
    return tekst.split("\n")[1]


def _erbij(tekst: str) -> str:
    """The line under the meta line, when it is the one this is about."""
    regel = tekst.split("\n")[2]
    return regel if regel.startswith(("✉️", "🤝")) else ""


PLAIN_META = "Vraag 12 · aan de minister · 10:02"


class TestDeRegelOnderDeVraag:
    def test_a_plain_question_reads_as_it_did(self):
        assert _meta(_thread()) == PLAIN_META
        assert _erbij(_thread()) == ""
        assert _thread() == _thread(
            vraagt_om=None, termijn=None, toegezegd=(), later_om=None
        )

    def test_what_is_asked_on_paper_is_one_line_under_the_line_that_was_there(self):
        zonder = _thread().split("\n")
        met = _thread(vraagt_om=PRODUCT_BRIEF).split("\n")
        assert met[2] == "✉️ een brief"
        # The line that was there is as it was, and so is everything else.
        assert met[:2] + met[3:] == zonder

    def test_the_moment_follows_what_is_asked(self):
        tekst = _thread(vraagt_om=PRODUCT_OVERZICHT, termijn=VOOR_DE_BEGROTING)
        assert _erbij(tekst) == "✉️ een overzicht, vóór de begrotingsbehandeling"
        assert _meta(tekst) == PLAIN_META

    def test_a_toezegging_that_followed_stands_on_the_same_line(self):
        tekst = _thread(
            vraagt_om=PRODUCT_OVERZICHT, termijn=VOOR_DE_BEGROTING, toegezegd=(15,)
        )
        assert tekst.split("\n")[:4] == [
            "❓ **Een overzicht van de bezetting per provincie?**",
            PLAIN_META,
            "✉️ een overzicht, vóór de begrotingsbehandeling · 🤝 toezegging 15",
            f"> {Q_OVERZICHT}",
        ]
        # Also on a question that asked for nothing on paper.
        assert _erbij(_thread(toegezegd=(15,))) == "🤝 toezegging 15"

    def test_two_toezeggingen_are_named_and_more_are_counted(self):
        assert MAX_TOEGEZEGD == 2
        assert _erbij(_thread(toegezegd=(15, 17))) == "🤝 toezegging 15, 17"
        assert _erbij(_thread(toegezegd=(15, 17, 21))) == "🤝 toezegging 15, 17 +1"
        assert (
            _erbij(_thread(toegezegd=(15, 17, 21, 30, 31))) == "🤝 toezegging 15, 17 +3"
        )

    def test_what_was_asked_for_later_says_that_it_came_later(self):
        tekst = _thread(later_om=PRODUCT_BRIEF, later_termijn="vóór het kerstreces")
        assert _erbij(tekst) == f"✉️ {LATER_GEVRAAGD} een brief, vóór het kerstreces"
        assert _erbij(_thread(later_om=PRODUCT_BRIEF)) == "✉️ later gevraagd: een brief"

    def test_what_the_question_asked_for_itself_goes_before_what_came_later(self):
        tekst = _thread(vraagt_om=PRODUCT_OVERZICHT, later_om=PRODUCT_BRIEF)
        assert _erbij(tekst) == "✉️ een overzicht"

    def test_the_document_and_the_quote_come_after_it(self):
        regels = _thread(
            vraagt_om=PRODUCT_BRIEF, toegezegd=(3,), stuk="Reactie van het kabinet"
        ).split("\n")
        assert regels[2:5] == [
            "✉️ een brief · 🤝 toezegging 3",
            "📄 Reactie van het kabinet",
            f"> {Q_OVERZICHT}",
        ]

    def test_where_it_stands_stays_in_the_line_that_was_there(self):
        tekst = _thread(
            vraagt_om=PRODUCT_OVERZICHT, status=STATUS_TOEGEWEZEN, door="persoon.a"
        )
        assert _meta(tekst) == (
            "Vraag 12 · opgepakt door persoon.a · aan de minister · 10:02"
        )
        assert _erbij(tekst) == "✉️ een overzicht"

    def test_a_moment_without_a_request_is_not_shown(self):
        assert _thread(termijn="vóór de zomer") == _thread()
        assert _thread(later_termijn="vóór de zomer") == _thread()

    def test_only_a_product_the_code_knows_is_shown(self):
        assert _thread(vraagt_om="@all **een brief**", termijn="x") == _thread()
        assert _thread(later_om="@all **een brief**") == _thread()

    def test_the_moment_is_escaped_and_capped(self):
        gevaarlijk = "voor de zomer @channel **vet** [x](http://voorbeeld.example)"
        for extra in (
            {"vraagt_om": PRODUCT_BRIEF, "termijn": gevaarlijk},
            {"later_om": PRODUCT_BRIEF, "later_termijn": gevaarlijk},
        ):
            regel = _erbij(_thread(**extra))
            assert "@" not in regel
            assert "**" not in regel.replace("\\*\\*", "")
            assert "://" not in regel
        lang = _erbij(_thread(vraagt_om=PRODUCT_BRIEF, termijn="voor " + "a" * 500))
        assert len(lang) <= len("✉️ een brief, ") + MAX_TERMIJN

    def test_a_moment_cannot_add_a_line(self):
        tekst = _thread(vraagt_om=PRODUCT_BRIEF, termijn="voor de zomer\n> nep citaat")
        assert len(tekst.split("\n")) == len(_thread().split("\n")) + 1

    def test_the_line_is_never_longer_than_its_parts_allow(self):
        langste = max(PRODUCTS, key=len)
        regel = _erbij(
            _thread(
                later_om=langste, later_termijn="m" * 500, toegezegd=range(100, 140)
            )
        )
        assert len(regel) <= (
            len(f"✉️ {LATER_GEVRAAGD} {langste}, ")
            + MAX_TERMIJN
            + len(" · 🤝 toezegging 100, 101 +38")
        )

    @pytest.mark.parametrize(
        ("vraagt_om", "termijn", "later_om", "toegezegd", "status", "stuk", "eerste"),
        list(
            itertools.product(
                (None, PRODUCT_BRIEF),
                (None, "vóór de zomer"),
                (None, PRODUCT_OVERZICHT),
                ((), (15,), (15, 17, 21)),
                (STATUS_OPEN, STATUS_TOEGEWEZEN, STATUS_BEANTWOORD),
                (None, "Een stuk"),
                (True, False),
            )
        ),
    )
    def test_every_combination_is_the_plain_reply_with_at_most_one_line_more(
        self, vraagt_om, termijn, later_om, toegezegd, status, stuk, eerste
    ):
        gemeen = {"status": status, "stuk": stuk, "first_in_thread": eerste}
        plain = _thread(**gemeen).split("\n")
        tekst = _thread(
            vraagt_om=vraagt_om,
            termijn=termijn,
            later_om=later_om,
            later_termijn=termijn,
            toegezegd=toegezegd,
            **gemeen,
        ).split("\n")
        iets = bool(vraagt_om or later_om or toegezegd)
        assert len(tekst) == len(plain) + iets
        assert tekst[:2] == plain[:2]
        assert tekst[2 + iets :] == plain[2:]
        if iets:
            regel = tekst[2]
            assert regel.count("✉️") == int(bool(vraagt_om or later_om))
            assert regel.count("🤝") == int(bool(toegezegd))
            assert (LATER_GEVRAAGD in regel) == bool(later_om and not vraagt_om)
            assert ("vóór de zomer" in regel) == bool(
                termijn and (vraagt_om or later_om)
            )
            assert " aan " not in regel
            assert len(regel) <= 80

    def test_a_rejected_question_is_the_one_struck_line_it_was(self):
        alles = {
            "vraagt_om": PRODUCT_BRIEF,
            "termijn": "vóór de zomer",
            "later_om": PRODUCT_OVERZICHT,
            "toegezegd": (15,),
        }
        tekst = _thread(status=STATUS_VERWORPEN, **alles)
        assert tekst == _thread(status=STATUS_VERWORPEN)
        assert tekst == (
            "❌ ~~Vraag 12 · Een overzicht van de bezetting per provincie?~~"
            " · geen vraag"
        )

    def test_the_reply_of_any_kind_passes_it_on_for_a_question_only(self):
        gemeen = {
            "volgnummer": 3,
            "gericht_aan": "de minister",
            "citaat": Q_OVERZICHT,
            "samenvatting": "S",
            "stuk": None,
            "moment": MOMENT,
            "moment_url": None,
        }
        erbij = {
            "vraagt_om": PRODUCT_OVERZICHT,
            "termijn": "vóór de zomer",
            "toegezegd": (4,),
            "later_om": PRODUCT_BRIEF,
        }
        als_vraag = format_thread(SOORT_VRAAG, **gemeen, **erbij)
        assert _erbij(als_vraag) == "✉️ een overzicht, vóór de zomer · 🤝 toezegging 4"
        als_toezegging = format_thread(SOORT_TOEZEGGING, **gemeen, **erbij)
        assert "✉️" not in als_toezegging
        assert "toezegging 4" not in als_toezegging
        assert "· vóór de zomer ·" in als_toezegging
        assert len(als_toezegging.split("\n")) == len(als_vraag.split("\n")) - 1


# --- the service, against a database -----------------------------------


async def _judge(db_session, mm, sessie_id, raw, *answers, post_id=None, **extra):
    llm = FakeLLM(*answers)
    post_id = post_id or mm.post(
        "post", f"**{raw['spreker']}** · 10:36\n{raw['tekst'][:60]}"
    )
    result = await DebatVraagService(db_session, mm, llm).beoordeel_beurt(
        _beurt(sessie_id, raw, post_id, **extra), CONTEXT
    )
    return post_id, result


async def _rows(session, sessie_id) -> list[DebatMarkering]:
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


async def _asked(db_session, mm, *citaten: str):
    """A member asks; each quote is an open question, numbered from 1."""
    sessie_id = await status_helpers._sessie(db_session)
    raw = {**VRAAGT, "tekst": "Voorzitter, dank u wel. " + " ".join(citaten)}
    post_id, result = await _judge(
        db_session,
        mm,
        sessie_id,
        raw,
        antwoord(
            *(vraag(c, samenvatting="Overzicht van de bezetting?") for c in citaten)
        ),
    )
    return sessie_id, post_id, result


BELOOFD = "Stuurt de Kamer een overzicht van de bezetting."


async def _granted(db_session, mm, sessie_id, bij_vraag: int = 1):
    """The minister promises what question `bij_vraag` asked for."""
    return await _judge(
        db_session,
        mm,
        sessie_id,
        ANTWOORD,
        toegezegd(toezegging(T_BRIEF, samenvatting=BELOOFD, bij_vraag=bij_vraag)),
    )


class TestOpDeRijEnInDeDraad:
    async def test_what_is_asked_and_by_when_are_stored_on_the_question(
        self, db_session
    ):
        mm = status_helpers.FakeMattermost()
        sessie_id, post_id, result = await _asked(db_session, mm, Q_OVERZICHT, Q_GEWOON)

        assert (result.uitkomst, result.threads) == (UITKOMST_GEMARKEERD, 2)
        request, plain = await _rows(db_session, sessie_id)
        assert (request.soort, request.vraagt_om, request.termijn) == (
            SOORT_VRAAG,
            PRODUCT_OVERZICHT,
            VOOR_DE_BEGROTING,
        )
        assert (plain.soort, plain.vraagt_om, plain.termijn) == (
            SOORT_VRAAG,
            None,
            None,
        )
        tekst = mm.messages[request.thread_post_id]
        assert _meta(tekst).startswith("Vraag 1 · aan de minister · ")
        assert _erbij(tekst) == "✉️ een overzicht, vóór de begrotingsbehandeling"
        assert "✉️" not in mm.messages[plain.thread_post_id]

    async def test_the_status_block_counts_it_as_the_question_it_is(self, db_session):
        mm = status_helpers.FakeMattermost()
        _, post_id, _ = await _asked(db_session, mm, Q_OVERZICHT, Q_GEWOON)
        blok = splits(mm.messages[post_id])[1]
        assert blok.startswith("❓ 2 vragen · ")
        assert "\n" not in blok
        assert "brief" not in blok and "✉️" not in blok

    async def test_a_statement_the_model_hands_in_is_not_marked(self, db_session):
        mm = status_helpers.FakeMattermost()
        sessie_id, _, result = await _asked(db_session, mm, STATEMENTS[3])
        assert await _rows(db_session, sessie_id) == []
        assert result.afgevallen == 1

    async def test_a_reaction_keeps_what_the_reply_said_about_paper(self, db_session):
        h = status_helpers
        mm = h.FakeMattermost()
        mm.usernames[h.PERSOON_A] = "persoon.a"
        sessie_id, _, _ = await _asked(db_session, mm, Q_OVERZICHT)
        (request,) = await _rows(db_session, sessie_id)
        open_tekst = mm.messages[request.thread_post_id]

        await h._reageer(
            db_session, mm, request.thread_post_id, h.PERSOON_A, REACTIE_OPGEPAKT
        )
        await h._ronde(db_session, mm)
        tekst = mm.messages[request.thread_post_id]
        assert _meta(tekst).startswith(
            "Vraag 1 · opgepakt door persoon.a · aan de minister · "
        )
        assert _erbij(tekst) == "✉️ een overzicht, vóór de begrotingsbehandeling"

        await h._haal_weg(
            db_session, mm, request.thread_post_id, h.PERSOON_A, REACTIE_OPGEPAKT
        )
        await h._ronde(db_session, mm)
        assert mm.messages[request.thread_post_id] == open_tekst


class TestOpnieuwGevraagdEnNuOpPapier:
    AGAIN = (
        "Ik heb daar geen antwoord op gekregen. Kan de minister dat overzicht dan"
        " vóór het kerstreces naar de Kamer sturen?"
    )
    PLAIN = "Kan de minister zeggen hoe de bezetting per provincie is?"

    async def _asked_again(self, db_session, mm, first: str, again: str):
        sessie_id, _, _ = await _asked(db_session, mm, first)
        raw = {**VRAAGT, "tekst": f"Voorzitter. {again}"}
        _, result = await _judge(
            db_session,
            mm,
            sessie_id,
            raw,
            antwoord(vraag(again, hoort_bij=1)),
        )
        return sessie_id, result

    async def test_the_reply_says_it_was_asked_later_and_the_row_stays(
        self, db_session
    ):
        h = status_helpers
        mm = h.FakeMattermost()
        sessie_id, result = await self._asked_again(
            db_session, mm, self.PLAIN, self.AGAIN
        )

        assert result.herhaald == (1,)
        (question,) = await _rows(db_session, sessie_id)
        # The quote of the question names no overview: the row says nothing.
        assert (question.vraagt_om, question.termijn) == (None, None)
        assert question.status == STATUS_OPEN
        assert question.reacties_gewijzigd_at is not None
        assert "✉️" not in mm.messages[question.thread_post_id]
        assert await later_op_papier(db_session, question.id) == PaperRequest(
            PRODUCT_OVERZICHT, "vóór het kerstreces"
        )

        await h._ronde(db_session, mm)

        tekst = mm.messages[question.thread_post_id]
        assert _meta(tekst).startswith("Vraag 1 · aan de minister · ")
        assert _erbij(tekst) == ("✉️ later gevraagd: een overzicht, vóór het kerstreces")
        assert f"> {self.PLAIN}" in tekst
        assert (await h._lees(db_session, question.id)).status == STATUS_OPEN

    async def test_what_the_question_asked_for_itself_stays_what_is_shown(
        self, db_session
    ):
        h = status_helpers
        mm = h.FakeMattermost()
        sessie_id, _ = await self._asked_again(
            db_session, mm, Q_OVERZICHT, "Kan de minister daar een brief over sturen?"
        )
        (question,) = await _rows(db_session, sessie_id)
        assert (question.vraagt_om, question.termijn) == (
            PRODUCT_OVERZICHT,
            VOOR_DE_BEGROTING,
        )
        before = mm.messages[question.thread_post_id]
        await h._ronde(db_session, mm)
        assert mm.messages[question.thread_post_id] == before

    async def test_asked_again_without_paper_changes_nothing(self, db_session):
        mm = status_helpers.FakeMattermost()
        sessie_id, result = await self._asked_again(
            db_session, mm, self.PLAIN, "Kan de minister daar alsnog op ingaan?"
        )
        assert result.herhaald == (1,)
        (question,) = await _rows(db_session, sessie_id)
        assert (question.vraagt_om, question.termijn) == (None, None)
        assert question.reacties_gewijzigd_at is None
        assert await later_op_papier(db_session, question.id) is None

    async def test_only_the_question_asked_again_counts_as_asked_later(
        self, db_session
    ):
        # A toezegging that answers the question leaves a vermelding too,
        # with the words of the bewindspersoon: nothing the member asked.
        mm = status_helpers.FakeMattermost()
        sessie_id, _, _ = await _asked(db_session, mm, self.PLAIN)
        (question,) = await _rows(db_session, sessie_id)
        db_session.add(
            DebatMarkeringVermelding(
                markering_id=question.id,
                sessie_id=sessie_id,
                beurt_sleutel="post:x",
                soort=VERMELDING_ANTWOORD,
                spreker="Bewindspersoon A (minister van Voorbeelden)",
                citaat="Kan de Kamer daar een brief over krijgen? Ja, dat zeg ik toe.",
                moment=MOMENT,
            )
        )
        await db_session.commit()
        assert await later_op_papier(db_session, question.id) is None

    async def test_a_question_posted_late_says_what_was_asked_later(self, db_session):
        h = status_helpers
        mm = h.FakeMattermost()
        sessie_id, _ = await self._asked_again(db_session, mm, self.PLAIN, self.AGAIN)
        (question,) = await _rows(db_session, sessie_id)
        await db_session.execute(
            update(DebatMarkering)
            .where(DebatMarkering.id == question.id)
            .values(thread_post_id=None)
        )
        await db_session.commit()

        assert await DebatVraagService(db_session, mm, FakeLLM())._post_thread(
            question.id
        )
        question = await h._lees(db_session, question.id)
        assert _erbij(mm.messages[question.thread_post_id]) == (
            "✉️ later gevraagd: een overzicht, vóór het kerstreces"
        )


class TestEenVerzoekDatWordtToegezegd:
    async def test_the_question_names_the_toezegging_and_stays_open(self, db_session):
        h = status_helpers
        mm = h.FakeMattermost()
        sessie_id, post_id, _ = await _asked(db_session, mm, Q_OVERZICHT)
        blok = splits(mm.messages[post_id])[1]
        await _granted(db_session, mm, sessie_id)

        question, promise = await _rows(db_session, sessie_id)
        assert (promise.soort, promise.bij_volgnummer) == (SOORT_TOEZEGGING, 1)
        assert "· bij vraag 1 · " in mm.messages[promise.thread_post_id]
        # Marked when the reply of the toezegging went into the channel:
        # the reply of the question is to be written again, and nothing
        # else about the question changed.
        assert question.reacties_gewijzigd_at is not None
        assert (question.status, question.status_at) == (STATUS_OPEN, None)
        assert "toezegging 2" not in mm.messages[question.thread_post_id]

        ronde = await h._ronde(db_session, mm)

        assert (ronde.bijgewerkt, ronde.gewijzigd, ronde.mislukt) == (1, 0, 0)
        question = await h._lees(db_session, question.id)
        tekst = mm.messages[question.thread_post_id]
        assert tekst.startswith("❓ **")
        assert _meta(tekst).startswith("Vraag 1 · aan de minister · ")
        assert _erbij(tekst) == (
            "✉️ een overzicht, vóór de begrotingsbehandeling · 🤝 toezegging 2"
        )
        assert (question.status, question.status_at) == (STATUS_OPEN, None)
        assert question.reacties_gewijzigd_at is None
        assert splits(mm.messages[post_id])[1] == blok

    async def test_writing_it_again_gives_the_same_reply(self, db_session):
        h = status_helpers
        mm = h.FakeMattermost()
        sessie_id, _, _ = await _asked(db_session, mm, Q_OVERZICHT)
        await _granted(db_session, mm, sessie_id)
        await h._ronde(db_session, mm)
        question, _ = await _rows(db_session, sessie_id)
        first = mm.messages[question.thread_post_id]

        # A second writer of the same post: a reaction that comes and goes.
        await h._reageer(
            db_session, mm, question.thread_post_id, h.PERSOON_A, REACTIE_OPGEPAKT
        )
        await h._ronde(db_session, mm)
        assert "🤝 toezegging 2" in mm.messages[question.thread_post_id]
        await h._haal_weg(
            db_session, mm, question.thread_post_id, h.PERSOON_A, REACTIE_OPGEPAKT
        )
        await h._ronde(db_session, mm)

        assert mm.messages[question.thread_post_id] == first

    async def test_a_reaction_and_a_toezegging_in_one_round_both_show(self, db_session):
        h = status_helpers
        mm = h.FakeMattermost()
        mm.usernames[h.PERSOON_A] = "persoon.a"
        sessie_id, _, _ = await _asked(db_session, mm, Q_OVERZICHT)
        (question,) = await _rows(db_session, sessie_id)
        await h._reageer(
            db_session, mm, question.thread_post_id, h.PERSOON_A, REACTIE_OPGEPAKT
        )
        await _granted(db_session, mm, sessie_id)

        await h._ronde(db_session, mm)

        tekst = mm.messages[question.thread_post_id]
        assert _meta(tekst).startswith(
            "Vraag 1 · opgepakt door persoon.a · aan de minister · "
        )
        assert _erbij(tekst) == (
            "✉️ een overzicht, vóór de begrotingsbehandeling · 🤝 toezegging 2"
        )
        # The status is the one of the reaction, not of the toezegging.
        assert (await h._lees(db_session, question.id)).status == STATUS_TOEGEWEZEN

    async def test_a_plain_question_names_its_toezegging_too(self, db_session):
        h = status_helpers
        mm = h.FakeMattermost()
        plain = (
            "Weet de minister bij de begrotingsbehandeling hoe de bezetting per"
            " provincie is?"
        )
        sessie_id, _, _ = await _asked(db_session, mm, plain)
        await _granted(db_session, mm, sessie_id)
        await h._ronde(db_session, mm)

        question, promise = await _rows(db_session, sessie_id)
        assert promise.bij_volgnummer == 1
        assert _erbij(mm.messages[question.thread_post_id]) == "🤝 toezegging 2"

    async def test_a_second_toezegging_in_a_later_window_is_named_as_well(
        self, db_session
    ):
        """A long answer is stored window by window. The second window's
        toezegging on the same question leaves no second vermelding, and
        still has to reach the reply of the question."""
        h = status_helpers
        mm = h.FakeMattermost()
        sessie_id, _, _ = await _asked(db_session, mm, Q_OVERZICHT)
        ook = (
            "Ik stuur de Kamer in het voorjaar ook een overzicht van de bezetting"
            " per provincie."
        )
        tekst = (
            f"Dan de bezetting per provincie. {T_BRIEF} {vul(70)}{ook} {vul(30)}"
        ).strip()
        raw = {**ANTWOORD, "tekst": tekst}
        assert next_window(tekst, next_window(tekst, 0)[2]) is not None

        post_id, first = await _judge(
            db_session,
            mm,
            sessie_id,
            raw,
            toegezegd(toezegging(T_BRIEF, samenvatting=BELOOFD, bij_vraag=1)),
        )
        assert first.meer
        await h._ronde(db_session, mm)
        question = (await _rows(db_session, sessie_id))[0]
        assert _erbij(mm.messages[question.thread_post_id]).endswith("🤝 toezegging 2")
        assert question.reacties_gewijzigd_at is None

        _, second = await _judge(
            db_session,
            mm,
            sessie_id,
            raw,
            toegezegd(
                toezegging(
                    ook,
                    samenvatting="Stuurt een overzicht van de bezetting per provincie.",
                    bij_vraag=1,
                )
            ),
            post_id=post_id,
            gelezen_tot=first.gelezen_tot,
        )

        assert second.toezeggingen == 1
        question, een, twee = await _rows(db_session, sessie_id)
        assert (een.bij_volgnummer, twee.bij_volgnummer) == (1, 1)
        assert "· bij vraag 1 · " in mm.messages[twee.thread_post_id]
        assert question.reacties_gewijzigd_at is not None
        await h._ronde(db_session, mm)
        assert _erbij(mm.messages[question.thread_post_id]) == (
            "✉️ een overzicht, vóór de begrotingsbehandeling · 🤝 toezegging 2, 3"
        )

    async def test_a_toezegging_that_is_rejected_is_no_longer_named(self, db_session):
        h = status_helpers
        mm = h.FakeMattermost()
        sessie_id, _, _ = await _asked(db_session, mm, Q_OVERZICHT)
        await _granted(db_session, mm, sessie_id)
        await h._ronde(db_session, mm)
        question, promise = await _rows(db_session, sessie_id)
        with_it = mm.messages[question.thread_post_id]
        assert "🤝 toezegging 2" in with_it

        await h._reageer(
            db_session, mm, promise.thread_post_id, h.PERSOON_A, REACTIE_GEEN_VRAAG
        )
        # The round that rejects the toezegging marks its question; the
        # next one writes the reply of the question.
        await h._ronde(db_session, mm)
        assert (await h._lees(db_session, promise.id)).status == STATUS_VERWORPEN
        assert await toezeggingen_bij(db_session, sessie_id, 1) == ()
        await h._ronde(db_session, mm)
        assert "toezegging 2" not in mm.messages[question.thread_post_id]
        assert "✉️ een overzicht" in mm.messages[question.thread_post_id]

        # Taken back in: named again.
        await h._haal_weg(
            db_session, mm, promise.thread_post_id, h.PERSOON_A, REACTIE_GEEN_VRAAG
        )
        await h._ronde(db_session, mm)
        await h._ronde(db_session, mm)
        assert mm.messages[question.thread_post_id] == with_it
        assert (await h._lees(db_session, question.id)).status == STATUS_OPEN

    async def test_another_reaction_on_the_toezegging_leaves_the_question_alone(
        self, db_session
    ):
        h = status_helpers
        mm = h.FakeMattermost()
        sessie_id, _, _ = await _asked(db_session, mm, Q_OVERZICHT)
        await _granted(db_session, mm, sessie_id)
        await h._ronde(db_session, mm)
        question, promise = await _rows(db_session, sessie_id)

        await h._reageer(
            db_session, mm, promise.thread_post_id, h.PERSOON_A, REACTIE_OPGEPAKT
        )
        await h._ronde(db_session, mm)

        assert (await h._lees(db_session, question.id)).reacties_gewijzigd_at is None

    async def test_a_toezegging_whose_reply_is_not_in_the_channel_is_not_named(
        self, db_session
    ):
        h = status_helpers
        mm = h.FakeMattermost()
        sessie_id, _, _ = await _asked(db_session, mm, Q_OVERZICHT)
        (question,) = await _rows(db_session, sessie_id)
        promise = await h._markering(
            db_session,
            mm,
            sessie_id,
            2,
            soort=SOORT_TOEZEGGING,
            spreker="Bewindspersoon A (minister van Voorbeelden)",
            citaat=T_BRIEF,
            bij_volgnummer=1,
            thread_post_id=None,
        )
        assert await toezeggingen_bij(db_session, sessie_id, 1) == ()
        # Stored, not posted: nothing tells the question yet.
        assert (await h._lees(db_session, question.id)).reacties_gewijzigd_at is None

        # Its reply gets into the channel after all: now the question is
        # told, and names it.
        assert await DebatVraagService(db_session, mm, FakeLLM())._post_thread(
            promise.id
        )
        assert await toezeggingen_bij(db_session, sessie_id, 1) == (2,)
        assert (
            await h._lees(db_session, question.id)
        ).reacties_gewijzigd_at is not None
        await h._ronde(db_session, mm)
        assert _erbij(mm.messages[question.thread_post_id]).endswith("🤝 toezegging 2")

    async def test_a_reply_that_fails_to_post_tells_the_question_nothing(
        self, db_session
    ):
        h = status_helpers
        mm = h.FakeMattermost()
        sessie_id, _, _ = await _asked(db_session, mm, Q_OVERZICHT)
        (question,) = await _rows(db_session, sessie_id)
        promise = await h._markering(
            db_session,
            mm,
            sessie_id,
            2,
            soort=SOORT_TOEZEGGING,
            citaat=T_BRIEF,
            bij_volgnummer=1,
            thread_post_id=None,
        )

        async def fails(*args, **kwargs):
            return None

        mm.send_channel_message = fails
        assert not await DebatVraagService(db_session, mm, FakeLLM())._post_thread(
            promise.id
        )
        assert (await h._lees(db_session, question.id)).reacties_gewijzigd_at is None

    async def test_a_question_that_is_posted_late_names_it_at_once(self, db_session):
        h = status_helpers
        mm = h.FakeMattermost()
        sessie_id = await h._sessie(db_session)
        beurt_post_id = mm.post("post", h.TURN)
        question = await h._markering(
            db_session,
            mm,
            sessie_id,
            1,
            beurt_post_id=beurt_post_id,
            citaat=Q_OVERZICHT,
            vraagt_om=PRODUCT_OVERZICHT,
            termijn=VOOR_DE_BEGROTING,
            thread_post_id=None,
        )
        await h._markering(
            db_session,
            mm,
            sessie_id,
            2,
            soort=SOORT_TOEZEGGING,
            spreker="Bewindspersoon A (minister van Voorbeelden)",
            citaat=T_BRIEF,
            bij_volgnummer=1,
        )

        service = DebatVraagService(db_session, mm, FakeLLM())
        assert await service._post_thread(question.id)

        question = await h._lees(db_session, question.id)
        assert _erbij(mm.messages[question.thread_post_id]) == (
            "✉️ een overzicht, vóór de begrotingsbehandeling · 🤝 toezegging 2"
        )

    async def test_only_toezeggingen_of_the_same_debate_count(self, db_session):
        h = status_helpers
        mm = h.FakeMattermost()
        sessie_id, _, _ = await _asked(db_session, mm, Q_OVERZICHT)
        other = await h._sessie(db_session)
        await h._markering(
            db_session,
            mm,
            other,
            5,
            soort=SOORT_TOEZEGGING,
            citaat=T_BRIEF,
            bij_volgnummer=1,
        )
        # A question that points at number 1 is no toezegging on it.
        await h._markering(db_session, mm, sessie_id, 7, bij_volgnummer=1)

        assert await toezeggingen_bij(db_session, sessie_id, 1) == ()
        assert await toezeggingen_bij(db_session, other, 1) == (5,)

    async def test_a_toezegging_of_another_debate_tells_no_question_here(
        self, db_session
    ):
        h = status_helpers
        mm = h.FakeMattermost()
        sessie_id, _, _ = await _asked(db_session, mm, Q_OVERZICHT)
        (question,) = await _rows(db_session, sessie_id)
        other = await h._sessie(db_session)
        elsewhere = await h._markering(
            db_session,
            mm,
            other,
            5,
            soort=SOORT_TOEZEGGING,
            citaat=T_BRIEF,
            bij_volgnummer=1,
            thread_post_id=None,
        )
        assert await DebatVraagService(db_session, mm, FakeLLM())._post_thread(
            elsewhere.id
        )
        assert (await h._lees(db_session, question.id)).reacties_gewijzigd_at is None
