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

import pytest
from sqlalchemy import select

from bouwmeester.models.debat_markering import (
    SOORT_TOEZEGGING,
    SOORT_VRAAG,
    STATUS_OPEN,
    STATUS_TOEGEWEZEN,
    STATUS_VERWORPEN,
    DebatMarkering,
)
from bouwmeester.services.debat_statusregel import splits
from bouwmeester.services.debat_vraag_brief import (
    MAX_MOMENT,
    PRODUCT_BERICHT,
    PRODUCT_BRIEF,
    PRODUCT_EVALUATIE,
    PRODUCT_INFORMATIE,
    PRODUCT_NOTITIE,
    PRODUCT_OVERZICHT,
    PRODUCT_PLAN,
    PRODUCT_RAPPORTAGE,
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
    MAX_TERMIJN,
    MAX_TOEGEZEGD,
    UITKOMST_GEMARKEERD,
    DebatVraagService,
    _Herhaling,
    format_thread,
    format_vraag_thread,
    lees_antwoord,
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
)
from tests.test_debat_vragen import FakeLLM, antwoord, vraag

MOMENT = status_helpers.MOMENT

# --- the rule ----------------------------------------------------------


class TestWatOpPapierWordtGevraagd:
    @pytest.mark.parametrize(
        ("citaat", "product", "moment"),
        [
            # A form of answering, whatever is asked.
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
                "voor het commissiedebat",
            ),
            # A product that is paper by its name, and asked for.
            (
                "Wil de staatssecretaris een overzicht van de kosten naar de Kamer"
                " sturen?",
                PRODUCT_OVERZICHT,
                None,
            ),
            (
                "Ik zou graag vóór de begrotingsbehandeling een brief van de"
                " minister ontvangen.",
                PRODUCT_BRIEF,
                "voor de begrotingsbehandeling",
            ),
            (
                "Wij verwachten deze maand nog een briefje waarin staat hoeveel"
                " stallingen er zijn.",
                PRODUCT_BRIEF,
                None,
            ),
            (
                "Dat mag wat mij betreft in een volgende brief, als de minister"
                " er dan uitgebreider op terugkomt.",
                PRODUCT_BRIEF,
                None,
            ),
            (
                "Kan de minister toezeggen dat hij de Kamer vóór het kerstreces"
                " een overzicht stuurt van de kosten per station?",
                PRODUCT_OVERZICHT,
                "voor het kerstreces",
            ),
            (
                "Krijgen wij daar elk jaar een rapportage over?",
                PRODUCT_RAPPORTAGE,
                None,
            ),
            (
                "Kan het kabinet daar een notitie over sturen?",
                PRODUCT_NOTITIE,
                None,
            ),
            # Asked for by a moment: not something that is said on the spot.
            (
                "Kan de minister vóór de begrotingsbehandeling een overzicht"
                " geven van de bezetting per provincie?",
                PRODUCT_OVERZICHT,
                "voor de begrotingsbehandeling",
            ),
            # A plan, an evaluatie or a tijdpad on its way to the Kamer.
            (
                "Kan de minister het plan vóór 1 maart naar de Kamer sturen?",
                PRODUCT_PLAN,
                "voor 1 maart",
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

    @pytest.mark.parametrize(
        "citaat",
        [
            # An answer on the spot.
            "Kan de minister daar iets over zeggen?",
            "Graag een reactie van de minister.",
            "Wat gaat dat kosten?",
            # "Informeren" without a moment or a form.
            "Kan de minister de Kamer daarover informeren?",
            # A moment that is what the letter is to be about, not a deadline.
            "Hoeveel brieven heeft de minister voor de zomer nog gekregen?",
            "Kan de minister ons informeren over wat er dit jaar is gebeurd?",
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
            "Wij krijgen de laatste rapportage steeds te laat. Hoe komt dat?",
            "Die notitie noemt geen bedrag. Stuurt de minister ons nog een aanvulling?",
            # Informing someone else than the Kamer, and receiving an answer.
            "Wil de minister de gemeenten vóór de zomer informeren over de regeling?",
            "Wij ontvangen graag een reactie van de minister.",
            # A member announcing something of their own.
            "Ik zal zelf een brief sturen aan de vervoerders. Wat vindt de"
            " minister daarvan?",
            "Wij komen daarover met een eigen notitie. Kan de minister wachten?",
            # When something comes is answered with a date.
            "Wanneer komt de evaluatie naar de Kamer?",
            "Wanneer kunnen wij de brief verwachten?",
            # Policy, not paper.
            "Komt de minister met een plan voor de kleine stations?",
            "Is de minister bereid de proef te laten evalueren?",
            "Hoe kijkt de minister aan tegen de planning van de vervoerders?",
            # The procedure, and what was done in writing before.
            "In het schriftelijk overleg heeft de minister dit ontkend. Klopt dat?",
            "De minister heeft schriftelijk laten weten dat het geld op is. Hoe"
            " kan dat?",
            # Rules that only work on paper.
            "Bestaat dat toezicht ook buiten wat er op papier staat?",
            "",
        ],
    )
    def test_what_asks_for_nothing_on_paper(self, citaat):
        assert paper_request(citaat) is None

    def test_a_request_to_the_minister_is_not_the_members_own(self):
        assert paper_request(
            "Ik ga de minister om een brief vragen, graag vóór de zomer."
        ) == PaperRequest(PRODUCT_BRIEF, "voor de zomer")
        assert paper_request("Ik ga zelf om een brief vragen, graag snel.") is None

    def test_the_moment_is_the_one_near_what_is_asked(self):
        # When something happened, far in front of the letter.
        found = paper_request(
            "Vóór de zomer zijn de regels veranderd en de gemeenten weten nog"
            " steeds niet waar zij aan toe zijn, dat hoor ik overal. Kan de"
            " minister daar een brief over sturen?"
        )
        assert found == PaperRequest(PRODUCT_BRIEF, None)

    def test_what_the_letter_is_about_is_not_by_when(self):
        found = paper_request(
            "Kan de minister de Kamer schriftelijk laten weten hoeveel beugels er"
            " voor het kerstreces zijn bijgekomen?"
        )
        assert found == PaperRequest(PRODUCT_SCHRIFTELIJK, None)

    def test_of_two_moments_the_nearest_is_taken(self):
        found = paper_request(
            "Kan de minister, liefst vóór het kerstreces en anders uiterlijk vóór"
            " de zomer, een brief sturen?"
        )
        assert found == PaperRequest(PRODUCT_BRIEF, "uiterlijk voor de zomer")

    def test_the_moment_is_in_the_words_of_the_transcript_without_marks(self):
        found = paper_request("Graag een brief, uiterlijk vóór   het Zomerreces!")
        assert found == PaperRequest(PRODUCT_BRIEF, "uiterlijk voor het zomerreces")

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

    def test_what_a_member_does_themselves_is_no_request(self):
        (own,) = [n for n in SYN["negatieven"] if n["type"] == "eigen_brief"]
        assert paper_request(own["citaat"]) is None


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
            (PRODUCT_OVERZICHT, "voor de begrotingsbehandeling"),
            (None, None),
        ]
        # A question still: the property makes no kind of its own.
        assert {n.soort for n in nieuw} == {SOORT_VRAAG}

    def test_a_question_about_a_letter_that_exists_asks_for_none(self):
        (een,), _, _ = lees_antwoord([_vraag(Q_BESTAAND)], Q_BESTAAND, [], set())
        assert (een.vraagt_om, een.termijn) == (None, None)

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

    def test_a_question_asked_again_carries_what_it_asks_for_now(self):
        _, (again,), _ = lees_antwoord(
            [_vraag(Q_OVERZICHT, hoort_bij=4)], Q_OVERZICHT, [], {4}
        )
        assert (again.volgnummer, again.vraagt_om, again.termijn) == (
            4,
            PRODUCT_OVERZICHT,
            "voor de begrotingsbehandeling",
        )
        _, (plain,), _ = lees_antwoord(
            [_vraag(Q_GEWOON, hoort_bij=4)], Q_GEWOON, [], {4}
        )
        assert (plain.vraagt_om, plain.termijn) == (None, None)

    def test_a_statement_about_a_letter_is_still_dropped(self):
        citaat = "In de brief van vorige week staat dat de proef is verlengd."
        assert lees_antwoord([_vraag(citaat)], citaat, [], set()) == ([], [], 1)

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


class TestDeRegelOnderDeVraag:
    def test_a_plain_question_reads_as_it_did(self):
        assert _meta(_thread()) == "Vraag 12 · aan de minister · 10:02"
        assert _thread() == _thread(vraagt_om=None, termijn=None, toegezegd=())

    def test_what_is_asked_on_paper_stands_in_the_line_that_is_there(self):
        zonder = _thread()
        met = _thread(vraagt_om=PRODUCT_BRIEF)
        assert _meta(met) == "Vraag 12 · ✉️ een brief · aan de minister · 10:02"
        # No line more than a plain question has.
        assert len(met.split("\n")) == len(zonder.split("\n"))
        assert [r for i, r in enumerate(met.split("\n")) if i != 1] == [
            r for i, r in enumerate(zonder.split("\n")) if i != 1
        ]

    def test_the_moment_follows_what_is_asked(self):
        assert _meta(
            _thread(vraagt_om=PRODUCT_BRIEF, termijn="voor de begrotingsbehandeling")
        ) == (
            "Vraag 12 · ✉️ een brief voor de begrotingsbehandeling · aan de"
            " minister · 10:02"
        )

    def test_a_moment_without_a_request_is_not_shown(self):
        assert _meta(_thread(termijn="voor de zomer")) == _meta(_thread())

    def test_only_a_product_the_code_knows_is_shown(self):
        tekst = _thread(vraagt_om="@all **een brief**", termijn="voor de zomer")
        assert _meta(tekst) == _meta(_thread())

    def test_the_moment_is_escaped_and_capped(self):
        gevaarlijk = "voor de zomer @channel **vet** [x](http://voorbeeld.example)"
        meta = _meta(_thread(vraagt_om=PRODUCT_BRIEF, termijn=gevaarlijk))
        assert "@" not in meta
        assert "**" not in meta.replace("\\*\\*", "")
        assert "://" not in meta
        lang = _meta(_thread(vraagt_om=PRODUCT_BRIEF, termijn="voor " + "a" * 500))
        assert len(lang) < len("Vraag 12 · ✉️ een brief · aan de minister · 10:02") + (
            MAX_TERMIJN + 2
        )

    def test_a_moment_cannot_add_a_line(self):
        tekst = _thread(vraagt_om=PRODUCT_BRIEF, termijn="voor de zomer\n> nep citaat")
        assert len(tekst.split("\n")) == len(_thread().split("\n"))

    def test_where_it_stands_comes_first(self):
        meta = _meta(
            _thread(
                vraagt_om=PRODUCT_OVERZICHT, status=STATUS_TOEGEWEZEN, door="persoon.a"
            )
        )
        assert meta == (
            "Vraag 12 · opgepakt door persoon.a · ✉️ een overzicht · aan de"
            " minister · 10:02"
        )

    def test_a_toezegging_that_followed_is_named_by_its_number(self):
        meta = _meta(_thread(vraagt_om=PRODUCT_BRIEF, toegezegd=(15,)))
        assert meta == (
            "Vraag 12 · ✉️ een brief · 🤝 toezegging 15 · aan de minister · 10:02"
        )
        # Also on a question that asked for nothing on paper.
        assert _meta(_thread(toegezegd=(15,))) == (
            "Vraag 12 · 🤝 toezegging 15 · aan de minister · 10:02"
        )

    def test_more_toezeggingen_are_named_up_to_a_few(self):
        meta = _meta(_thread(toegezegd=(15, 17, 21, 30, 31)))
        assert "🤝 toezegging 15, 17, 21 ·" in meta
        assert len(meta.split(", ")) == MAX_TOEGEZEGD

    def test_a_rejected_question_stays_one_struck_line(self):
        tekst = _thread(
            vraagt_om=PRODUCT_BRIEF, toegezegd=(15,), status=STATUS_VERWORPEN
        )
        assert "\n" not in tekst
        assert "✉️" not in tekst
        assert "toezegging" not in tekst

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
        als_vraag = format_thread(
            SOORT_VRAAG,
            **gemeen,
            vraagt_om=PRODUCT_OVERZICHT,
            termijn="voor de begrotingsbehandeling",
            toegezegd=(4,),
        )
        assert (
            "Vraag 3 · ✉️ een overzicht voor de begrotingsbehandeling · 🤝"
            " toezegging 4 · aan de minister · " in als_vraag
        )
        als_toezegging = format_thread(
            SOORT_TOEZEGGING,
            **gemeen,
            vraagt_om=PRODUCT_OVERZICHT,
            termijn="voor de zomer",
            toegezegd=(4,),
        )
        assert "✉️" not in als_toezegging
        assert "toezegging 4" not in als_toezegging
        assert "· voor de zomer ·" in als_toezegging


# --- the service, against a database -----------------------------------


async def _judge(db_session, mm, sessie_id, raw, *answers, **extra):
    llm = FakeLLM(*answers)
    post_id = mm.post("post", f"**{raw['spreker']}** · 10:36\n{raw['tekst'][:60]}")
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


async def _granted(db_session, mm, sessie_id, bij_vraag: int = 1):
    """The minister promises what question `bij_vraag` asked for."""
    return await _judge(
        db_session,
        mm,
        sessie_id,
        ANTWOORD,
        toegezegd(
            toezegging(
                T_BRIEF,
                samenvatting="Stuurt de Kamer een overzicht van de bezetting.",
                bij_vraag=bij_vraag,
            )
        ),
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
            "voor de begrotingsbehandeling",
        )
        assert (plain.soort, plain.vraagt_om, plain.termijn) == (
            SOORT_VRAAG,
            None,
            None,
        )
        assert _meta(mm.messages[request.thread_post_id]).startswith(
            "Vraag 1 · ✉️ een overzicht voor de begrotingsbehandeling · aan de"
            " minister · "
        )
        assert "✉️" not in mm.messages[plain.thread_post_id]

    async def test_the_status_block_counts_it_as_the_question_it_is(self, db_session):
        mm = status_helpers.FakeMattermost()
        _, post_id, _ = await _asked(db_session, mm, Q_OVERZICHT, Q_GEWOON)
        assert splits(mm.messages[post_id])[1] == "❓ 2 vragen · open"

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
        assert _meta(mm.messages[request.thread_post_id]).startswith(
            "Vraag 1 · opgepakt door persoon.a · ✉️ een overzicht voor de"
            " begrotingsbehandeling · aan de minister · "
        )

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

    async def test_the_question_asks_for_it_from_then_on(self, db_session):
        h = status_helpers
        mm = h.FakeMattermost()
        plain = "Kan de minister zeggen hoe de bezetting per provincie is?"
        sessie_id, result = await self._asked_again(db_session, mm, plain, self.AGAIN)

        assert result.herhaald == (1,)
        (question,) = await _rows(db_session, sessie_id)
        assert (question.vraagt_om, question.termijn) == (
            PRODUCT_OVERZICHT,
            "voor het kerstreces",
        )
        assert question.status == STATUS_OPEN
        assert "✉️" not in mm.messages[question.thread_post_id]

        await h._ronde(db_session, mm)
        assert _meta(mm.messages[question.thread_post_id]).startswith(
            "Vraag 1 · ✉️ een overzicht voor het kerstreces · aan de minister · "
        )

    async def test_what_it_asked_for_first_stays(self, db_session):
        mm = status_helpers.FakeMattermost()
        sessie_id, _ = await self._asked_again(
            db_session, mm, Q_OVERZICHT, "Kan de minister daar een brief over sturen?"
        )
        (question,) = await _rows(db_session, sessie_id)
        assert (question.vraagt_om, question.termijn) == (
            PRODUCT_OVERZICHT,
            "voor de begrotingsbehandeling",
        )
        assert question.reacties_gewijzigd_at is None

    async def test_asked_again_without_paper_changes_nothing(self, db_session):
        mm = status_helpers.FakeMattermost()
        plain = "Kan de minister zeggen hoe de bezetting per provincie is?"
        sessie_id, result = await self._asked_again(
            db_session, mm, plain, "Kan de minister daar alsnog op ingaan?"
        )
        assert result.herhaald == (1,)
        (question,) = await _rows(db_session, sessie_id)
        assert (question.vraagt_om, question.termijn) == (None, None)
        assert question.reacties_gewijzigd_at is None

    async def test_a_toezegging_keeps_its_own_moment(self, db_session):
        # The same column holds by when a toezegging was promised; a
        # question asked again never writes there.
        h = status_helpers
        mm = h.FakeMattermost()
        sessie_id = await h._sessie(db_session)
        promise = await h._markering(
            db_session,
            mm,
            sessie_id,
            1,
            soort=SOORT_TOEZEGGING,
            citaat=T_BRIEF,
            termijn="in mei",
        )
        service = DebatVraagService(db_session, mm, FakeLLM())
        beurt = _beurt(sessie_id, VRAAGT, mm.post("post", h.TURN))
        await service._leg_vast(
            beurt,
            [],
            [
                _Herhaling(
                    1, self.AGAIN, termijn="voor de zomer", vraagt_om=PRODUCT_BRIEF
                )
            ],
            {1: promise.id},
        )
        row = await h._lees(db_session, promise.id)
        assert (row.vraagt_om, row.termijn) == (None, "in mei")


class TestEenVerzoekDatWordtToegezegd:
    async def test_the_question_names_the_toezegging_and_stays_open(self, db_session):
        h = status_helpers
        mm = h.FakeMattermost()
        sessie_id, post_id, _ = await _asked(db_session, mm, Q_OVERZICHT)
        await _granted(db_session, mm, sessie_id)

        question, promise = await _rows(db_session, sessie_id)
        assert (promise.soort, promise.bij_volgnummer) == (SOORT_TOEZEGGING, 1)
        assert "· bij vraag 1 · " in mm.messages[promise.thread_post_id]
        # Stored with the toezegging: the reply of the question is to be
        # written again, and nothing else about the question changed.
        assert question.reacties_gewijzigd_at is not None
        assert (question.status, question.status_at) == (STATUS_OPEN, None)
        assert "toezegging 2" not in mm.messages[question.thread_post_id]

        ronde = await h._ronde(db_session, mm)

        assert (ronde.bijgewerkt, ronde.gewijzigd, ronde.mislukt) == (1, 0, 0)
        question = await h._lees(db_session, question.id)
        assert _meta(mm.messages[question.thread_post_id]).startswith(
            "Vraag 1 · ✉️ een overzicht voor de begrotingsbehandeling · 🤝"
            " toezegging 2 · aan de minister · "
        )
        assert mm.messages[question.thread_post_id].startswith("❓ **")
        assert (question.status, question.status_at) == (STATUS_OPEN, None)
        assert question.reacties_gewijzigd_at is None
        assert splits(mm.messages[post_id])[1] == "❓ 1 vraag · open"

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

        meta = _meta(mm.messages[question.thread_post_id])
        assert meta.startswith(
            "Vraag 1 · opgepakt door persoon.a · ✉️ een overzicht voor de"
            " begrotingsbehandeling · 🤝 toezegging 2 · aan de minister · "
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
        assert _meta(mm.messages[question.thread_post_id]).startswith(
            "Vraag 1 · 🤝 toezegging 2 · aan de minister · "
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
            termijn="voor de begrotingsbehandeling",
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
        assert _meta(mm.messages[question.thread_post_id]).startswith(
            "Vraag 1 · ✉️ een overzicht voor de begrotingsbehandeling · 🤝"
            " toezegging 2 · aan de minister · "
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
