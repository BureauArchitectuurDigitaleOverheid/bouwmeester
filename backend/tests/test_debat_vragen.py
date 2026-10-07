"""Tests for marking questions in a debate.

The service runs against a real database with a fake Mattermost and a fake
model. The fake model is a real `BaseLLMService` whose only fake part is the
text that comes back, so the prompt builder and the reading of the answer
are the real ones.

The turns come from a real debate (see the fixture), with the mistakes of
the automatic transcript left in and the names of people taken out.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.debat_markering import (
    SOORT_TOEZEGGING,
    SOORT_VRAAG,
    STATUS_ANTWOORD_KLAAR,
    STATUS_BEANTWOORD,
    STATUS_OPEN,
    STATUS_VERWORPEN,
    VERMELDING_HERHALING,
    DebatMarkering,
    DebatMarkeringVermelding,
)
from bouwmeester.models.debat_sessie import DebatSessie
from bouwmeester.services import debat_direct as dd
from bouwmeester.services import debat_vraag_service as mod
from bouwmeester.services.debat_statusregel import (
    met_body,
    met_status,
    splits,
    statusregel,
    voeg_samen,
)
from bouwmeester.services.debat_vraag_moment import Line
from bouwmeester.services.debat_vraag_service import (
    UITKOMST_AL_BEOORDEELD,
    UITKOMST_GEEN_VRAAG,
    UITKOMST_GEMARKEERD,
    UITKOMST_LLM_ONBEREIKBAAR,
    UITKOMST_LLM_ONBRUIKBAAR,
    UITKOMST_OVERGESLAGEN,
    Beurt,
    DebatContext,
    DebatVraagService,
    format_vraag_thread,
    is_bewindspersoon,
    lees_antwoord,
    statusblok_voor_post,
    stuk_blijkt_uit_citaat,
    vind_citaat,
)
from bouwmeester.services.llm.base import (
    DEBAT_VRAGEN_ONBEREIKBAAR,
    DEBAT_VRAGEN_ONBRUIKBAAR,
    BaseLLMService,
    DataSensitivity,
    DebatVraag,
    ProviderCapabilities,
)
from bouwmeester.services.llm.prompts import (
    MAX_BEURT_IN_PROMPT,
    build_debat_vragen_prompt,
)
from bouwmeester.services.mattermost_service import PostNotFoundError
from bouwmeester.services.tk_activiteit import (
    Activiteit,
    AgendaDocument,
    Agendapunt,
    Bewindspersoon,
)

FIXTURE = json.loads(
    (
        Path(__file__).parent / "fixtures" / "debat_transcript_notaoverleg.json"
    ).read_text(encoding="utf-8")
)
BEURTEN = FIXTURE["beurten"]
VOORZITTER, KAMERLID_A, KAMERLID_B_MET_MOTIE, KAMERLID_C, INTERRUPTIE, _ = BEURTEN
# The turn of Kamerlid B says a motie is being considered, and that is
# marked by rule. The tests that count the questions of that turn use it
# without that sentence; the ones on moties use it whole.
ZIN_MOTIE = next(
    zin
    for zin in re.split(r"(?<=[.?!]) ", KAMERLID_B_MET_MOTIE["tekst"])
    if "motie" in zin
)
KAMERLID_B = {
    **KAMERLID_B_MET_MOTIE,
    "tekst": " ".join(KAMERLID_B_MET_MOTIE["tekst"].replace(ZIN_MOTIE, "").split()),
}

CHANNEL = "chandebat0000000000000000"
TEAM = "teamdebat00000000000000000"
MOMENT_URL = (
    "https://debatdirect.example/debat?event=speaker2026-10-05T10%3A02%3A23%2B0200"
)

CONTEXT = DebatContext(
    onderwerp=FIXTURE["onderwerp"],
    soort=FIXTURE["soort"],
    bewindspersonen=(
        Bewindspersoon(naam="B. Bewindspersoon", functie="minister van Voorbeelden"),
    ),
    stukken=tuple(FIXTURE["stukken"]),
    initiatiefnemers=True,
)

# Quotes as they stand in the fixture, transcript mistakes and all.
Q_ARTSEN = (
    "Klopt het dat wordt bezuinigd op het aantal bedrijfsartsen of op de "
    "beschikbare uren bij de politie?"
)
Q_CAMPAGNE = (
    "Is de minister bereid om toe te zeggen dat hij voor alle beroepsgroepen "
    "een campagne gaat uitrollen zodat mensen met mogelijke "
    "PTSD-gerealiteerde klachten weten dat er hulp beschikbaar is en wanneer "
    "deze beschikbaar is?"
)
Q_WENSELIJK = "Vindt de minister dat een wenslijke situatie vragen wij?"
Q_TERMIJNEN = "Worden die termijnen daadwerkelijk gehaald?"
Q_LOKET = "Kan de minister dit nadertoe lichten?"
Q_KABINETSREACTIE = (
    "Uit de kabinetsreactie maak ik echter op dat de minister niet van plan is "
    "om één landelijk PTSS-loket in te richten voor deze beroepen. Kan de "
    "minister dit nadertoe lichten?"
)


def vraag(citaat: str, **extra) -> dict:
    return {
        "citaat": citaat,
        "gericht_aan": "de minister",
        "samenvatting": "Samenvatting van de vraag.",
        "hoort_bij": None,
        "stuk": None,
        **extra,
    }


def antwoord(*vragen: dict) -> str:
    return json.dumps({"vragen": list(vragen)}, ensure_ascii=False)


class FakeLLM(BaseLLMService):
    """A real provider, except that the text comes from a list."""

    capabilities = ProviderCapabilities(allowed_data={DataSensitivity.PUBLIC})

    def __init__(self, *answers: str | Exception) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []

    async def _complete(self, prompt: str, max_tokens: int = 1024) -> str:
        self.prompts.append(prompt)
        if not self.answers:
            return antwoord()
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


class FakeMattermost:
    def __init__(self) -> None:
        # The messages of the turns: post id -> text.
        self.messages: dict[str, str] = {}
        # (channel_id, root_id, text, post_id) of every reply.
        self.replies: list[tuple[str, str | None, str, str]] = []
        self.updates: list[tuple[str, str]] = []
        self.update_props: list[dict | None] = []
        self.props: dict[str, dict] = {}
        self.reads: list[str] = []
        self.fail_sends = 0
        self.raise_sends = 0
        self.fail_reads = 0
        self.fail_updates = 0
        self.gone: set[str] = set()
        # For the concurrency test: a send waits here while it holds its row.
        self.gate: asyncio.Event | None = None
        self.sending = asyncio.Event()

    def turn(self, text: str = "**Kamerlid A (BBB)** · 10:02\nDank u wel.") -> str:
        post_id = f"post{uuid.uuid4().hex}"[:26]
        self.messages[post_id] = text
        return post_id

    async def send_channel_message(self, channel_id, text, props=None, root_id=None):
        self.sending.set()
        if self.gate is not None:
            await self.gate.wait()
        if self.raise_sends > 0:
            self.raise_sends -= 1
            raise RuntimeError("mattermost is weg")
        if self.fail_sends > 0:
            self.fail_sends -= 1
            return None
        post_id = f"reply{uuid.uuid4().hex}"[:26]
        self.replies.append((channel_id, root_id, text, post_id))
        return post_id

    async def get_post(self, post_id):
        self.reads.append(post_id)
        if post_id in self.gone:
            raise PostNotFoundError(post_id)
        if self.fail_reads > 0:
            self.fail_reads -= 1
            return None
        return {
            "id": post_id,
            "message": self.messages[post_id],
            "props": self.props.get(post_id, {}),
        }

    async def update_post(self, post_id, message, props=None) -> bool:
        if self.fail_updates > 0:
            self.fail_updates -= 1
            return False
        self.updates.append((post_id, message))
        self.update_props.append(props)
        self.messages[post_id] = message
        return True

    async def add_reaction(self, post_id, emoji_name) -> bool:
        # The one reaction the bot puts under a new reply. What reactions
        # do is tested in `test_debat_vraag_status`.
        return True


async def _sessie(session: AsyncSession) -> uuid.UUID:
    sessie = DebatSessie(
        activiteit_id=str(uuid.uuid4()),
        onderwerp=FIXTURE["onderwerp"],
        team_id=TEAM,
    )
    session.add(sessie)
    await session.flush()
    return sessie.id


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
        "onderbroken": raw.get("onderbroken"),
    }
    values.update(extra)
    return Beurt(**values)


async def _markeringen(session: AsyncSession, sessie_id: uuid.UUID) -> list:
    return (
        await session.execute(
            select(
                DebatMarkering.volgnummer,
                DebatMarkering.citaat,
                DebatMarkering.thread_post_id,
                DebatMarkering.post_pogingen,
                DebatMarkering.statusregel_at,
            )
            .where(DebatMarkering.sessie_id == sessie_id)
            .order_by(DebatMarkering.volgnummer)
        )
    ).all()


# --- the status line ---------------------------------------------------


class TestStatusregel:
    def test_one_open_question_is_the_line_from_the_plan(self):
        assert statusregel([(SOORT_VRAAG, STATUS_OPEN)]) == ("❓ 1 vraag · open")

    def test_several_open_questions_are_one_line(self):
        assert statusregel([(SOORT_VRAAG, STATUS_OPEN)] * 3) == ("❓ 3 vragen · open")

    def test_mixed_states_are_counted_per_state(self):
        regel = statusregel(
            [
                (SOORT_VRAAG, STATUS_BEANTWOORD),
                (SOORT_VRAAG, STATUS_OPEN),
                (SOORT_VRAAG, STATUS_OPEN),
                (SOORT_VRAAG, STATUS_ANTWOORD_KLAAR),
            ]
        )
        assert regel == ("❓ 4 vragen · 2 open · 1 antwoord klaar · 1 beantwoord")

    def test_one_state_that_is_not_open_is_said_in_one_word_too(self):
        assert statusregel([(SOORT_VRAAG, STATUS_BEANTWOORD)]) == (
            "❓ 1 vraag · beantwoord"
        )
        assert statusregel([(SOORT_VRAAG, STATUS_ANTWOORD_KLAAR)] * 2) == (
            "❓ 2 vragen · antwoord klaar"
        )

    def test_a_rejected_question_does_not_count(self):
        assert statusregel(
            [(SOORT_VRAAG, STATUS_VERWORPEN), (SOORT_VRAAG, STATUS_OPEN)]
        ) == ("❓ 1 vraag · open")
        assert statusregel([(SOORT_VRAAG, STATUS_VERWORPEN)]) == ""

    def test_nothing_marked_is_no_line(self):
        assert statusregel([]) == ""

    def test_a_kind_that_is_not_built_yet_is_not_shown(self):
        assert statusregel([("feitelijke_claim", STATUS_OPEN)]) == ""

    def test_a_message_is_body_rule_status(self):
        bericht = voeg_samen("**Kamerlid A** · 10:02\nDank u wel.", "❓ Vraag")
        assert bericht == "**Kamerlid A** · 10:02\nDank u wel.\n\n---\n❓ Vraag"
        assert splits(bericht) == ("**Kamerlid A** · 10:02\nDank u wel.", "❓ Vraag")

    def test_a_message_without_status_is_only_body(self):
        assert voeg_samen("tekst\n", "") == "tekst"
        assert splits("tekst") == ("tekst", "")
        assert splits("") == ("", "")

    def test_the_status_writer_keeps_a_body_that_grew(self):
        """The transcript grew between two writes of the status line."""
        eerst = met_status("kop\neen zin.", "❓ 1 vraag · open")
        gegroeid = met_body(eerst, "kop\neen zin. En nog een zin.")
        daarna = met_status(gegroeid, "❓ 2 vragen · open")
        assert daarna == ("kop\neen zin. En nog een zin.\n\n---\n❓ 2 vragen · open")

    def test_the_body_writer_keeps_the_status(self):
        bericht = voeg_samen("kop", "❓ 1 vraag · open")
        assert met_body(bericht, "kop\nmeer tekst") == (
            "kop\nmeer tekst\n\n---\n❓ 1 vraag · open"
        )

    def test_an_empty_status_removes_the_block(self):
        assert met_status(voeg_samen("kop", "❓ Vraag"), "") == "kop"

    def test_a_bare_rule_in_the_body_is_not_read_as_the_separator(self):
        bericht = voeg_samen("kop\n---\nna de streep", "❓ Vraag")
        assert splits(bericht) == ("kop\n\\---\nna de streep", "❓ Vraag")
        # And without a status block nothing of the body is cut off.
        assert splits(voeg_samen("kop\n---\nna de streep", "")) == (
            "kop\n\\---\nna de streep",
            "",
        )

    def test_writing_twice_gives_the_same_message(self):
        een = met_status("kop\ntekst", "❓ Vraag")
        assert met_status(een, "❓ Vraag") == een

    def test_only_the_last_rule_is_the_separator(self):
        """A body written by hand with a rule in it loses nothing."""
        assert splits("kop\n---\nmidden\n---\n❓ Vraag") == (
            "kop\n---\nmidden",
            "❓ Vraag",
        )

    def test_a_status_of_several_lines_stays_together(self):
        bericht = voeg_samen("kop", "❓ Vraag\n📌 Toezegging")
        assert splits(bericht) == ("kop", "❓ Vraag\n📌 Toezegging")


# --- the quote ---------------------------------------------------------


class TestVindCitaat:
    TEKST = KAMERLID_A["tekst"]

    def test_a_literal_quote_is_found(self):
        assert vind_citaat(self.TEKST, Q_ARTSEN) == Q_ARTSEN

    def test_the_quote_comes_from_the_turn_not_from_the_model(self):
        """Other spacing, case and quotation marks: the turn's own text."""
        van_model = '"klopt het dat  wordt bezuinigd\nop het aantal BEDRIJFSARTSEN"'
        assert vind_citaat(self.TEKST, van_model) == (
            "Klopt het dat wordt bezuinigd op het aantal bedrijfsartsen"
        )

    def test_a_corrected_quote_comes_back_the_way_it_was_said(self):
        """The model fixed a transcript mistake. The thread says "literal",
        so it gets what the transcript has, mistake included."""
        verbeterd = Q_CAMPAGNE.replace("PTSD-gerealiteerde", "PTSD-gerelateerde")
        assert verbeterd != Q_CAMPAGNE
        assert vind_citaat(self.TEKST, verbeterd) == Q_CAMPAGNE

    def test_a_corrected_first_or_last_word_is_not_cut_in_half(self):
        citaat = "Zo ja, verhoudt zich dat tot de ambitie om beroepsgerelateerde"
        assert vind_citaat(self.TEKST, citaat) == (
            "Zoja, verhoudt zich dat tot de ambitie om beroepsgerealiteerde"
        )

    def test_a_corrected_last_word_comes_back_whole(self):
        assert vind_citaat(KAMERLID_B["tekst"], "Het kost inderdaad tijd, zweet") == (
            "Het kost inderdaad tijd, zweed,"
        )

    def test_quotation_marks_do_not_stand_in_the_way(self):
        assert vind_citaat(self.TEKST, '"En kan hij dat"') == "En kan hij dat"
        assert vind_citaat('Hij zei "nee" en bleef', "zei nee en") == 'zei "nee" en'

    def test_a_made_up_quote_is_not_found(self):
        assert vind_citaat(self.TEKST, "Wanneer komt de brief naar de Kamer?") is None

    def test_a_paraphrase_with_the_same_words_is_not_a_quote(self):
        """Words of the turn in an order of the model's own."""
        parafrase = (
            "Is de minister bereid een campagne uit te rollen voor alle "
            "beroepsgroepen zodat mensen weten dat er hulp beschikbaar is?"
        )
        assert vind_citaat(self.TEKST, parafrase) is None

    def test_two_real_sentences_far_apart_are_not_one_quote(self):
        citaat = (
            "Klopt het dat wordt bezuinigd op het aantal bedrijfsartsen? "
            "En kan hij dat toezeggen?"
        )
        assert vind_citaat(self.TEKST, citaat) is None

    def test_a_short_quote_has_to_be_exact(self):
        assert vind_citaat(self.TEKST, "En kan zij dat") is None
        assert vind_citaat(self.TEKST, "En kan hij dat") == "En kan hij dat"

    def test_parts_joined_with_dots_are_each_found(self):
        citaat = "Klopt het dat wordt bezuinigd [...] Worden die termijnen gehaald"
        assert vind_citaat(self.TEKST, citaat) is None
        citaat = "Klopt het dat wordt bezuinigd ... Worden die termijnen daadwerkelijk"
        assert vind_citaat(self.TEKST, citaat) == (
            "Klopt het dat wordt bezuinigd (...) Worden die termijnen daadwerkelijk"
        )

    def test_parts_in_the_wrong_order_are_not_a_quote(self):
        citaat = "Worden die termijnen daadwerkelijk ... Klopt het dat wordt bezuinigd"
        assert vind_citaat(self.TEKST, citaat) is None

    def test_dots_of_the_transcript_itself_are_part_of_the_quote(self):
        assert vind_citaat("Ik noemde de impact... en dan", "de impact... en") == (
            "de impact... en"
        )

    def test_an_empty_quote_is_nothing(self):
        assert vind_citaat(self.TEKST, "  ") is None
        assert vind_citaat(self.TEKST, '""') is None
        assert vind_citaat(self.TEKST, "...") is None


