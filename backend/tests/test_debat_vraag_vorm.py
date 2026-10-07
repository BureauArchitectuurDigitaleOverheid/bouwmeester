"""The form of a question, checked in code.

Every sentence in here is made up. The made-up debate in
`fixtures/debat_markeringen_synthetisch.json` is the one place where the
rule meets a whole codebook of hard negatives.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bouwmeester.services.debat_vraag_vorm import has_question_form, words

FIXTURE = json.loads(
    (
        Path(__file__).parent / "fixtures" / "debat_markeringen_synthetisch.json"
    ).read_text(encoding="utf-8")
)


class TestAQuestion:
    @pytest.mark.parametrize(
        "quote",
        [
            # A question mark is enough.
            "En dan de stallingen bij kleine stations?",
            # The verb first and then who is asked. No question mark: the
            # transcript writes a full stop there as often as not.
            "Kan de minister dat toelichten.",
            "Wil de staatssecretaris daar een overzicht van maken.",
            "Is het kabinet bereid om dat te onderzoeken",
            "Deelt de minister die zorg",
            "Gaat de regering daar geld voor vrijmaken.",
            "Erkent hij dat het plan vertraging heeft opgelopen",
            # A verb a question opens with, and nobody named behind it.
            "Klopt het dat het budget volgend jaar met 12 miljoen wordt verlaagd.",
            "Worden die termijnen daadwerkelijk gehaald.",
            "Is er zicht op hoeveel stallingen leegstaan",
            # A question word and then its verb.
            "Hoe gaat de minister dat betalen.",
            "Waarom duurt het zo lang",
            "Wanneer komt de evaluatie naar de Kamer.",
            "Welke stappen zet het kabinet daarvoor",
            "Wat voor maatregelen neemt de minister tegen diefstal",
            "Hoeveel stations hebben nu een bewaakte stalling.",
            # Behind a lead-in, a subtitle line that runs on, or a statement.
            "Voorzitter, en waarom is daar niet eerder over bericht",
            "Dat is een stap vooruit... maar wanneer horen wij daar meer over",
            "Het loket is er nog niet. Kan de minister zeggen wanneer het opengaat.",
            "Dan een vraag aan de minister: wil hij dat toezeggen",
            # A question word halfway a clause, with the verb and who is asked.
            "en dan vraag twee hoe ziet de minister de rol van de gemeenten",
            # An explicit request.
            "Ik vraag de minister om daar een brief over te sturen.",
            "Ik verzoek het kabinet daarop terug te komen.",
            "Mijn vraag aan de minister is wat hij daaraan gaat doen",
            "Graag een reactie van de minister.",
            "Graag hoor ik hoe de staatssecretaris dat ziet.",
            "Ik hoor graag van de minister of hij die cijfers heeft.",
            "Ik ben benieuwd hoe de minister daartegen aankijkt.",
            "Kan de minister toezeggen dat de Kamer dat overzicht krijgt",
            "Daar zou ik de minister graag over horen.",
            # The first word of the sentence lost: the request is still in it.
            "de minister dat nader toelichten",
            "minister het met mij eens dat dit sneller moet",
        ],
    )
    def test_a_question_or_request_has_the_form(self, quote):
        assert has_question_form(quote)

    def test_a_missing_question_mark_does_not_drop_a_question(self):
        """The same question with and without the mark, and in capitals or not."""
        for quote in (
            "Kan de minister zeggen wanneer de telling klaar is?",
            "Kan de minister zeggen wanneer de telling klaar is.",
            "kan de minister zeggen wanneer de telling klaar is",
            "Kan de minister... zeggen wanneer de telling... klaar is",
        ):
            assert has_question_form(quote), quote

    def test_accents_and_case_do_not_matter(self):
        assert words("Vóór de zomer, één brief!") == [
            "voor",
            "de",
            "zomer",
            "een",
            "brief",
        ]
        assert has_question_form("HOE GAAT DE MINISTER DAT BETALEN")


class TestWithoutAQuestionMark:
    """Forms a first version of the check dropped when the mark was missing."""

    @pytest.mark.parametrize(
        "quote",
        [
            # A preposition in front of the question word.
            "op welke termijn kunnen wij dat verwachten",
            "per wanneer gaat dat in",
            "met welke partijen heeft de minister gesproken",
            # Indirect.
            "ik wil weten of de minister bereid is",
            "ik wil de minister vragen of hij dat herkent",
            "ik zou de minister willen vragen om daarop in te gaan",
            "daar wil ik een reactie op",
            "een reactie van de minister graag",
            "daar hoor ik de minister graag over",
            # A request.
            "ik roep de minister op om met een plan te komen",
            "ik wil een toezegging van de minister",
            # A condition first, and no comma where the question begins.
            "als dat zo is trekt de minister het voorstel dan in",
            # Who is spoken to first.
            "minister wanneer komt die brief",
            "voorzitter staatssecretaris hoe gaat dat verder",
            # A verb and a subject that is nobody at the table.
            "krijgen de gemeenten daar geld voor",
            "betekent dit dat de regeling stopt",
            "misschien kan de minister daar iets over zeggen",
            # The start of the question cut off by the model.
            "Met mij eens dat dit sneller moet.",
        ],
    )
    def test_these_are_questions(self, quote):
        assert has_question_form(quote)

    @pytest.mark.parametrize(
        "quote",
        [
            # Behind a comma the verb comes first in a statement too.
            "Omdat het kabinet niets deed, zitten de gemeenten nu met de kosten.",
            "Toen dat bleek, kregen de gemeenten de rekening.",
            # A condition and then a conclusion or a call, not a question.
            "Als de minister dat doet zijn wij tevreden.",
            "Als dat zo is moet de minister het voorstel intrekken.",
            # Words that end like a verb in front of "de".
            "Tussen de regels door lees ik twijfel.",
            "Niet de minister maar de Kamer beslist.",
            "Binnen het kabinet is daar geen steun voor.",
            # A dictum is not a question to the cabinet.
            "verzoekt de regering om een plan te maken",
            "De motie verzoekt de regering om een plan te maken.",
            # The reaction of someone, as a fact.
            "De reactie van het kabinet was teleurstellend.",
        ],
    )
    def test_these_are_still_statements(self, quote):
        assert not has_question_form(quote)


class TestAStatement:
    @pytest.mark.parametrize(
        "quote",
        [
            # What the model makes a question of.
            "Niemand kan mij vertellen waar de 30 miljoen aan is uitgegeven.",
            "Dat heeft het kabinet ons nooit uitgelegd.",
            "Het is mij niet duidelijk waar dat bedrag op is gebaseerd.",
            "De grote vraag is of een landelijke norm wel uitvoerbaar is.",
            # About the cabinet, not to it.
            "Het kabinet kiest hier niet voor.",
            "De minister was daar in zijn brief zuinig over.",
            "Volgens het kabinet is er geen geld voor.",
            "Misschien kunnen wij de minister er nog van overtuigen.",
            # A call without a question.
            "Het kabinet moet ophouden met wijzen naar anderen.",
            "Ik hoop dat de minister dat serieus neemt.",
            # A question of earlier, retold.
            "In het voorjaar heb ik de minister gevraagd of hij dat wilde onderzoeken",
            # A question word with the verb at the end is part of a statement.
            "Ik weet niet hoe de minister dat voor zich ziet.",
            "Wat de fractie betreft gaat dit plan niet door.",
            "Wat voor ons telt is dat de stalling open blijft.",
            "Hoe wij daarnaar kijken heb ik net gezegd.",
            "Hoe meer stallingen er komen, hoe minder fietsen er op straat staan.",
            "Waarom dit zo lang duurt weet niemand.",
            # A clause that opens with something that is not a verb.
            "Als de minister dat doet zijn wij tevreden.",
            "Omdat het kabinet niets deed, zitten de gemeenten nu met de kosten.",
        ],
    )
    def test_a_statement_has_no_question_form(self, quote):
        assert not has_question_form(quote)

    @pytest.mark.parametrize("quote", ["", "...", "Dank u wel, voorzitter."])
    def test_nothing_to_ask_with(self, quote):
        assert not has_question_form(quote)

    def test_a_relative_clause_is_not_a_question(self):
        assert not has_question_form(
            "Er ligt een wet, waardoor gemeenten zelf mogen handhaven."
        )
        # With the verb and who is asked behind it, it is.
        assert has_question_form("En waarmee gaat de minister dat betalen")


class TestOnTheMadeUpDebate:
    def test_every_question_of_the_fixture_has_the_form(self):
        questions = [i for i in FIXTURE["items"] if i["soort"] == "vraag"]
        assert len(questions) >= 10
        assert [
            q["citaat"] for q in questions if not has_question_form(q["citaat"])
        ] == []

    def test_the_statements_of_the_fixture_are_stopped(self):
        """All of them: the kinds of sentence the check was made for."""
        for kind in ("stelling", "over_kabinet", "oproep"):
            quotes = [n["citaat"] for n in FIXTURE["negatieven"] if n["type"] == kind]
            assert quotes, kind
            assert [q for q in quotes if has_question_form(q)] == [], kind

    def test_what_has_the_form_of_a_question_is_left_to_the_model(self):
        """A rhetorical question and one to a colleague are questions in form."""
        for kind in ("retorisch", "aan_kamerlid", "aan_initiatiefnemers"):
            quotes = [n["citaat"] for n in FIXTURE["negatieven"] if n["type"] == kind]
            assert any(has_question_form(q) for q in quotes), kind