# --- the thread --------------------------------------------------------


def _thread(**extra) -> str:
    values = {
        "volgnummer": 12,
        "gericht_aan": "de minister",
        "citaat": Q_ARTSEN,
        "samenvatting": "Wordt er bezuinigd op bedrijfsartsen bij de politie?",
        "stuk": None,
        "moment": datetime.fromisoformat("2026-10-05T10:02:23+02:00"),
        "moment_url": MOMENT_URL,
        "vraag_moment": datetime.fromisoformat("2026-10-05T10:09:40+02:00"),
    }
    values.update(extra)
    return format_vraag_thread(**values)


# The link of the turn, opened five seconds before the question of 10:09:40.
VRAAG_URL = (
    "https://debatdirect.example/debat?event=speaker2026-10-05T10%3A09%3A35%2B0200"
)
NOOT = "_Citaten komen letterlijk uit het automatische transcript._"


class TestEenCitaatZegtIets:
    """A quote of a word or two stands in every turn and proves nothing:
    the summary next to it would be free text of the model."""

    @pytest.mark.parametrize("citaat", ["de", "?", "minister", "kan de"])
    def test_a_scrap_is_not_a_quote(self, citaat):
        assert vind_citaat("Kan de minister dat toezeggen? Dank.", citaat) is None

    def test_a_short_question_is(self):
        assert vind_citaat("Dank. Waarom niet? Dat vraag ik.", "Waarom niet? Dat") == (
            "Waarom niet? Dat"
        )


class TestFormatVraagThread:
    def test_the_whole_reply(self):
        assert _thread(stuk="Kabinetsreactie") == (
            "❓ **Wordt er bezuinigd op bedrijfsartsen bij de politie?**\n"
            f"Vraag 12 · aan de minister · [10:09]({VRAAG_URL})\n"
            "📄 Kabinetsreactie\n"
            f"> {Q_ARTSEN}\n"
            "\n"
            f"{NOOT}"
        )

    def test_a_later_reply_in_the_thread_ends_with_the_quote(self):
        assert _thread(first_in_thread=False) == (
            "❓ **Wordt er bezuinigd op bedrijfsartsen bij de politie?**\n"
            f"Vraag 12 · aan de minister · [10:09]({VRAAG_URL})\n"
            f"> {Q_ARTSEN}"
        )

    def test_only_the_question_is_bold(self):
        tekst = _thread(stuk="Kabinetsreactie")
        assert tekst.count("**") == 2
        assert tekst.split("\n")[0].count("**") == 2

    def test_who_asks_is_not_in_it(self):
        # The reply hangs under the message of the speaker.
        assert "Kamerlid" not in _thread()
        assert "BBB" not in _thread()

    def test_the_time_is_that_of_the_question_in_amsterdam(self):
        utc = datetime.fromisoformat("2026-10-05T08:09:40+00:00")
        assert f"· [10:09]({VRAAG_URL})" in _thread(vraag_moment=utc)

    def test_without_the_moment_of_the_question_it_is_the_start_of_the_turn(self):
        regel = _thread(vraag_moment=None).split("\n")[1]
        assert regel == (
            f"Vraag 12 · aan de minister · [10:02]({MOMENT_URL})"
            " (begin van de spreekbeurt)"
        )
        assert "begin van de spreekbeurt" not in _thread()

    def test_a_link_without_a_moment_in_it_still_opens_the_turn(self):
        url = "https://debatdirect.example/debat?event=speaker1"
        assert f"· [10:09]({url})" in _thread(moment_url=url)

    def test_without_a_link_the_time_is_plain(self):
        assert _thread(moment_url=None).split("\n")[1].endswith(" · 10:09")
        assert "](" not in _thread(moment_url=None)
        assert (
            _thread(moment_url=None, vraag_moment=None)
            .split("\n")[1]
            .endswith(" · 10:02 (begin van de spreekbeurt)")
        )

    @pytest.mark.parametrize("vraag_moment", [None, "2026-10-05T10:09:40+02:00"])
    @pytest.mark.parametrize(
        "url",
        [
            "javascript:alert(1)",
            "http://debatdirect.example/x",
            "https://debatdirect.example/x) [klik](https://kwaad.example",
            "https://debatdirect.example/x y",
            "https://debatdirect.example/x) [klik](https://kwaad.example"
            "?event=speaker2026-10-05T10%3A02%3A23%2B0200",
            "https://debatdirect.example/x"
            "?event=speaker2026-10-05T10%3A02%3A23%2B0200&x=) [klik](y",
        ],
    )
    def test_a_link_that_could_break_out_is_left_out(self, url, vraag_moment):
        moment = vraag_moment and datetime.fromisoformat(vraag_moment)
        tekst = _thread(moment_url=url, vraag_moment=moment)
        assert "](" not in tekst
        assert "kwaad" not in tekst

    def test_the_document_is_named_only_when_there_is_one(self):
        assert "📄" not in _thread()
        regels = _thread(stuk="Kabinetsreactie [concept]").split("\n")
        # Between the line about the question and the quote.
        assert regels[2] == "📄 Kabinetsreactie \\[concept\\]"
        assert regels[1].startswith("Vraag 12")
        assert regels[3].startswith("> ")

    def test_the_note_about_the_transcript_only_under_the_first_reply(self):
        assert _thread().endswith(f"\n> {Q_ARTSEN}\n\n{NOOT}")
        assert "transcript" not in _thread(first_in_thread=False)

    def test_no_empty_lines_but_the_one_that_ends_the_quote(self):
        assert _thread(stuk="Stuk").split("\n").count("") == 1
        assert "" not in _thread(stuk="Stuk", first_in_thread=False).split("\n")
        for tekst in (_thread(), _thread(first_in_thread=False)):
            assert tekst == tekst.strip()

    def test_text_from_outside_is_escaped(self):
        tekst = _thread(
            gericht_aan="de **minister**",
            citaat="Kan de minister @channel [dit](https://kwaad.example) lezen?",
            samenvatting="@here ~town-square _nu_ **vet**",
            stuk="@all **stuk**",
        )
        # No at-sign survives, escaped or not: a model can write the
        # backslash itself, and then the escape is what frees the mention.
        assert "@" not in tekst
        # Who it is put to is said in our words, not the model's.
        assert "· aan de minister ·" in tekst
        assert "channel \\[dit\\](https: //kwaad.example)" in tekst
        kop = tekst.split("\n")[0]
        assert kop == "❓ **here \\~town-square \\_nu\\_ \\*\\*vet\\*\\***"
        assert "📄 all \\*\\*stuk\\*\\*" in tekst

    def test_a_backslash_from_the_model_cannot_free_a_mention(self):
        tekst = _thread(
            samenvatting="lees \\@all en \\\\@here", citaat="Wat \\@channel?"
        )

        assert "@" not in tekst
        assert "\\" not in tekst.split("\n")[0]

    def test_an_address_does_not_become_a_link(self):
        tekst = _thread(samenvatting="zie https://kwaad.example en www.kwaad.example")

        assert "://" not in tekst.split("\n")[0]
        assert "www." not in tekst

    @pytest.mark.parametrize(
        "aan,verwacht",
        [
            ("De minister", "de minister"),
            ("minister", "de minister"),
            ("de staatssecretaris van BZK", "de staatssecretaris"),
            ("de minister-president", "de minister-president"),
            ("het kabinet", "het kabinet"),
            ("de regering", "het kabinet"),
            ("", "de bewindspersoon"),
            ("@all", "de bewindspersoon"),
        ],
    )
    def test_who_it_is_put_to_is_one_of_a_few(self, aan, verwacht):
        assert f"Vraag 12 · aan {verwacht} · [" in _thread(gericht_aan=aan)

    def test_a_quote_cannot_leave_its_block(self):
        tekst = _thread(citaat="Eerste regel.\n\n# Kop\n@channel")
        citaat = [r for r in tekst.split("\n") if r.startswith(">")]
        assert citaat == ["> Eerste regel. \\# Kop channel"]

    def test_a_summary_cannot_leave_its_line(self):
        tekst = _thread(samenvatting="Een vraag\n\n# Kop\n> citaat")
        assert tekst.split("\n")[0] == "❓ **Een vraag \\# Kop > citaat**"

    def test_a_very_long_quote_is_cut(self):
        tekst = _thread(citaat="woord " * 400)
        regel = next(r for r in tekst.split("\n") if r.startswith(">"))
        assert len(regel) <= mod.MAX_CITAAT + 2
        assert regel.endswith("…")

    def test_the_dots_of_a_line_that_runs_on_are_not_shown(self):
        tekst = _thread(citaat="Kan de minister... zeggen wanneer dat... komt?")
        assert "> Kan de minister zeggen wanneer dat komt?" in tekst

    def test_dots_that_end_a_sentence_stay(self):
        tekst = _thread(citaat="Dat is... Nee. Kan de minister dat zeggen?")
        assert "> Dat is... Nee. Kan de minister dat zeggen?" in tekst

    def test_what_was_left_out_between_two_pieces_stays_marked(self):
        tekst = _thread(citaat="Kan de minister dat (...) zeggen voor de zomer?")
        assert "> Kan de minister dat (...) zeggen voor de zomer?" in tekst

    @pytest.mark.parametrize("samenvatting", ["", "   ", "@", "\\"])
    def test_without_a_summary_the_first_sentence_of_the_quote_is_the_question(
        self, samenvatting
    ):
        tekst = _thread(
            samenvatting=samenvatting,
            citaat="Kan de minister dat toezeggen? Ik hoor het graag. Dank.",
        )
        assert tekst.split("\n")[0] == "❓ **Kan de minister dat toezeggen?**"
        assert "> Kan de minister dat toezeggen? Ik hoor het graag. Dank." in tekst

    def test_a_first_sentence_that_goes_on_and_on_is_cut(self):
        kop = _thread(samenvatting="", citaat="woord " * 100).split("\n")[0]
        assert kop.startswith("❓ **woord woord")
        assert kop.endswith("…**")
        assert len(kop) <= mod.MAX_KOP + len("❓ ****")

    def test_a_quote_without_an_end_of_sentence_is_the_question_as_a_whole(self):
        kop = _thread(samenvatting="", citaat="wanneer komt de brief").split("\n")[0]
        assert kop == "❓ **wanneer komt de brief**"

    def test_the_first_sentence_is_read_past_the_dots_of_a_line_that_runs_on(self):
        kop = _thread(
            samenvatting="", citaat="Kan de minister... zeggen wanneer? Dank."
        ).split("\n")[0]
        assert kop == "❓ **Kan de minister zeggen wanneer?**"

    def test_a_number_with_a_dot_in_it_does_not_end_the_sentence(self):
        kop = _thread(
            samenvatting="", citaat="Komt die 1.5 miljoen er nog? Graag een reactie."
        ).split("\n")[0]
        assert kop == "❓ **Komt die 1.5 miljoen er nog?**"

    def test_nothing_at_all_to_say_is_still_not_four_asterisks(self):
        kop = _thread(samenvatting="@", citaat="@@@@@@@@@@@@@").split("\n")[0]
        assert kop == "❓ **Vraag**"

    def test_an_empty_addressee_is_the_bewindspersoon(self):
        assert "· aan de bewindspersoon ·" in _thread(gericht_aan="")


# --- reading the answer ------------------------------------------------


def _vraag(citaat: str, **extra) -> DebatVraag:
    return DebatVraag(**vraag(citaat, **extra))


class TestLeesAntwoord:
    TEKST = KAMERLID_A["tekst"]
    STUKKEN = tuple(FIXTURE["stukken"])

    def test_a_new_question(self):
        nieuw, herhaald, afgevallen = lees_antwoord(
            [_vraag(Q_ARTSEN)], self.TEKST, self.STUKKEN, set()
        )
        assert [n.citaat for n in nieuw] == [Q_ARTSEN]
        assert nieuw[0].gericht_aan == "de minister"
        assert nieuw[0].stuk is None
        assert (herhaald, afgevallen) == ([], 0)

    def test_a_question_to_the_initiatiefnemers_is_dropped(self):
        citaat = "Maar hoe zien de initiatiefnemers dit melpunt concreet voor zich?"
        nieuw, herhaald, afgevallen = lees_antwoord(
            [_vraag(citaat, gericht_aan="de initiatiefnemers")],
            self.TEKST,
            self.STUKKEN,
            set(),
        )
        assert (nieuw, herhaald, afgevallen) == ([], [], 1)

    @pytest.mark.parametrize(
        "aan",
        [
            "de minister",
            "de Staatssecretaris",
            "het kabinet",
            "de regering",
            "de initiatiefnemers en de minister",
            "de bewindspersoon",
            "de minister-president",
        ],
    )
    def test_who_counts_as_the_bewindspersoon(self, aan):
        nieuw, _, _ = lees_antwoord(
            [_vraag(Q_ARTSEN, gericht_aan=aan)], self.TEKST, self.STUKKEN, set()
        )
        assert len(nieuw) == 1

    @pytest.mark.parametrize("aan", ["", "de voorzitter", "mevrouw A", "collega's"])
    def test_who_does_not(self, aan):
        nieuw, _, afgevallen = lees_antwoord(
            [_vraag(Q_ARTSEN, gericht_aan=aan)], self.TEKST, self.STUKKEN, set()
        )
        assert (nieuw, afgevallen) == ([], 1)

    def test_a_quote_that_is_not_in_the_turn_is_dropped(self):
        nieuw, _, afgevallen = lees_antwoord(
            [_vraag("Wanneer komt de brief?"), _vraag(Q_ARTSEN)],
            self.TEKST,
            self.STUKKEN,
            set(),
        )
        assert [n.citaat for n in nieuw] == [Q_ARTSEN]
        assert afgevallen == 1

    def test_the_same_quote_twice_is_one_question(self):
        nieuw, _, afgevallen = lees_antwoord(
            [_vraag(Q_ARTSEN), _vraag(Q_ARTSEN.upper())],
            self.TEKST,
            self.STUKKEN,
            set(),
        )
        assert (len(nieuw), afgevallen) == (1, 1)

    def test_a_question_that_belongs_to_an_open_one_is_a_herhaling(self):
        nieuw, herhaald, _ = lees_antwoord(
            [_vraag(Q_ARTSEN, hoort_bij=4)], self.TEKST, self.STUKKEN, {4}
        )
        assert nieuw == []
        assert [(h.volgnummer, h.citaat) for h in herhaald] == [(4, Q_ARTSEN)]

    def test_a_number_that_is_not_open_makes_the_question_new(self):
        nieuw, herhaald, _ = lees_antwoord(
            [_vraag(Q_ARTSEN, hoort_bij=9)], self.TEKST, self.STUKKEN, {4}
        )
        assert (len(nieuw), herhaald) == (1, [])

    def test_two_questions_on_the_same_open_one_are_one_herhaling(self):
        _, herhaald, _ = lees_antwoord(
            [_vraag(Q_ARTSEN, hoort_bij=4), _vraag(Q_CAMPAGNE, hoort_bij=4)],
            self.TEKST,
            self.STUKKEN,
            {4},
        )
        assert [h.volgnummer for h in herhaald] == [4]

    def test_the_document_is_named_when_the_quote_points_at_it(self):
        nieuw, _, _ = lees_antwoord(
            [_vraag(Q_KABINETSREACTIE, stuk=2)],
            KAMERLID_B["tekst"],
            self.STUKKEN,
            set(),
            FIXTURE["onderwerp"],
        )
        assert [n.stuk for n in nieuw] == [self.STUKKEN[1]]

    def test_a_document_the_model_picked_without_reason_is_left_out(self):
        """Every question is about the subject of the debate."""
        nieuw, _, _ = lees_antwoord(
            [_vraag(Q_ARTSEN, stuk=2), _vraag(Q_CAMPAGNE, stuk=1)],
            self.TEKST,
            self.STUKKEN,
            set(),
            FIXTURE["onderwerp"],
        )
        assert [n.stuk for n in nieuw] == [None, None]

    @pytest.mark.parametrize("nummer", [0, 3, -1, 99])
    def test_a_document_that_is_not_on_the_agenda_is_left_out(self, nummer):
        nieuw, _, _ = lees_antwoord(
            [_vraag(Q_KABINETSREACTIE, stuk=nummer)],
            KAMERLID_B["tekst"],
            self.STUKKEN,
            set(),
            FIXTURE["onderwerp"],
        )
        assert nieuw[0].stuk is None

    def test_what_points_at_a_document(self):
        onderwerp = FIXTURE["onderwerp"]
        nota, reactie = self.STUKKEN
        assert stuk_blijkt_uit_citaat(Q_KABINETSREACTIE, reactie, onderwerp)
        assert stuk_blijkt_uit_citaat("In de REACTIE staat", reactie, onderwerp)
        # Words of the subject of the debate point at nothing.
        assert not stuk_blijkt_uit_citaat(
            "de aanpak van PTSS bij geuniformeerde beroepen", reactie, onderwerp
        )
        # The document the debate is about is never the answer.
        assert not stuk_blijkt_uit_citaat(
            "In de initiatiefnota staat dat", nota, onderwerp
        )
        # Short words say nothing: "van", "het", "op".
        assert not stuk_blijkt_uit_citaat("van het op de", reactie, onderwerp)
        # Accents do not get in the way.
        assert stuk_blijkt_uit_citaat(
            "de evaluatie van de geüniformeerde dienst", "Geuniformeerde dienst", ""
        )

    def test_a_long_summary_is_cut(self):
        nieuw, _, _ = lees_antwoord(
            [_vraag(Q_ARTSEN, samenvatting="lang " * 200)],
            self.TEKST,
            self.STUKKEN,
            set(),
        )
        assert len(nieuw[0].samenvatting) <= mod.MAX_SAMENVATTING


# --- the prompt and the provider ---------------------------------------


def _prompt(**extra) -> str:
    values = {
        "onderwerp": FIXTURE["onderwerp"],
        "soort_vergadering": "Notaoverleg",
        "bewindspersonen": ["minister van Voorbeelden: B. Bewindspersoon"],
        "stukken": list(FIXTURE["stukken"]),
        "openstaand": [],
        "spreker": "Kamerlid A (BBB)",
        "interruptie": False,
        "tekst": KAMERLID_A["tekst"],
    }
    values.update(extra)
    return build_debat_vragen_prompt(**values)


class TestPrompt:
    def test_carries_what_is_known_about_the_debate(self):
        prompt = _prompt()
        assert f"Onderwerp: {FIXTURE['onderwerp']}" in prompt
        assert "Soort vergadering: Notaoverleg" in prompt
        assert "- minister van Voorbeelden: B. Bewindspersoon" in prompt
        assert f"1. {FIXTURE['stukken'][0]}" in prompt
        assert f"2. {FIXTURE['stukken'][1]}" in prompt
        assert "Dit is een spreekbeurt van Kamerlid A (BBB)." in prompt
        assert f"<spreekbeurt>\n{KAMERLID_A['tekst']}\n</spreekbeurt>" in prompt

    def test_without_open_questions_it_says_so(self):
        assert "nog openstaan\n(nog geen)" in _prompt()

    def test_lists_the_open_questions_with_their_number(self):
        prompt = _prompt(
            openstaand=[
                (3, "Kamerlid A (BBB)", "Wordt er bezuinigd op bedrijfsartsen?"),
                (7, "Kamerlid B (CDA)", "Waarom komt er geen loket?"),
            ]
        )
        assert "3. Kamerlid A (BBB): Wordt er bezuinigd op bedrijfsartsen?\n" in prompt
        assert "7. Kamerlid B (CDA): Waarom komt er geen loket?\n" in prompt
        assert "(nog geen)" not in prompt

    def test_an_interruption_says_who_is_interrupted(self):
        prompt = _prompt(interruptie=True, onderbroken="Kamerlid C (D66)")
        assert (
            "Dit is een interruptie van Kamerlid A (BBB), die Kamerlid C (D66)"
            " onderbreekt." in prompt
        )
        zonder = _prompt(interruptie=True)
        assert "Wie er wordt onderbroken is niet bekend." in zonder

    def test_with_initiatiefnemers_a_question_to_nobody_does_not_count(self):
        met = _prompt(initiatiefnemers=True)
        zonder = _prompt(initiatiefnemers=False)
        assert "Naast de bewindspersoon zitten de initiatiefnemers" in met
        assert "Naast de bewindspersoon zitten de initiatiefnemers" not in zonder
        assert "In dit debat antwoordt alleen de bewindspersoon." in zonder
        assert "In dit debat antwoordt alleen de bewindspersoon." not in met

    def test_missing_context_does_not_break_it(self):
        prompt = _prompt(soort_vergadering=None, bewindspersonen=[], stukken=[])
        assert "Soort vergadering" not in prompt
        assert "- (niet bekend)" in prompt
        assert "Geagendeerde stukken:\n(geen)" in prompt

    def test_of_a_very_long_turn_the_end_is_kept(self):
        tekst = "begin " + "x" * MAX_BEURT_IN_PROMPT + " Kan de minister dat toezeggen?"
        prompt = _prompt(tekst=tekst)
        assert "Kan de minister dat toezeggen?\n</spreekbeurt>" in prompt
        assert "begin " not in prompt
        assert "<spreekbeurt>\n(...) " in prompt


async def _ask(llm: FakeLLM):
    return await llm.markeer_debat_vragen(
        onderwerp="Onderwerp",
        soort_vergadering=None,
        bewindspersonen=[],
        stukken=[],
        openstaand=[],
        spreker="Kamerlid A (BBB)",
        interruptie=False,
        tekst=KAMERLID_A["tekst"],
    )


class TestProvider:
    async def test_reads_a_plain_answer(self):
        result = await _ask(FakeLLM(antwoord(vraag(Q_ARTSEN, hoort_bij=2, stuk=1))))
        assert result.fout is None
        assert result.vragen == [
            DebatVraag(
                citaat=Q_ARTSEN,
                gericht_aan="de minister",
                samenvatting="Samenvatting van de vraag.",
                hoort_bij=2,
                stuk=1,
            )
        ]

    async def test_reads_an_answer_in_a_code_fence(self):
        result = await _ask(FakeLLM(f"```json\n{antwoord(vraag(Q_ARTSEN))}\n```"))
        assert [v.citaat for v in result.vragen] == [Q_ARTSEN]

    async def test_no_question_is_an_answer_not_a_failure(self):
        result = await _ask(FakeLLM('{"vragen": []}'))
        assert (result.vragen, result.fout) == ([], None)

    async def test_an_unreachable_model_is_not_asked_twice(self):
        llm = FakeLLM(TimeoutError("te laat"), antwoord(vraag(Q_ARTSEN)))
        result = await _ask(llm)
        assert result.fout == DEBAT_VRAGEN_ONBEREIKBAAR
        assert result.vragen == []
        assert len(llm.prompts) == 1

    async def test_an_unreadable_answer_gets_a_second_chance(self):
        llm = FakeLLM("Hier is mijn analyse:", antwoord(vraag(Q_ARTSEN)))
        result = await _ask(llm)
        assert result.fout is None
        assert [v.citaat for v in result.vragen] == [Q_ARTSEN]
        assert len(llm.prompts) == 2

    @pytest.mark.parametrize(
        "onzin",
        ["", "geen json", '{"vragen": "geen"}', "[]", '{"antwoord": []}'],
    )
    async def test_twice_unreadable_is_unusable(self, onzin):
        llm = FakeLLM(onzin, onzin, antwoord(vraag(Q_ARTSEN)))
        result = await _ask(llm)
        assert result.fout == DEBAT_VRAGEN_ONBRUIKBAAR
        assert result.vragen == []
        assert len(llm.prompts) == 2

    async def test_one_bad_item_does_not_take_the_rest_along(self):
        raw = json.dumps(
            {
                "vragen": [
                    "geen object",
                    {"citaat": "", "gericht_aan": "de minister"},
                    {"gericht_aan": "de minister"},
                    {"citaat": Q_ARTSEN},
                ]
            }
        )
        result = await _ask(FakeLLM(raw))
        assert result.fout is None
        assert result.vragen == [
            DebatVraag(citaat=Q_ARTSEN, gericht_aan="", samenvatting="")
        ]

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [(3, 3), ("3", 3), (" 4 ", 4), (None, None), (True, None), ("nieuw", None)],
    )
    async def test_numbers_are_read_leniently_but_not_guessed(self, raw, expected):
        result = await _ask(FakeLLM(antwoord(vraag(Q_ARTSEN, hoort_bij=raw, stuk=raw))))
        assert result.vragen[0].hoort_bij == expected
        assert result.vragen[0].stuk == expected


# --- small parts of the contract ---------------------------------------


class TestContract:
    def test_a_minister_is_a_bewindspersoon(self):
        assert is_bewindspersoon(dd.Spreker("B.", None, "minister van Voorbeelden"))
        assert is_bewindspersoon(dd.Spreker("B.", None, "Staatssecretaris van X"))

    def test_a_member_of_parliament_is_not(self):
        assert not is_bewindspersoon(dd.Spreker("A.", "BBB", "Tweede Kamerlid"))
        assert not is_bewindspersoon(dd.Spreker("A.", None, "Tweede Kamerlid"))
        assert not is_bewindspersoon(dd.Spreker("A.", None, None))
        # A party wins from a title.
        assert not is_bewindspersoon(dd.Spreker("A.", "BBB", "minister"))

    def test_the_key_of_a_turn(self):
        sessie_id = uuid.uuid4()
        spreekbeurt_id = uuid.uuid4()
        beurt = _beurt(sessie_id, KAMERLID_A, "post1", spreekbeurt_id=spreekbeurt_id)
        assert beurt.sleutel == f"beurt:{spreekbeurt_id}"
        assert _beurt(sessie_id, KAMERLID_A, "post1").sleutel == "post:post1"
        zonder = _beurt(sessie_id, KAMERLID_A, None)
        assert zonder.sleutel == "tijd:2026-10-05T08:02:23+00:00|Kamerlid A (BBB)"
        assert (
            len(_beurt(sessie_id, KAMERLID_A, None, spreker="x" * 400).sleutel) == 255
        )

    def test_context_from_an_activiteit(self):
        activiteit = Activiteit(
            id="a1",
            nummer="2026A00001",
            soort="Notaoverleg",
            onderwerp="Initiatiefnota over de aanpak van PTSS",
            aanvang=None,
            einde=None,
            status=None,
            commissie=None,
            bewindspersonen=(Bewindspersoon("B. Bewindspersoon", "minister"),),
            agendapunten=(
                Agendapunt(
                    1,
                    "Agendapunt met stukken",
                    None,
                    (
                        AgendaDocument("2026D1", "Brief", "De initiatiefnota"),
                        AgendaDocument("2026D2", "Brief", None),
                        AgendaDocument("2026D3", "Brief", "De kabinetsreactie"),
                    ),
                ),
                Agendapunt(2, "Agendapunt zonder stukken", None, ()),
                Agendapunt(3, "De initiatiefnota", None, ()),
            ),
        )
        context = DebatContext.from_activiteit(activiteit)
        assert context.onderwerp == "Initiatiefnota over de aanpak van PTSS"
        assert context.soort == "Notaoverleg"
        assert context.bewindspersonen == activiteit.bewindspersonen
        assert context.stukken == (
            "De initiatiefnota",
            "De kabinetsreactie",
            "Agendapunt zonder stukken",
        )
        assert context.initiatiefnemers is True

    def test_an_ordinary_debate_has_no_initiatiefnemers(self):
        activiteit = Activiteit(
            id="a1",
            nummer=None,
            soort="Commissiedebat",
            onderwerp="Digitaliserende overheid",
            aanvang=None,
            einde=None,
            status=None,
            commissie=None,
            bewindspersonen=(),
            agendapunten=(),
        )
        assert DebatContext.from_activiteit(activiteit).initiatiefnemers is False

    async def test_the_service_is_built_on_the_configured_model(
        self, db_session, monkeypatch
    ):
        from bouwmeester.services import llm as llm_package

        fake, mm = FakeLLM(), FakeMattermost()

        async def configured(db):
            return fake

        monkeypatch.setattr(llm_package, "get_llm_service", configured)
        svc = await DebatVraagService.create(db_session, mm)
        assert (svc.llm, svc.mattermost, svc.session) == (fake, mm, db_session)

    async def test_without_a_model_there_is_no_service(self, db_session, monkeypatch):
        from bouwmeester.services import llm as llm_package

        async def nothing(db):
            return None

        monkeypatch.setattr(llm_package, "get_llm_service", nothing)
        assert await DebatVraagService.create(db_session, FakeMattermost()) is None


# --- the service -------------------------------------------------------


class TestWhatIsNotSentToTheModel:
    async def _skipped(self, db_session, raw, **extra) -> tuple[str, FakeLLM]:
        sessie_id = await _sessie(db_session)
        mm, llm = FakeMattermost(), FakeLLM(antwoord(vraag(Q_ARTSEN)))
        result = await DebatVraagService(db_session, mm, llm).beoordeel_beurt(
            _beurt(sessie_id, raw, mm.turn(), **extra), CONTEXT
        )
        assert await _markeringen(db_session, sessie_id) == [] or llm.prompts
        return (result.reden if result.uitkomst == UITKOMST_OVERGESLAGEN else ""), llm

    async def test_the_chairman(self, db_session):
        reden, llm = await self._skipped(db_session, VOORZITTER)
        assert reden == "voorzitter"
        assert llm.prompts == []

    # An answer in which nothing is promised. What the service does with
    # one that holds a toezegging is in `test_debat_toezegging`.
    ANTWOORD = {
        **KAMERLID_A,
        "tekst": "Dank u wel, voorzitter. Het budget is dit jaar 54 miljoen euro, "
        "evenveel als vorig jaar. Wat vindt de Kamer daar zelf van?",
    }

    async def test_the_bewindspersoon(self, db_session):
        reden, llm = await self._skipped(
            db_session,
            self.ANTWOORD,
            # Not someone the agenda knows, so only the flag can tell.
            spreker="Iemand Anders (staatssecretaris van Voorbeelden)",
            fractie=None,
            is_bewindspersoon=True,
        )
        assert reden == "bewindspersoon"
        assert llm.prompts == []

    async def test_the_bewindspersoon_by_surname_when_not_flagged(self, db_session):
        reden, llm = await self._skipped(
            db_session,
            self.ANTWOORD,
            spreker="Bob Bewindspersoon (minister van Voorbeelden)",
            fractie=None,
        )
        assert reden == "bewindspersoon"
        assert llm.prompts == []

    async def test_a_member_with_the_same_surname_is_judged(self, db_session):
        reden, llm = await self._skipped(
            db_session, KAMERLID_A, spreker="Anna Bewindspersoon (BBB)", fractie="BBB"
        )
        assert reden == ""
        assert len(llm.prompts) == 1

    async def test_a_turn_of_a_few_words(self, db_session):
        reden, llm = await self._skipped(
            db_session, KAMERLID_A, tekst="Het is maandagochtend."
        )
        assert reden == "te kort"
        assert llm.prompts == []

    async def test_five_words_are_enough(self, db_session):
        reden, llm = await self._skipped(
            db_session, KAMERLID_A, tekst="Kan de minister dat toezeggen?"
        )
        assert reden == ""
        assert len(llm.prompts) == 1

    async def test_an_interruption_of_someone_else(self, db_session):
        """ "Bent u het daarmee eens?" is a question to the one interrupted."""
        reden, llm = await self._skipped(db_session, INTERRUPTIE)
        assert reden == "interruptie van een ander"
        assert llm.prompts == []

    async def test_an_interruption_that_names_the_minister_is_judged(self, db_session):
        tekst = INTERRUPTIE["tekst"] + " En is de minister het daarmee eens?"
        reden, llm = await self._skipped(db_session, INTERRUPTIE, tekst=tekst)
        assert reden == ""
        assert "die Kamerlid C (D66) onderbreekt" in llm.prompts[0]

    async def test_an_interruption_of_the_bewindspersoon_is_judged(self, db_session):
        reden, llm = await self._skipped(
            db_session, INTERRUPTIE, onderbroken_is_bewindspersoon=True
        )
        assert reden == ""
        assert len(llm.prompts) == 1


class TestMarkeren:
    async def test_a_question_becomes_a_row_a_thread_and_a_status_line(
        self, db_session
    ):
        sessie_id = await _sessie(db_session)
        mm = FakeMattermost()
        body = "**Kamerlid A (BBB)** · 10:02\nDank u wel. Voorzitter, ik wil..."
        post_id = mm.turn(body)
        llm = FakeLLM(
            antwoord(
                vraag(
                    Q_ARTSEN,
                    samenvatting="Wordt er bezuinigd op bedrijfsartsen?",
                    stuk=2,
                ),
                vraag(Q_CAMPAGNE, samenvatting="Komt er een campagne?"),
            )
        )
        beurt = _beurt(sessie_id, KAMERLID_A, post_id)

        result = await DebatVraagService(db_session, mm, llm).beoordeel_beurt(
            beurt, CONTEXT
        )

        assert result.uitkomst == UITKOMST_GEMARKEERD
        assert result.threads == 2
        assert result.herhaald == ()
        assert result.opnieuw_proberen is False

        rows = (
            (
                await db_session.execute(
                    select(DebatMarkering)
                    .where(DebatMarkering.sessie_id == sessie_id)
                    .order_by(DebatMarkering.volgnummer)
                )
            )
            .scalars()
            .all()
        )
        assert tuple(r.id for r in rows) == result.markering_ids
        assert [r.volgnummer for r in rows] == [1, 2]
        een, twee = rows
        assert (een.soort, een.status) == (SOORT_VRAAG, STATUS_OPEN)
        assert een.citaat == Q_ARTSEN
        assert een.samenvatting == "Wordt er bezuinigd op bedrijfsartsen?"
        assert een.gericht_aan == "de minister"
        assert (een.spreker, een.fractie) == ("Kamerlid A (BBB)", "BBB")
        assert een.moment == beurt.start
        assert een.moment_url == MOMENT_URL
        assert (een.channel_id, een.beurt_post_id) == (CHANNEL, post_id)
        assert een.beurt_sleutel == beurt.sleutel
        # The model named a document the quote does not point at.
        assert een.stuk is None
        assert een.statusregel_at is not None

        # One reply per question, under the message of the turn.
        assert [(c, root) for c, root, _, _ in mm.replies] == [(CHANNEL, post_id)] * 2
        assert [r.thread_post_id for r in rows] == [p for _, _, _, p in mm.replies]
        eerste = mm.replies[0][2]
        assert f"> {Q_ARTSEN}" in eerste
        assert eerste.split("\n")[0] == "❓ **Wordt er bezuinigd op bedrijfsartsen?**"
        # No lines were handed in with this turn: the time is the turn's.
        assert eerste.split("\n")[1] == (
            f"Vraag 1 · aan de minister · [10:02]({MOMENT_URL})"
            " (begin van de spreekbeurt)"
        )
        assert een.vraag_moment is None
        assert "📄" not in eerste
        # Said once in the thread, under the first reply.
        assert eerste.endswith(NOOT)
        assert mm.replies[1][2].split("\n")[1].startswith("Vraag 2 · ")
        assert "transcript" not in mm.replies[1][2]

        # The message of the turn keeps its text and gets the status line.
        assert mm.messages[post_id] == (f"{body}\n\n---\n❓ 2 vragen · open")
        assert len(mm.updates) == 1

    async def test_the_document_a_question_names_is_in_the_thread(self, db_session):
        sessie_id = await _sessie(db_session)
        mm = FakeMattermost()
        llm = FakeLLM(antwoord(vraag(Q_KABINETSREACTIE, stuk=2)))

        await DebatVraagService(db_session, mm, llm).beoordeel_beurt(
            _beurt(sessie_id, KAMERLID_B, mm.turn()), CONTEXT
        )

        assert f"\n📄 {FIXTURE['stukken'][1]}\n> " in mm.replies[0][2]
        stuk = (
            await db_session.execute(
                select(DebatMarkering.stuk).where(DebatMarkering.sessie_id == sessie_id)
            )
        ).scalar_one()
        assert stuk == FIXTURE["stukken"][1]

    async def test_what_is_stored_as_said_is_what_the_transcript_has(self, db_session):
        """The model repaired a mistake of the transcript in its quote."""
        sessie_id = await _sessie(db_session)
        mm = FakeMattermost()
        verbeterd = Q_CAMPAGNE.replace("PTSD-gerealiteerde", "PTSD-gerelateerde")
        llm = FakeLLM(antwoord(vraag(verbeterd)))

        await DebatVraagService(db_session, mm, llm).beoordeel_beurt(
            _beurt(sessie_id, KAMERLID_A, mm.turn()), CONTEXT
        )

        assert [r[1] for r in await _markeringen(db_session, sessie_id)] == [Q_CAMPAGNE]
        assert f"> {Q_CAMPAGNE}" in mm.replies[0][2]

    async def test_the_document_the_debate_is_about_is_never_named(self, db_session):
        """The quote has words of the subject in it ("beroepen"). That is
        true of every question in the debate."""
        sessie_id = await _sessie(db_session)
        mm = FakeMattermost()
        llm = FakeLLM(antwoord(vraag(Q_KABINETSREACTIE, stuk=1)))

        await DebatVraagService(db_session, mm, llm).beoordeel_beurt(
            _beurt(sessie_id, KAMERLID_B, mm.turn()), CONTEXT
        )

        assert "📄" not in mm.replies[0][2]

    async def test_a_turn_without_a_question_leaves_nothing(self, db_session):
        sessie_id = await _sessie(db_session)
        mm, llm = FakeMattermost(), FakeLLM(antwoord())
        post_id = mm.turn()

        result = await DebatVraagService(db_session, mm, llm).beoordeel_beurt(
            _beurt(sessie_id, KAMERLID_C, post_id), CONTEXT
        )

        assert result.uitkomst == UITKOMST_GEEN_VRAAG
        assert result.markering_ids == ()
        assert await _markeringen(db_session, sessie_id) == []
        assert mm.replies == []
        assert mm.updates == []
        assert len(llm.prompts) == 1

    async def test_only_dropped_answers_is_no_question(self, db_session):
        sessie_id = await _sessie(db_session)
        mm = FakeMattermost()
        llm = FakeLLM(antwoord(vraag("Dit heeft niemand gezegd?")))

        result = await DebatVraagService(db_session, mm, llm).beoordeel_beurt(
            _beurt(sessie_id, KAMERLID_A, mm.turn()), CONTEXT
        )

        assert (result.uitkomst, result.afgevallen) == (UITKOMST_GEEN_VRAAG, 1)
        assert await _markeringen(db_session, sessie_id) == []
        assert mm.replies == []

    async def test_the_model_gets_the_context_and_the_turn(self, db_session):
        sessie_id = await _sessie(db_session)
        mm, llm = FakeMattermost(), FakeLLM()
        await DebatVraagService(db_session, mm, llm).beoordeel_beurt(
            _beurt(sessie_id, KAMERLID_A, mm.turn()), CONTEXT
        )
        (prompt,) = llm.prompts
        assert f"Onderwerp: {FIXTURE['onderwerp']}" in prompt
        assert "- minister van Voorbeelden: B. Bewindspersoon" in prompt
        assert f"2. {FIXTURE['stukken'][1]}" in prompt
        assert "Naast de bewindspersoon zitten de initiatiefnemers" in prompt
        assert "Dit is een spreekbeurt van Kamerlid A (BBB)." in prompt
        assert KAMERLID_A["tekst"] in prompt

    async def test_what_the_model_wrote_is_escaped_in_the_channel(self, db_session):
        sessie_id = await _sessie(db_session)
        mm = FakeMattermost()
        llm = FakeLLM(
            antwoord(
                vraag(
                    Q_ARTSEN,
                    samenvatting="@channel lees dit",
                    gericht_aan="de minister @all",
                )
            )
        )
        await DebatVraagService(db_session, mm, llm).beoordeel_beurt(
            _beurt(sessie_id, KAMERLID_A, mm.turn()), CONTEXT
        )
        tekst = mm.replies[0][2]
        assert "channel lees dit" in tekst
        assert "· aan de minister ·" in tekst
        assert "@" not in tekst


class TestEenVraagIsEenToestand:
    """The open questions of a speaker go along with their next turn, so a
    question that is asked again does not become a second thread."""

    async def _first(self, db_session):
        sessie_id = await _sessie(db_session)
        mm = FakeMattermost()
        llm = FakeLLM(
            antwoord(
                vraag(Q_ARTSEN, samenvatting="Wordt er bezuinigd op bedrijfsartsen?"),
                vraag(Q_CAMPAGNE, samenvatting="Komt er een campagne?"),
            )
        )
        svc = DebatVraagService(db_session, mm, llm)
        post_a = mm.turn()
        await svc.beoordeel_beurt(_beurt(sessie_id, KAMERLID_A, post_a), CONTEXT)
        return sessie_id, mm, llm, svc, post_a

    def _again(self, sessie_id, mm) -> Beurt:
        """Kamerlid A speaks again, later in the debate."""
        return _beurt(
            sessie_id,
            KAMERLID_A,
            mm.turn("**Kamerlid A (BBB)** · 11:40"),
            start=datetime.fromisoformat("2026-10-05T11:40:00+02:00"),
        )

    async def test_the_next_turn_of_the_speaker_gets_their_open_questions(
        self, db_session
    ):
        sessie_id, mm, llm, svc, _ = await self._first(db_session)
        await svc.beoordeel_beurt(self._again(sessie_id, mm), CONTEXT)

        assert "(nog geen)" in llm.prompts[0]
        assert (
            "1. Kamerlid A (BBB): Wordt er bezuinigd op bedrijfsartsen?\n"
            "2. Kamerlid A (BBB): Komt er een campagne?\n"
        ) in llm.prompts[1]

    async def test_another_speaker_does_not_get_them(self, db_session):
        """Two members who ask about the same thing each expect an answer."""
        sessie_id, mm, llm, svc, _ = await self._first(db_session)
        llm.answers.append(antwoord(vraag(Q_WENSELIJK, hoort_bij=1)))

        result = await svc.beoordeel_beurt(
            _beurt(sessie_id, KAMERLID_B, mm.turn()), CONTEXT
        )

        assert "(nog geen)" in llm.prompts[1]
        assert "Kamerlid A" not in llm.prompts[1].split("## De spreekbeurt")[0]
        # And a number of someone else's question cannot swallow this one.
        assert result.herhaald == ()
        assert len(result.markering_ids) == 1
        assert len(mm.replies) == 3

    async def test_a_question_asked_again_is_a_vermelding_not_a_thread(
        self, db_session
    ):
        sessie_id, mm, llm, svc, post_a = await self._first(db_session)
        na_eerste = mm.messages[post_a]
        llm.answers.append(antwoord(vraag(Q_CAMPAGNE, hoort_bij=2)))
        opnieuw = self._again(sessie_id, mm)

        result = await svc.beoordeel_beurt(opnieuw, CONTEXT)

        assert result.uitkomst == UITKOMST_GEMARKEERD
        assert result.markering_ids == ()
        assert result.herhaald == (2,)
        assert len(await _markeringen(db_session, sessie_id)) == 2
        assert len(mm.replies) == 2
        assert mm.messages[opnieuw.post_id] == "**Kamerlid A (BBB)** · 11:40"
        assert mm.messages[post_a] == na_eerste

        (vermelding,) = (
            (
                await db_session.execute(
                    select(DebatMarkeringVermelding).where(
                        DebatMarkeringVermelding.sessie_id == sessie_id
                    )
                )
            )
            .scalars()
            .all()
        )
        tweede = (
            await db_session.execute(
                select(DebatMarkering.id).where(
                    DebatMarkering.sessie_id == sessie_id,
                    DebatMarkering.volgnummer == 2,
                )
            )
        ).scalar_one()
        assert vermelding.markering_id == tweede
        assert vermelding.soort == VERMELDING_HERHALING
        assert vermelding.citaat == Q_CAMPAGNE
        assert vermelding.spreker == "Kamerlid A (BBB)"
        assert vermelding.fractie == "BBB"
        assert vermelding.beurt_post_id == opnieuw.post_id
        assert vermelding.beurt_sleutel == opnieuw.sleutel
        assert vermelding.moment == opnieuw.start
        assert vermelding.moment_url == MOMENT_URL

    async def test_new_and_repeated_in_one_turn(self, db_session):
        sessie_id, mm, llm, svc, _ = await self._first(db_session)
        llm.answers.append(
            antwoord(vraag(Q_ARTSEN, hoort_bij=1), vraag(Q_TERMIJNEN, hoort_bij=None))
        )
        opnieuw = self._again(sessie_id, mm)

        result = await svc.beoordeel_beurt(opnieuw, CONTEXT)

        assert result.herhaald == (1,)
        rows = await _markeringen(db_session, sessie_id)
        # The numbering goes on where the debate was.
        assert [(r[0], r[1]) for r in rows][-1] == (3, Q_TERMIJNEN)
        assert mm.messages[opnieuw.post_id] == (
            "**Kamerlid A (BBB)** · 11:40\n\n---\n❓ 1 vraag · open"
        )

    async def test_a_number_the_model_made_up_gives_a_new_question(self, db_session):
        sessie_id, mm, llm, svc, _ = await self._first(db_session)
        llm.answers.append(antwoord(vraag(Q_TERMIJNEN, hoort_bij=17)))

        result = await svc.beoordeel_beurt(self._again(sessie_id, mm), CONTEXT)

        assert result.herhaald == ()
        assert len(result.markering_ids) == 1
        assert len(mm.replies) == 3

    async def test_a_question_that_is_no_longer_open_is_not_offered(self, db_session):
        sessie_id, mm, llm, svc, _ = await self._first(db_session)
        await db_session.execute(
            update(DebatMarkering)
            .where(
                DebatMarkering.sessie_id == sessie_id, DebatMarkering.volgnummer == 1
            )
            .values(status=STATUS_BEANTWOORD)
        )
        llm.answers.append(antwoord(vraag(Q_ARTSEN, hoort_bij=1)))

        result = await svc.beoordeel_beurt(self._again(sessie_id, mm), CONTEXT)

        assert "1. Kamerlid A" not in llm.prompts[1]
        assert "2. Kamerlid A (BBB): Komt er een campagne?" in llm.prompts[1]
        # And an answered question cannot swallow a new one.
        assert result.herhaald == ()
        assert len(result.markering_ids) == 1

    async def test_only_questions_are_offered_as_open_questions(self, db_session):
        """The table will hold other kinds; the list is about questions."""
        sessie_id, mm, llm, svc, _ = await self._first(db_session)
        await db_session.execute(
            update(DebatMarkering)
            .where(
                DebatMarkering.sessie_id == sessie_id, DebatMarkering.volgnummer == 1
            )
            .values(soort=SOORT_TOEZEGGING)
        )

        await svc.beoordeel_beurt(self._again(sessie_id, mm), CONTEXT)

        assert "1. Kamerlid A" not in llm.prompts[1]
        assert "2. Kamerlid A (BBB): Komt er een campagne?" in llm.prompts[1]

    async def test_another_debate_has_its_own_questions_and_numbers(self, db_session):
        _, mm, llm, svc, _ = await self._first(db_session)
        ander = await _sessie(db_session)
        llm.answers.append(antwoord(vraag(Q_TERMIJNEN)))

        await svc.beoordeel_beurt(self._again(ander, mm), CONTEXT)

        assert "(nog geen)" in llm.prompts[1]
        assert [r[0] for r in await _markeringen(db_session, ander)] == [1]

    async def test_of_a_long_list_the_latest_are_kept(self, db_session, monkeypatch):
        sessie_id, mm, llm, svc, _ = await self._first(db_session)
        llm.answers.append(
            antwoord(vraag(Q_TERMIJNEN, samenvatting="Worden de termijnen gehaald?"))
        )
        await svc.beoordeel_beurt(self._again(sessie_id, mm), CONTEXT)
        monkeypatch.setattr(mod, "MAX_OPENSTAAND", 2)

        await svc.beoordeel_beurt(
            _beurt(
                sessie_id,
                KAMERLID_A,
                mm.turn(),
                start=datetime.fromisoformat("2026-10-05T12:10:00+02:00"),
            ),
            CONTEXT,
        )

        open_blok = llm.prompts[2].split("nog openstaan\n")[1].split("\n\n")[0]
        assert open_blok == (
            "2. Kamerlid A (BBB): Komt er een campagne?\n"
            "3. Kamerlid A (BBB): Worden de termijnen gehaald?"
        )


class TestTweeKeerDezelfdeBeurt:
    async def test_the_model_is_asked_once_and_nothing_is_posted_twice(
        self, db_session
    ):
        sessie_id = await _sessie(db_session)
        mm = FakeMattermost()
        # A second answer that would mark something else, if it were asked.
        llm = FakeLLM(antwoord(vraag(Q_ARTSEN)), antwoord(vraag(Q_CAMPAGNE)))
        svc = DebatVraagService(db_session, mm, llm)
        beurt = _beurt(sessie_id, KAMERLID_A, mm.turn())

        eerste = await svc.beoordeel_beurt(beurt, CONTEXT)
        tweede = await svc.beoordeel_beurt(beurt, CONTEXT)

        assert tweede.uitkomst == UITKOMST_AL_BEOORDEELD
        assert tweede.markering_ids == eerste.markering_ids
        assert tweede.threads == 0
        assert len(llm.prompts) == 1
        assert len(mm.replies) == 1
        assert len(mm.updates) == 1
        assert [r[1] for r in await _markeringen(db_session, sessie_id)] == [Q_ARTSEN]

    async def test_also_for_a_turn_that_only_repeated_a_question(self, db_session):
        sessie_id = await _sessie(db_session)
        mm = FakeMattermost()
        llm = FakeLLM(
            antwoord(vraag(Q_ARTSEN)),
            antwoord(vraag(Q_ARTSEN, hoort_bij=1)),
            antwoord(vraag(Q_CAMPAGNE)),
        )
        svc = DebatVraagService(db_session, mm, llm)
        await svc.beoordeel_beurt(_beurt(sessie_id, KAMERLID_A, mm.turn()), CONTEXT)
        later = _beurt(sessie_id, KAMERLID_A, mm.turn())
        eerste = await svc.beoordeel_beurt(later, CONTEXT)
        assert eerste.herhaald == (1,)

        opnieuw = await svc.beoordeel_beurt(later, CONTEXT)

        assert opnieuw.uitkomst == UITKOMST_AL_BEOORDEELD
        assert opnieuw.markering_ids == ()
        assert len(llm.prompts) == 2
        vermeldingen = (
            await db_session.execute(
                select(func.count(DebatMarkeringVermelding.id)).where(
                    DebatMarkeringVermelding.sessie_id == sessie_id
                )
            )
        ).scalar()
        assert vermeldingen == 1

    async def test_the_same_post_in_another_debate_is_another_turn(self, db_session):
        een, twee = await _sessie(db_session), await _sessie(db_session)
        mm = FakeMattermost()
        llm = FakeLLM(antwoord(vraag(Q_ARTSEN)), antwoord(vraag(Q_ARTSEN)))
        svc = DebatVraagService(db_session, mm, llm)
        post_id = mm.turn()

        await svc.beoordeel_beurt(_beurt(een, KAMERLID_A, post_id), CONTEXT)
        result = await svc.beoordeel_beurt(_beurt(twee, KAMERLID_A, post_id), CONTEXT)

        assert result.uitkomst == UITKOMST_GEMARKEERD
        assert len(llm.prompts) == 2


class TestHetModelFaalt:
    async def test_an_unreachable_model_stores_nothing_and_can_be_retried(
        self, db_session
    ):
        sessie_id = await _sessie(db_session)
        mm = FakeMattermost()
        llm = FakeLLM(ConnectionError("geen verbinding"), antwoord(vraag(Q_ARTSEN)))
        svc = DebatVraagService(db_session, mm, llm)
        beurt = _beurt(sessie_id, KAMERLID_A, mm.turn())

        result = await svc.beoordeel_beurt(beurt, CONTEXT)

        assert result.uitkomst == UITKOMST_LLM_ONBEREIKBAAR
        assert result.opnieuw_proberen is True
        assert await _markeringen(db_session, sessie_id) == []
        assert (mm.replies, mm.updates) == ([], [])

        # Not remembered as judged: the next call asks again.
        opnieuw = await svc.beoordeel_beurt(beurt, CONTEXT)
        assert opnieuw.uitkomst == UITKOMST_GEMARKEERD
        assert len(mm.replies) == 1

    async def test_an_unusable_answer_stores_nothing_and_is_not_worth_a_retry(
        self, db_session
    ):
        sessie_id = await _sessie(db_session)
        mm, llm = FakeMattermost(), FakeLLM("geen json", "nog steeds niet")

        result = await DebatVraagService(db_session, mm, llm).beoordeel_beurt(
            _beurt(sessie_id, KAMERLID_A, mm.turn()), CONTEXT
        )

        assert result.uitkomst == UITKOMST_LLM_ONBRUIKBAAR
        assert result.opnieuw_proberen is False
        assert await _markeringen(db_session, sessie_id) == []
        assert (mm.replies, mm.updates) == ([], [])


class TestMattermostFaalt:
    async def _twee_vragen(self, db_session):
        sessie_id = await _sessie(db_session)
        mm = FakeMattermost()
        llm = FakeLLM(antwoord(vraag(Q_ARTSEN), vraag(Q_CAMPAGNE)))
        svc = DebatVraagService(db_session, mm, llm)
        post_id = mm.turn("kop")
        return sessie_id, mm, llm, svc, post_id

    async def test_a_thread_that_fails_does_not_look_posted(self, db_session):
        sessie_id, mm, _, svc, post_id = await self._twee_vragen(db_session)
        mm.fail_sends = 2

        result = await svc.beoordeel_beurt(
            _beurt(sessie_id, KAMERLID_A, post_id), CONTEXT
        )

        # The questions are kept, but nothing says they are in the channel.
        assert result.uitkomst == UITKOMST_GEMARKEERD
        assert result.threads == 0
        rows = await _markeringen(db_session, sessie_id)
        assert [(r[2], r[3], r[4]) for r in rows] == [(None, 1, None)] * 2
        assert mm.messages[post_id] == "kop"
        assert (mm.updates, mm.reads) == ([], [])
        assert await statusblok_voor_post(db_session, post_id) == ""

    async def test_the_next_turn_posts_what_was_left(self, db_session):
        sessie_id, mm, llm, svc, post_id = await self._twee_vragen(db_session)
        mm.fail_sends = 2
        await svc.beoordeel_beurt(_beurt(sessie_id, KAMERLID_A, post_id), CONTEXT)

        # Any turn of a next round will do, also one that is not judged
        # itself.
        svc.nieuwe_ronde()
        result = await svc.beoordeel_beurt(
            _beurt(sessie_id, VOORZITTER, mm.turn()), CONTEXT
        )

        assert result.uitkomst == UITKOMST_OVERGESLAGEN
        assert result.threads == 2
        assert len(llm.prompts) == 1
        assert [root for _, root, _, _ in mm.replies] == [post_id, post_id]
        # In the order they were asked.
        assert Q_ARTSEN in mm.replies[0][2]
        assert Q_CAMPAGNE in mm.replies[1][2]
        rows = await _markeringen(db_session, sessie_id)
        assert all(r[2] and r[4] for r in rows)
        assert mm.messages[post_id] == ("kop\n\n---\n❓ 2 vragen · open")

    async def test_a_thread_that_raises_is_a_thread_that_fails(self, db_session):
        sessie_id, mm, _, svc, post_id = await self._twee_vragen(db_session)
        mm.raise_sends = 1

        result = await svc.beoordeel_beurt(
            _beurt(sessie_id, KAMERLID_A, post_id), CONTEXT
        )

        assert result.threads == 1
        rows = await _markeringen(db_session, sessie_id)
        assert [bool(r[2]) for r in rows] == [False, True]
        assert rows[0][3] == 1

    async def test_the_status_line_counts_only_what_is_in_the_channel(self, db_session):
        sessie_id, mm, _, svc, post_id = await self._twee_vragen(db_session)
        mm.fail_sends = 1

        await svc.beoordeel_beurt(_beurt(sessie_id, KAMERLID_A, post_id), CONTEXT)
        assert mm.messages[post_id] == "kop\n\n---\n❓ 1 vraag · open"

        # The retry posts the other one and corrects the line.
        svc.nieuwe_ronde()
        await svc.beoordeel_beurt(_beurt(sessie_id, VOORZITTER, mm.turn()), CONTEXT)
        assert mm.messages[post_id] == ("kop\n\n---\n❓ 2 vragen · open")
        assert len(mm.replies) == 2

    async def test_after_three_failures_a_thread_is_left_alone(self, db_session):
        sessie_id, mm, _, svc, post_id = await self._twee_vragen(db_session)
        mm.fail_sends = 100
        await svc.beoordeel_beurt(_beurt(sessie_id, KAMERLID_A, post_id), CONTEXT)
        for _ in range(4):
            svc.nieuwe_ronde()
            await svc.beoordeel_beurt(_beurt(sessie_id, VOORZITTER, None), CONTEXT)

        rows = await _markeringen(db_session, sessie_id)
        assert [r[3] for r in rows] == [mod.MAX_POST_POGINGEN] * 2
        # Two questions, three attempts each, and then no more.
        assert mm.fail_sends == 100 - 2 * mod.MAX_POST_POGINGEN

    async def test_one_round_is_one_attempt_however_many_turns(self, db_session):
        """Otherwise a Mattermost that is away for one round uses up every
        attempt, and the threads never come."""
        sessie_id, mm, _, svc, post_id = await self._twee_vragen(db_session)
        mm.fail_sends = 100
        await svc.beoordeel_beurt(_beurt(sessie_id, KAMERLID_A, post_id), CONTEXT)
        for _ in range(5):
            await svc.beoordeel_beurt(_beurt(sessie_id, VOORZITTER, None), CONTEXT)

        rows = await _markeringen(db_session, sessie_id)
        assert [r[3] for r in rows] == [1, 1]

    async def test_a_thread_of_another_debate_is_left_to_that_debate(self, db_session):
        sessie_id, mm, _, svc, post_id = await self._twee_vragen(db_session)
        mm.fail_sends = 2
        await svc.beoordeel_beurt(_beurt(sessie_id, KAMERLID_A, post_id), CONTEXT)
        ander = await _sessie(db_session)

        result = await svc.beoordeel_beurt(_beurt(ander, VOORZITTER, None), CONTEXT)

        assert result.threads == 0
        assert mm.replies == []

    async def test_a_turn_without_a_message_is_recorded_but_not_posted(
        self, db_session
    ):
        sessie_id = await _sessie(db_session)
        mm = FakeMattermost()
        llm = FakeLLM(antwoord(vraag(Q_ARTSEN)))
        svc = DebatVraagService(db_session, mm, llm)

        result = await svc.beoordeel_beurt(_beurt(sessie_id, KAMERLID_A, None), CONTEXT)
        await svc.beoordeel_beurt(_beurt(sessie_id, VOORZITTER, None), CONTEXT)

        assert result.uitkomst == UITKOMST_GEMARKEERD
        assert result.threads == 0
        rows = await _markeringen(db_session, sessie_id)
        assert [(r[1], r[2], r[3]) for r in rows] == [(Q_ARTSEN, None, 0)]
        assert (mm.replies, mm.updates, mm.reads) == ([], [], [])


class TestDeStatusregel:
    async def _een_vraag(self, db_session, body="kop\neen zin."):
        sessie_id = await _sessie(db_session)
        mm = FakeMattermost()
        svc = DebatVraagService(db_session, mm, FakeLLM(antwoord(vraag(Q_ARTSEN))))
        post_id = mm.turn(body)
        return sessie_id, mm, svc, post_id

    async def test_a_message_that_cannot_be_read_is_tried_again(self, db_session):
        sessie_id, mm, svc, post_id = await self._een_vraag(db_session)
        mm.fail_reads = 1

        await svc.beoordeel_beurt(_beurt(sessie_id, KAMERLID_A, post_id), CONTEXT)
        assert mm.updates == []
        assert (await _markeringen(db_session, sessie_id))[0][4] is None

        svc.nieuwe_ronde()
        await svc.beoordeel_beurt(_beurt(sessie_id, VOORZITTER, None), CONTEXT)
        assert mm.messages[post_id].endswith("❓ 1 vraag · open")
        assert (await _markeringen(db_session, sessie_id))[0][4] is not None
        # The thread itself is not posted again.
        assert len(mm.replies) == 1

    async def test_a_line_of_another_debate_is_left_to_that_debate(self, db_session):
        sessie_id, mm, svc, post_id = await self._een_vraag(db_session)
        mm.fail_reads = 1
        await svc.beoordeel_beurt(_beurt(sessie_id, KAMERLID_A, post_id), CONTEXT)
        ander = await _sessie(db_session)

        await svc.beoordeel_beurt(_beurt(ander, VOORZITTER, None), CONTEXT)

        assert mm.reads == [post_id]
        assert mm.updates == []

    async def test_a_write_that_fails_is_tried_again(self, db_session):
        sessie_id, mm, svc, post_id = await self._een_vraag(db_session)
        mm.fail_updates = 1

        await svc.beoordeel_beurt(_beurt(sessie_id, KAMERLID_A, post_id), CONTEXT)
        assert mm.messages[post_id] == "kop\neen zin."
        assert (await _markeringen(db_session, sessie_id))[0][4] is None

        svc.nieuwe_ronde()
        await svc.beoordeel_beurt(_beurt(sessie_id, VOORZITTER, None), CONTEXT)
        assert mm.messages[post_id].endswith("❓ 1 vraag · open")

    async def test_a_message_that_is_gone_is_not_tried_forever(self, db_session):
        sessie_id, mm, svc, post_id = await self._een_vraag(db_session)
        mm.gone.add(post_id)

        await svc.beoordeel_beurt(_beurt(sessie_id, KAMERLID_A, post_id), CONTEXT)
        await svc.beoordeel_beurt(_beurt(sessie_id, VOORZITTER, None), CONTEXT)

        assert mm.updates == []
        assert mm.reads == [post_id]

    async def test_once_written_it_is_not_written_or_read_again(self, db_session):
        sessie_id, mm, svc, post_id = await self._een_vraag(db_session)
        await svc.beoordeel_beurt(_beurt(sessie_id, KAMERLID_A, post_id), CONTEXT)
        await svc.beoordeel_beurt(_beurt(sessie_id, VOORZITTER, None), CONTEXT)
        assert (len(mm.updates), mm.reads) == (1, [post_id])

    async def test_a_line_that_is_already_right_is_not_written(self, db_session):
        sessie_id, mm, svc, post_id = await self._een_vraag(
            db_session, "kop\n\n---\n❓ 1 vraag · open"
        )
        await svc.beoordeel_beurt(_beurt(sessie_id, KAMERLID_A, post_id), CONTEXT)
        assert mm.updates == []
        assert (await _markeringen(db_session, sessie_id))[0][4] is not None

    async def test_the_transcript_that_is_in_the_message_now_is_kept(self, db_session):
        """The status line is put on the message as it is at that moment,
        not as it was when the turn was handed in."""
        sessie_id, mm, svc, post_id = await self._een_vraag(db_session)
        mm.fail_reads = 1
        await svc.beoordeel_beurt(_beurt(sessie_id, KAMERLID_A, post_id), CONTEXT)
        mm.messages[post_id] = met_body(mm.messages[post_id], "kop\neen zin. En meer.")

        svc.nieuwe_ronde()
        await svc.beoordeel_beurt(_beurt(sessie_id, VOORZITTER, None), CONTEXT)

        assert mm.messages[post_id] == (
            "kop\neen zin. En meer.\n\n---\n❓ 1 vraag · open"
        )

    async def test_the_props_of_the_message_are_kept(self, db_session):
        sessie_id, mm, svc, post_id = await self._een_vraag(db_session)
        mm.props[post_id] = {"debat_spreekbeurt": "abc"}
        await svc.beoordeel_beurt(_beurt(sessie_id, KAMERLID_A, post_id), CONTEXT)
        assert mm.update_props == [{"debat_spreekbeurt": "abc"}]

    async def test_the_block_for_whoever_rewrites_the_message(self, db_session):
        sessie_id, mm, svc, post_id = await self._een_vraag(db_session)
        await svc.beoordeel_beurt(_beurt(sessie_id, KAMERLID_A, post_id), CONTEXT)
        assert await statusblok_voor_post(db_session, post_id) == ("❓ 1 vraag · open")
        assert await statusblok_voor_post(db_session, "ander") == ""


# --- when in the turn the question was asked ---------------------------

A_START = datetime.fromisoformat(KAMERLID_A["start"])


def _lines_at(tekst: str, cuts: dict[str, float]) -> tuple[Line, ...]:
    """The text of Kamerlid A as subtitle lines, a new one where each of
    `cuts` begins, that many seconds into the turn."""
    marks = sorted((tekst.index(begin), seconds) for begin, seconds in cuts.items())
    lines = [Line(A_START + timedelta(seconds=1), tekst[: marks[0][0]])]
    for n, (at, seconds) in enumerate(marks):
        end = marks[n + 1][0] if n + 1 < len(marks) else len(tekst)
        lines.append(Line(A_START + timedelta(seconds=seconds), tekst[at:end]))
    return tuple(lines)


def _link(seconds: float) -> str:
    at = (A_START + timedelta(seconds=seconds)).strftime("%H%%3A%M%%3A%S")
    return f"https://debatdirect.example/debat?event=speaker2026-10-05T{at}%2B0200"


class TestHetMomentVanDeVraag:
    TEKST = KAMERLID_A["tekst"]
    # 10:02:23 plus these: 10:07:23, 10:10:43 and 10:13:13.
    LINES = _lines_at(
        TEKST,
        {
            "Klopt het dat wordt bezuinigd": 300,
            "Worden die termijnen": 500,
            "Is de minister bereid om toe te zeggen": 650,
        },
    )

    async def _ask(self, db_session, *vragen: dict, **beurt):
        sessie_id = await _sessie(db_session)
        mm = FakeMattermost()
        svc = DebatVraagService(db_session, mm, FakeLLM(antwoord(*vragen)))
        values = {"lines": self.LINES, **beurt}
        await svc.beoordeel_beurt(
            _beurt(sessie_id, KAMERLID_A, mm.turn(), **values), CONTEXT
        )
        moments = (
            (
                await db_session.execute(
                    select(DebatMarkering.vraag_moment)
                    .where(DebatMarkering.sessie_id == sessie_id)
                    .order_by(DebatMarkering.volgnummer)
                )
            )
            .scalars()
            .all()
        )
        return moments, [text.split("\n")[1] for _, _, text, _ in mm.replies]

    async def test_each_question_gets_the_moment_of_the_line_it_begins_in(
        self, db_session
    ):
        moments, regels = await self._ask(
            db_session, vraag(Q_ARTSEN), vraag(Q_CAMPAGNE)
        )

        assert moments == [
            A_START + timedelta(seconds=300),
            A_START + timedelta(seconds=650),
        ]
        # The time of the question, and a link that opens 5 seconds before.
        assert regels == [
            f"Vraag 1 · aan de minister · [10:07]({_link(295)})",
            f"Vraag 2 · aan de minister · [10:13]({_link(645)})",
        ]

    async def test_a_quote_the_model_repaired_is_found_where_it_stands(
        self, db_session
    ):
        repaired = Q_CAMPAGNE.replace("PTSD-gerealiteerde", "PTSS-gerelateerde")
        assert repaired not in self.TEKST

        moments, _ = await self._ask(db_session, vraag(repaired))

        assert moments == [A_START + timedelta(seconds=650)]

    async def test_a_quote_in_pieces_has_the_moment_of_its_first_piece(
        self, db_session
    ):
        moments, _ = await self._ask(
            db_session,
            vraag(
                "Klopt het dat wordt bezuinigd [...] "
                "Worden die termijnen daadwerkelijk gehaald?"
            ),
        )

        assert moments == [A_START + timedelta(seconds=300)]

    async def test_a_quote_that_begins_halfway_a_line(self, db_session):
        moments, _ = await self._ask(db_session, vraag(Q_TERMIJNEN[7:]))

        assert moments == [A_START + timedelta(seconds=500)]

    async def test_without_lines_the_time_is_the_start_of_the_turn(self, db_session):
        moments, regels = await self._ask(db_session, vraag(Q_ARTSEN), lines=())

        assert moments == [None]
        assert regels == [
            f"Vraag 1 · aan de minister · [10:02]({MOMENT_URL})"
            " (begin van de spreekbeurt)"
        ]

    async def test_lines_that_are_not_the_text_of_the_turn_are_not_used(
        self, db_session
    ):
        """A line moved to the next turn after the text was read."""
        moments, regels = await self._ask(
            db_session, vraag(Q_ARTSEN), lines=self.LINES[:-1]
        )

        assert moments == [None]
        assert regels[0].endswith("(begin van de spreekbeurt)")

    async def test_a_line_from_before_the_turn_is_the_start_of_the_turn(
        self, db_session
    ):
        """The voices can give a turn a line from just before its event."""
        early = (Line(A_START - timedelta(seconds=4), self.TEKST),)

        moments, regels = await self._ask(db_session, vraag(Q_ARTSEN), lines=early)

        assert moments == [A_START]
        # The moment is known, so nothing is said about it.
        assert regels == [f"Vraag 1 · aan de minister · [10:02]({MOMENT_URL})"]

    async def test_a_thread_posted_later_says_the_same_moment(self, db_session):
        sessie_id = await _sessie(db_session)
        mm = FakeMattermost()
        mm.fail_sends = 1
        svc = DebatVraagService(db_session, mm, FakeLLM(antwoord(vraag(Q_ARTSEN))))
        beurt = _beurt(sessie_id, KAMERLID_A, mm.turn(), lines=self.LINES)
        await svc.beoordeel_beurt(beurt, CONTEXT)
        assert mm.replies == []

        # Another service, long after: nothing but the row to go by.
        await DebatVraagService(db_session, mm, FakeLLM())._haal_achterstand_in(
            sessie_id
        )

        assert mm.replies[0][2].split("\n")[1] == (
            f"Vraag 1 · aan de minister · [10:07]({_link(295)})"
        )


class TestDeNootStaatEenKeerInDeDraad:
    """That the quotes are literal is said under the first reply that got
    into the thread, whichever question that is."""

    async def _twee(self, db_session, fail_sends: int = 0):
        sessie_id = await _sessie(db_session)
        mm = FakeMattermost()
        mm.fail_sends = fail_sends
        svc = DebatVraagService(
            db_session, mm, FakeLLM(antwoord(vraag(Q_ARTSEN), vraag(Q_CAMPAGNE)))
        )
        post_id = mm.turn("kop")
        await svc.beoordeel_beurt(_beurt(sessie_id, KAMERLID_A, post_id), CONTEXT)
        return sessie_id, mm, svc, post_id

    @staticmethod
    def _notes(mm) -> list[bool]:
        return [NOOT in text for _, _, text, _ in mm.replies]

    async def test_two_questions_posted_in_one_call(self, db_session):
        _, mm, _, _ = await self._twee(db_session)

        assert self._notes(mm) == [True, False]
        assert mm.replies[0][2].endswith(f"\n\n{NOOT}")
        assert mm.replies[1][2].endswith(f"> {Q_CAMPAGNE}")

    async def test_when_the_first_post_fails_the_second_question_carries_it(
        self, db_session
    ):
        sessie_id, mm, svc, _ = await self._twee(db_session, fail_sends=1)

        assert [text.split("\n")[1][:7] for _, _, text, _ in mm.replies] == ["Vraag 2"]
        assert self._notes(mm) == [True]

        # The first question comes in later, under a thread that has it.
        svc.nieuwe_ronde()
        await svc._haal_achterstand_in(sessie_id)

        assert [text.split("\n")[1][:7] for _, _, text, _ in mm.replies] == [
            "Vraag 2",
            "Vraag 1",
        ]
        assert self._notes(mm) == [True, False]

    async def test_when_both_fail_the_first_to_get_in_carries_it(self, db_session):
        sessie_id, mm, svc, _ = await self._twee(db_session, fail_sends=2)
        assert mm.replies == []

        svc.nieuwe_ronde()
        await svc._haal_achterstand_in(sessie_id)

        assert self._notes(mm) == [True, False]

    async def test_a_post_that_raises_leaves_the_note_for_the_next(self, db_session):
        sessie_id = await _sessie(db_session)
        mm = FakeMattermost()
        mm.raise_sends = 1
        svc = DebatVraagService(
            db_session, mm, FakeLLM(antwoord(vraag(Q_ARTSEN), vraag(Q_CAMPAGNE)))
        )

        await svc.beoordeel_beurt(_beurt(sessie_id, KAMERLID_A, mm.turn()), CONTEXT)

        assert self._notes(mm) == [True]

    async def test_every_thread_has_its_own(self, db_session):
        sessie_id, mm, svc, post_id = await self._twee(db_session)
        svc.llm.answers.append(antwoord(vraag(Q_WENSELIJK)))
        ander = mm.turn("kop van een ander")

        await svc.beoordeel_beurt(_beurt(sessie_id, KAMERLID_B, ander), CONTEXT)

        assert [root for _, root, _, _ in mm.replies] == [post_id, post_id, ander]
        assert self._notes(mm) == [True, False, True]

    async def test_a_question_of_another_debate_under_another_message_does_not_count(
        self, db_session
    ):
        await self._twee(db_session)
        _, mm, _, _ = await self._twee(db_session)

        assert self._notes(mm) == [True, False]


# --- real sessions: what commits, and what two workers do --------------


@pytest.fixture
async def real(_test_engine):
    """Sessions that really commit, and a debate that is cleaned up after.

    `db_session` is one connection in one transaction: it cannot show what
    another session sees, and a row it locks is never locked for itself.
    """
    sessions: list[AsyncSession] = []
    sessie_ids: list[uuid.UUID] = []

    def new_session() -> AsyncSession:
        session = AsyncSession(bind=_test_engine, expire_on_commit=False)
        sessions.append(session)
        return session

    async def new_sessie() -> uuid.UUID:
        session = new_session()
        sessie_id = await _sessie(session)
        await session.commit()
        sessie_ids.append(sessie_id)
        return sessie_id

    try:
        yield new_session, new_sessie
    finally:
        for session in sessions:
            await session.rollback()
            await session.close()
        cleanup = AsyncSession(bind=_test_engine)
        await cleanup.execute(delete(DebatSessie).where(DebatSessie.id.in_(sessie_ids)))
        await cleanup.commit()
        await cleanup.close()


class TestRealSessions:
    async def test_what_is_posted_is_committed(self, real):
        new_session, new_sessie = real
        sessie_id = await new_sessie()
        mm = FakeMattermost()
        svc = DebatVraagService(new_session(), mm, FakeLLM(antwoord(vraag(Q_ARTSEN))))

        await svc.beoordeel_beurt(_beurt(sessie_id, KAMERLID_A, mm.turn()), CONTEXT)

        # Without a commit by the caller, another session sees all of it.
        rows = await _markeringen(new_session(), sessie_id)
        assert [(r[1], r[2]) for r in rows] == [(Q_ARTSEN, mm.replies[0][3])]
        assert rows[0][4] is not None

    async def test_the_post_id_is_committed_before_the_status_line(self, real):
        """A crash while the status line is written must not lose the
        thread: the next start would post it a second time."""
        new_session, new_sessie = real
        sessie_id = await new_sessie()
        mm = FakeMattermost()
        andere = new_session()
        seen: list = []

        async def get_post(post_id):
            seen.extend(await _markeringen(andere, sessie_id))
            raise RuntimeError("valt om tijdens de statusregel")

        mm.get_post = get_post
        svc = DebatVraagService(new_session(), mm, FakeLLM(antwoord(vraag(Q_ARTSEN))))

        await svc.beoordeel_beurt(_beurt(sessie_id, KAMERLID_A, mm.turn()), CONTEXT)

        assert [r[2] for r in seen] == [mm.replies[0][3]]

    async def test_two_workers_post_a_thread_once(self, real):
        new_session, new_sessie = real
        sessie_id = await new_sessie()
        mm = FakeMattermost()
        mm.fail_sends = 1
        llm = FakeLLM(antwoord(vraag(Q_ARTSEN)))
        een = DebatVraagService(new_session(), mm, llm)
        twee = DebatVraagService(new_session(), mm, llm)
        result = await een.beoordeel_beurt(
            _beurt(sessie_id, KAMERLID_A, mm.turn()), CONTEXT
        )
        (markering_id,) = result.markering_ids
        assert mm.replies == []

        # Worker one is in the middle of posting, holding the row...
        mm.gate = asyncio.Event()
        mm.sending.clear()
        bezig = asyncio.create_task(een._post_thread(markering_id))
        await asyncio.wait_for(mm.sending.wait(), timeout=5)
        # ...when worker two comes by for the same thread.
        mm.sending.clear()
        # Does not wait for worker one either: a tick must not hang on it.
        assert (
            await asyncio.wait_for(twee._post_thread(markering_id), timeout=5) is False
        )
        assert not mm.sending.is_set()

        mm.gate.set()
        assert await asyncio.wait_for(bezig, timeout=5) is True
        assert len(mm.replies) == 1
        # And afterwards it is simply posted, for everyone.
        assert await twee._post_thread(markering_id) is False
        assert len(mm.replies) == 1

    async def test_two_workers_under_one_message_leave_one_note(self, real):
        """Two questions of one turn, each posted by another worker at the
        same moment: both would find the thread empty and both would put
        the note about the transcript under their reply."""
        new_session, new_sessie = real
        sessie_id = await new_sessie()
        mm = FakeMattermost()
        mm.fail_sends = 2
        llm = FakeLLM(antwoord(vraag(Q_ARTSEN), vraag(Q_CAMPAGNE)))
        een = DebatVraagService(new_session(), mm, llm)
        twee = DebatVraagService(new_session(), mm, llm)
        result = await een.beoordeel_beurt(
            _beurt(sessie_id, KAMERLID_A, mm.turn()), CONTEXT
        )
        eerste, tweede = result.markering_ids
        assert mm.replies == []

        # Worker one is in the middle of posting the first question...
        mm.gate = asyncio.Event()
        mm.sending.clear()
        bezig = asyncio.create_task(een._post_thread(eerste))
        await asyncio.wait_for(mm.sending.wait(), timeout=5)
        # ...when worker two comes by for the second, under the same message.
        mm.sending.clear()
        # It does not post, and does not wait: a tick must not hang on it.
        assert await asyncio.wait_for(twee._post_thread(tweede), timeout=5) is False
        assert not mm.sending.is_set()

        mm.gate.set()
        assert await asyncio.wait_for(bezig, timeout=5) is True
        # Not counted as a failure, and posted the next time round.
        rows = await _markeringen(new_session(), sessie_id)
        assert [r[3] for r in rows] == [1, 1]
        assert await twee._post_thread(tweede) is True
        assert [NOOT in text for _, _, text, _ in mm.replies] == [True, False]

    async def test_two_workers_under_two_messages_do_not_wait_for_each_other(
        self, real
    ):
        new_session, new_sessie = real
        sessie_id = await new_sessie()
        mm = FakeMattermost()
        # Nothing gets in at first, whoever tries and however often.
        mm.fail_sends = 10
        een = DebatVraagService(new_session(), mm, FakeLLM(antwoord(vraag(Q_ARTSEN))))
        twee = DebatVraagService(
            new_session(), mm, FakeLLM(antwoord(vraag(Q_WENSELIJK)))
        )
        (eerste,) = (
            await een.beoordeel_beurt(_beurt(sessie_id, KAMERLID_A, mm.turn()), CONTEXT)
        ).markering_ids
        (tweede,) = (
            await twee.beoordeel_beurt(
                _beurt(sessie_id, KAMERLID_B, mm.turn()), CONTEXT
            )
        ).markering_ids
        assert mm.replies == []
        mm.fail_sends = 0

        mm.gate = asyncio.Event()
        mm.sending.clear()
        bezig = asyncio.create_task(een._post_thread(eerste))
        await asyncio.wait_for(mm.sending.wait(), timeout=5)
        ander = asyncio.create_task(twee._post_thread(tweede))
        await asyncio.sleep(0.2)
        mm.gate.set()

        assert await asyncio.wait_for(bezig, timeout=5) is True
        assert await asyncio.wait_for(ander, timeout=5) is True
        assert [NOOT in text for _, _, text, _ in mm.replies] == [True, True]

    async def test_two_workers_store_a_turn_once(self, real):
        new_session, new_sessie = real
        sessie_id = await new_sessie()
        mm = FakeMattermost()
        beurt = _beurt(sessie_id, KAMERLID_A, mm.turn())
        een = DebatVraagService(new_session(), mm, FakeLLM(antwoord(vraag(Q_ARTSEN))))
        twee = DebatVraagService(
            new_session(), mm, FakeLLM(antwoord(vraag(Q_CAMPAGNE)))
        )

        # Both asked the model, both come to store what it said.
        results = await asyncio.gather(
            een.beoordeel_beurt(beurt, CONTEXT), twee.beoordeel_beurt(beurt, CONTEXT)
        )

        assert sorted(r.uitkomst for r in results) == [
            UITKOMST_AL_BEOORDEELD,
            UITKOMST_GEMARKEERD,
        ]
        assert results[0].markering_ids == results[1].markering_ids
        assert len(await _markeringen(new_session(), sessie_id)) == 1
        assert len(mm.replies) == 1

    async def test_two_turns_at_once_get_their_own_numbers(self, real):
        new_session, new_sessie = real
        sessie_id = await new_sessie()
        mm = FakeMattermost()
        een = DebatVraagService(
            new_session(), mm, FakeLLM(antwoord(vraag(Q_ARTSEN), vraag(Q_CAMPAGNE)))
        )
        twee = DebatVraagService(
            new_session(), mm, FakeLLM(antwoord(vraag(Q_WENSELIJK), vraag(Q_LOKET)))
        )

        await asyncio.gather(
            een.beoordeel_beurt(_beurt(sessie_id, KAMERLID_A, mm.turn()), CONTEXT),
            twee.beoordeel_beurt(_beurt(sessie_id, KAMERLID_B, mm.turn()), CONTEXT),
        )

        rows = await _markeringen(new_session(), sessie_id)
        assert [r[0] for r in rows] == [1, 2, 3, 4]
        assert len(mm.replies) == 4

    async def test_a_debate_that_is_gone_stores_nothing(self, real):
        new_session, _ = real
        mm = FakeMattermost()
        svc = DebatVraagService(new_session(), mm, FakeLLM(antwoord(vraag(Q_ARTSEN))))

        result = await svc.beoordeel_beurt(
            _beurt(uuid.uuid4(), KAMERLID_A, mm.turn()), CONTEXT
        )

        assert result.uitkomst == UITKOMST_AL_BEOORDEELD
        assert result.markering_ids == ()
        assert mm.replies == []
