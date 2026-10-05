"""Marking questions: what is the bewindspersoon asked in this debate.

When a turn at speaking is finished, the transcription hands it to
`DebatVraagService.beoordeel_beurt`. A model reads that one turn, with what
is known about the debate and the list of questions that are still open,
and says which questions to the bewindspersoon are in it. Each new question
is recorded, becomes a reply under the message of the turn, and shows up in
the status line of that message.

A question is a state, not an event. The model has no memory of the debate;
the table has. Every call gets the open questions of the speaker as a short
list, and a question they ask again becomes a vermelding on the row that is
there instead of a second thread.

Order of work, and why:

1. The answer of the model is stored in one commit, threads not yet posted.
   From then on the turn counts as judged: a second call for the same turn
   does not ask the model again, so it cannot mark other questions.
2. Each thread is posted while its row is locked, and the post id is
   committed before anything else happens. A post that fails leaves the row
   without a thread, and the next call tries it again.
3. The status line counts only questions that have a thread, and is written
   last. It is derived from the table, so writing it twice is harmless.

The service commits. It never rolls back: nothing is left half done between
two commits, and a rollback would expire what the caller holds.
"""

from __future__ import annotations

import difflib
import logging
import re
import unicodedata
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.debat_markering import (
    SOORT_VRAAG,
    STATUS_OPEN,
    VERMELDING_HERHALING,
    DebatMarkering,
    DebatMarkeringVermelding,
)
from bouwmeester.models.debat_sessie import DebatSessie
from bouwmeester.services import debat_direct as dd
from bouwmeester.services.debat_kanaal_service import AMSTERDAM
from bouwmeester.services.debat_statusregel import (
    ICOON_VRAAG,
    met_status,
    statusregel,
)
from bouwmeester.services.llm.base import (
    DEBAT_VRAGEN_ONBEREIKBAAR,
    BaseLLMService,
    DebatVraag,
)
from bouwmeester.services.mattermost_service import (
    MattermostService,
    PostNotFoundError,
)
from bouwmeester.services.mattermost_utils import (
    escape_mattermost_prose as _escape,
)
from bouwmeester.services.tk_activiteit import Activiteit, Bewindspersoon

logger = logging.getLogger(__name__)

SOORT_SPEAKER = dd.EVENT_SPEAKER
SOORT_INTERRUPTER = dd.EVENT_INTERRUPTER
SOORT_CHAIRMAN = "chairman"

# A turn shorter than this is not sent to the model: "Dank u wel,
# voorzitter." is not a question to anyone.
MIN_WOORDEN = 5
# How many of the speaker's own open questions the model gets, newest first.
MAX_OPENSTAAND = 20
# How often posting a thread is tried before it is left alone.
MAX_POST_POGINGEN = 3
MAX_CITAAT = 600
MAX_SAMENVATTING = 240
MAX_GERICHT_AAN = 80

UITKOMST_OVERGESLAGEN = "overgeslagen"
UITKOMST_AL_BEOORDEELD = "al_beoordeeld"
UITKOMST_GEEN_VRAAG = "geen_vraag"
UITKOMST_GEMARKEERD = "gemarkeerd"
# Nothing was judged and nothing was stored: calling again later is useful.
UITKOMST_LLM_ONBEREIKBAAR = "llm_onbereikbaar"
# The model answered, but not with something readable. Not stored either;
# calling again will most likely give the same.
UITKOMST_LLM_ONBRUIKBAAR = "llm_onbruikbaar"

_TITEL_BEWINDSPERSOON = ("minister", "staatssecretaris")
# What `gericht_aan` has to name for a question to count. The model is asked
# for questions to the bewindspersoon only, and still hands in one to the
# initiatiefnemers now and then, honestly labelled as such.
_AAN_BEWINDSPERSOON = (
    "minister",
    "staatssecretaris",
    "kabinet",
    "regering",
    "bewindsperso",
    "premier",
)


@dataclass(frozen=True)
class Beurt:
    """One finished turn at speaking, as the transcription hands it over."""

    sessie_id: uuid.UUID
    # Row in `debat_spreekbeurt`, if known.
    spreekbeurt_id: uuid.UUID | None
    # The Mattermost message of this turn. The thread hangs under it.
    post_id: str | None
    channel_id: str
    # "speaker" | "interrupter" | "chairman"
    soort: str
    # Display label, such as "Kamerlid A (CDA)".
    spreker: str
    fractie: str | None
    # Start of the turn, timezone-aware.
    start: datetime
    # Link to this moment in the broadcast.
    moment_url: str | None
    tekst: str
    # A turn by the bewindspersoon holds answers, not questions. See
    # `is_bewindspersoon` for how to tell from a Debat Direct speaker.
    is_bewindspersoon: bool = False
    # For an interruption: the label of whoever had the floor, if known.
    # "Bent u het daarmee eens?" is a question to that person, and only a
    # question to the bewindspersoon when that person is the bewindspersoon.
    onderbroken: str | None = None
    onderbroken_is_bewindspersoon: bool = False

    @property
    def sleutel(self) -> str:
        """What makes this turn this turn, for "was it judged already"."""
        if self.spreekbeurt_id is not None:
            return f"beurt:{self.spreekbeurt_id}"
        if self.post_id:
            return f"post:{self.post_id}"
        return f"tijd:{self.start.astimezone(UTC).isoformat()}|{self.spreker}"[:255]


@dataclass(frozen=True)
class DebatContext:
    """What is known about a debate before it starts."""

    onderwerp: str
    # Kind of meeting: "Commissiedebat", "Notaoverleg", "Plenair debat".
    soort: str | None = None
    bewindspersonen: tuple[Bewindspersoon, ...] = ()
    # Titles of the agenda documents.
    stukken: tuple[str, ...] = ()
    # Whether members of parliament sit next to the bewindspersoon to
    # answer questions themselves: the debate is about their initiatiefnota
    # or initiatiefwet. Half of the questions then go to them.
    initiatiefnemers: bool = False

    @classmethod
    def from_activiteit(cls, activiteit: Activiteit) -> DebatContext:
        stukken: list[str] = []
        for punt in activiteit.agendapunten:
            titels = [d.onderwerp for d in punt.documenten if d.onderwerp]
            for titel in titels or [punt.onderwerp]:
                if titel and titel not in stukken:
                    stukken.append(titel)
        return cls(
            onderwerp=activiteit.onderwerp,
            soort=activiteit.soort,
            bewindspersonen=activiteit.bewindspersonen,
            stukken=tuple(stukken),
            initiatiefnemers="initiatief" in activiteit.onderwerp.lower(),
        )


@dataclass(frozen=True)
class Beoordeling:
    """What became of one turn."""

    uitkomst: str
    # Why a turn was skipped.
    reden: str = ""
    # The markeringen of this turn, new or found from an earlier call.
    markering_ids: tuple[uuid.UUID, ...] = ()
    # Numbers of open questions this turn came back to.
    herhaald: tuple[int, ...] = ()
    # Threads posted by this call, backlog of earlier turns included.
    threads: int = 0
    # Answers of the model that were dropped, mostly a quote that is not
    # in the turn.
    afgevallen: int = 0

    @property
    def opnieuw_proberen(self) -> bool:
        """Whether handing in the same turn again later can help."""
        return self.uitkomst == UITKOMST_LLM_ONBEREIKBAAR


def is_bewindspersoon(spreker: dd.Spreker) -> bool:
    """Whether a Debat Direct speaker is a member of government.

    They carry no party and a title that says what they are.
    """
    titel = (spreker.titel or "").lower()
    return not spreker.fractie and titel.startswith(_TITEL_BEWINDSPERSOON)


# --- the quote ---------------------------------------------------------

_WEGLATING = re.compile(r"\s*(?:\[\s*\.\.\.\s*\]|\(\s*\.\.\.\s*\)|\.\.\.|…)\s*")
_QUOTES = "\"'“”‘’„«»`"


def _plat(tekst: str) -> tuple[str, list[int]]:
    """Text flattened for comparison, with where each character came from.

    Lower case, whitespace as one space, quotation marks dropped. The model
    copies the quote, but not always its spacing or its quotation marks.
    """
    tekens: list[str] = []
    herkomst: list[int] = []
    for i, teken in enumerate(tekst):
        if teken in _QUOTES:
            continue
        if teken.isspace():
            if tekens and tekens[-1] != " ":
                tekens.append(" ")
                herkomst.append(i)
            continue
        laag = teken.lower()
        # One character can lower to two; keep the map one to one.
        for deel in laag:
            tekens.append(deel)
            herkomst.append(i)
    return "".join(tekens), herkomst


def vind_citaat(tekst: str, citaat: str) -> str | None:
    """The quote as it stands in the turn, or ``None`` if it is not there.

    What goes into a thread as "literally said" has to be in the
    transcript. A model that tidies up a sentence, or writes the question
    it thinks was meant, gives a quote nobody said. The return value is cut
    from the turn itself, never taken from the model.

    A model that was told to copy mistakes still repairs one now and then
    ("porgt" becomes "borgt"). The passage it meant is then looked up, and
    what comes back is how the transcript has it, mistake included.
    """
    plat, herkomst = _plat(tekst)
    delen = [d for d in _WEGLATING.split(citaat) if d.strip()]
    # The whole quote first: the transcript has dots of its own.
    kandidaten = [[citaat]] + ([delen] if len(delen) > 1 else [])
    for stukken in kandidaten:
        gevonden: list[tuple[int, int]] = []
        vanaf = 0
        for stuk in stukken:
            zoek = _plat(stuk)[0].strip()
            if not zoek:
                break
            at = plat.find(zoek, vanaf)
            if at == -1:
                break
            gevonden.append((at, at + len(zoek) - 1))
            vanaf = at + len(zoek)
        else:
            if gevonden:
                return _zegt_iets(
                    " (...) ".join(
                        tekst[herkomst[a] : herkomst[b] + 1].strip()
                        for a, b in gevonden
                    )
                )
    bijna = _vind_bijna(plat, _plat(citaat)[0].strip())
    if bijna is None:
        return None
    return _zegt_iets(tekst[herkomst[bijna[0]] : herkomst[bijna[1]] + 1].strip())


def _zegt_iets(citaat: str) -> str | None:
    """A quote of a word or two stands in every turn and proves nothing."""
    return citaat if len(citaat) >= MIN_CITAAT else None


# The shortest quote that counts as a question that was really asked.
MIN_CITAAT = 12
# How much of a quote has to stand in the turn, in the same order, for the
# passage to count as the one the model meant.
_BIJNA_AANDEEL = 0.9
# Pieces shorter than this match anywhere and say nothing.
_BIJNA_MIN_STUK = 6


def _vind_bijna(plat: str, zoek: str) -> tuple[int, int] | None:
    """Where an almost literal quote stands in the flattened turn.

    The pieces the quote and the turn share, in order, have to cover nearly
    all of the quote and lie as close together as they do in the quote. A
    question the model wrote itself shares words with the turn, not
    sentences, and does not get there.
    """
    if len(zoek) < 3 * _BIJNA_MIN_STUK:
        return None
    blokken = [
        b
        for b in difflib.SequenceMatcher(
            None, plat, zoek, autojunk=False
        ).get_matching_blocks()
        if b.size >= _BIJNA_MIN_STUK
    ]
    if not blokken:
        return None
    gedekt = sum(b.size for b in blokken)
    begin, eind = blokken[0].a, blokken[-1].a + blokken[-1].size - 1
    if gedekt < _BIJNA_AANDEEL * len(zoek):
        return None
    if eind - begin + 1 > len(zoek) * (2 - _BIJNA_AANDEEL):
        return None
    # Whole words: a repaired first or last word is cut in half otherwise.
    while begin > 0 and plat[begin - 1] != " ":
        begin -= 1
    while eind + 1 < len(plat) and plat[eind + 1] != " ":
        eind += 1
    return begin, eind


def _kort(tekst: str, maximum: int) -> str:
    tekst = " ".join((tekst or "").split())
    if len(tekst) <= maximum:
        return tekst
    return tekst[: maximum - 1].rstrip() + "…"


# --- the thread --------------------------------------------------------

_VEILIGE_URL = re.compile(r"^https://[^\s()<>\[\]]+$")


def _hhmm(moment: datetime) -> str:
    return moment.astimezone(AMSTERDAM).strftime("%H:%M")


def format_vraag_thread(
    *,
    spreker: str,
    fractie: str | None,
    gericht_aan: str,
    citaat: str,
    samenvatting: str,
    stuk: str | None,
    moment: datetime,
    moment_url: str | None,
) -> str:
    """The reply under the message of a turn that is the thread of a question.

    Everything in it comes from outside: the names from Debat Direct, the
    quote from the transcript, the summary from a model that read the
    transcript. All of it is escaped.
    """
    wie = _vrij(_kort(spreker, 120))
    if fractie and fractie.lower() not in spreker.lower():
        wie = f"{wie} ({_vrij(fractie)})"
    tijd = _hhmm(moment)
    if moment_url and _VEILIGE_URL.match(moment_url):
        tijd = f"[{tijd}]({moment_url})"
    regels = [f"{ICOON_VRAAG} **Vraag aan {aan_wie(gericht_aan)}** · {wie} · {tijd}"]
    if samenvatting:
        regels.append(_vrij(_kort(samenvatting, MAX_SAMENVATTING)))
    if stuk:
        regels.append(f"Gaat over: {_vrij(_kort(stuk, 300))}")
    regels.append("")
    regels.append(f"> {_vrij(_kort(citaat, MAX_CITAAT))}")
    regels.append("")
    regels.append(
        "_Het citaat komt letterlijk uit het automatische transcript; de tijd"
        " is het begin van de spreekbeurt._"
    )
    return "\n".join(regels)


def _vrij(tekst: str) -> str:
    """Text a model wrote, or chose, made harmless for a message.

    Escaping alone is not enough: a model that writes a backslash before
    an at-sign gets the backslash escaped and the mention live. So no
    backslashes and no at-signs at all, and an address is broken up so it
    does not become a link.
    """
    tekst = tekst.replace("\\", "").replace("@", "")
    tekst = tekst.replace("://", ": //").replace("www.", "www ")
    return _escape(tekst)


def aan_wie(gericht_aan: str) -> str:
    """Who a question is put to, in our words and not the model's."""
    aan = gericht_aan.lower()
    if "staatssecretaris" in aan:
        return "de staatssecretaris"
    if "minister-president" in aan or "premier" in aan:
        return "de minister-president"
    if "minister" in aan:
        return "de minister"
    if "kabinet" in aan or "regering" in aan:
        return "het kabinet"
    return "de bewindspersoon"


# --- the answer of the model -------------------------------------------


@dataclass(frozen=True)
class _Nieuw:
    citaat: str
    gericht_aan: str
    samenvatting: str
    stuk: str | None


@dataclass(frozen=True)
class _Herhaling:
    volgnummer: int
    citaat: str


def _woorden(tekst: str) -> list[str]:
    plat = unicodedata.normalize("NFKD", tekst.lower())
    plat = "".join(c for c in plat if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", plat)


def stuk_blijkt_uit_citaat(citaat: str, titel: str, onderwerp: str) -> bool:
    """Whether the quote itself points at this agenda document.

    The model is asked for the document only when the speaker names it, and
    on a real debate it still picked one for half of the questions: every
    question in a debate is about the subject of the debate. So the choice
    is checked. What sets a document apart is in its title and not in the
    subject of the debate ("Reactie van het kabinet op ..."), and one of
    those words has to be in the quote ("uit de kabinetsreactie maak ik
    op"). A document whose title is the subject is never named: that a
    question is about it says nothing.
    """
    algemeen = set(_woorden(onderwerp))
    eigen = [w for w in _woorden(titel) if len(w) >= 5 and w not in algemeen]
    gezegd = " ".join(_woorden(citaat))
    return any(woord in gezegd for woord in eigen)


def lees_antwoord(
    vragen: Sequence[DebatVraag],
    tekst: str,
    stukken: Sequence[str],
    openstaand: set[int],
    onderwerp: str = "",
) -> tuple[list[_Nieuw], list[_Herhaling], int]:
    """Sort what the model answered into new, repeated and dropped.

    Dropped: a question that is not to the bewindspersoon, a quote that is
    not in the turn, and a second answer with the same quote. A `hoort_bij`
    that is not an open question is a number the model made up; the question
    is then new. A `stuk` that is not on the agenda, or that the quote does
    not point at, is left out.
    """
    nieuw: list[_Nieuw] = []
    herhaald: list[_Herhaling] = []
    afgevallen = 0
    gezien: set[str] = set()
    for vraag in vragen:
        aan = vraag.gericht_aan.lower()
        if not any(woord in aan for woord in _AAN_BEWINDSPERSOON):
            afgevallen += 1
            logger.info("Vraag aan %r is niet aan de bewindspersoon", aan[:60])
            continue
        citaat = vind_citaat(tekst, vraag.citaat)
        if citaat is None:
            afgevallen += 1
            logger.info(
                "Citaat staat niet in de spreekbeurt, vraag valt af: %s",
                vraag.citaat[:120],
            )
            continue
        sleutel = _plat(citaat)[0]
        if sleutel in gezien:
            afgevallen += 1
            continue
        gezien.add(sleutel)
        if vraag.hoort_bij is not None and vraag.hoort_bij in openstaand:
            if all(h.volgnummer != vraag.hoort_bij for h in herhaald):
                herhaald.append(_Herhaling(vraag.hoort_bij, citaat))
            continue
        stuk = None
        if vraag.stuk is not None and 1 <= vraag.stuk <= len(stukken):
            titel = stukken[vraag.stuk - 1]
            if stuk_blijkt_uit_citaat(citaat, titel, onderwerp):
                stuk = titel
        nieuw.append(
            _Nieuw(
                citaat=citaat,
                gericht_aan=_kort(vraag.gericht_aan, MAX_GERICHT_AAN),
                samenvatting=_kort(vraag.samenvatting, MAX_SAMENVATTING),
                stuk=stuk,
            )
        )
    return nieuw, herhaald, afgevallen


# --- the service -------------------------------------------------------


async def statusblok_voor_post(session: AsyncSession, post_id: str) -> str:
    """The status block that belongs under the message of a turn.

    For whoever rewrites that message from scratch. Only markeringen with a
    thread count: a question whose thread could not be posted is not shown
    as marked.
    """
    rows = (
        await session.execute(
            select(DebatMarkering.soort, DebatMarkering.status)
            .where(
                DebatMarkering.beurt_post_id == post_id,
                DebatMarkering.thread_post_id.is_not(None),
            )
            .order_by(DebatMarkering.volgnummer)
        )
    ).all()
    return statusregel([(r[0], r[1]) for r in rows])


class DebatVraagService:
    def __init__(
        self,
        session: AsyncSession,
        mattermost: MattermostService,
        llm: BaseLLMService,
    ) -> None:
        self.session = session
        self.mattermost = mattermost
        self.llm = llm
        self._ingehaald: set[uuid.UUID] = set()

    @classmethod
    async def create(
        cls, session: AsyncSession, mattermost: MattermostService | None = None
    ) -> DebatVraagService | None:
        """A service on the configured model, or ``None`` if there is none.

        A debate is public and broadcast, so any provider may read it.
        """
        from bouwmeester.services.llm import get_llm_service

        llm = await get_llm_service(session)
        if llm is None:
            return None
        return cls(session, mattermost or MattermostService(session), llm)

    def nieuwe_ronde(self) -> None:
        """For whoever keeps one service over several rounds."""
        self._ingehaald.clear()

    async def beoordeel_beurt(self, beurt: Beurt, context: DebatContext) -> Beoordeling:
        """Judge one finished turn, and post what it holds.

        Safe to call again for the same turn: the model is asked once, and
        a thread is posted once.
        """
        # Threads and status lines of earlier turns that did not make it.
        # Once per debate for as long as this service lives, which is one
        # round: tried with every turn, a Mattermost that is down for a
        # moment would use up all attempts within that one round.
        threads = 0
        if beurt.sessie_id not in self._ingehaald:
            self._ingehaald.add(beurt.sessie_id)
            threads = await self._haal_achterstand_in(beurt.sessie_id)

        reden = self._overslaan(beurt, context)
        if reden:
            return Beoordeling(UITKOMST_OVERGESLAGEN, reden=reden, threads=threads)

        eerder = await self._eerder_beoordeeld(beurt.sessie_id, beurt.sleutel)
        if eerder is not None:
            return Beoordeling(
                UITKOMST_AL_BEOORDEELD, markering_ids=eerder, threads=threads
            )

        open_ids = await self._openstaand(beurt.sessie_id, beurt.spreker)
        openstaand = [(nummer, wie, wat) for nummer, wie, wat, _ in open_ids]
        result = await self.llm.markeer_debat_vragen(
            onderwerp=context.onderwerp,
            soort_vergadering=context.soort,
            bewindspersonen=[
                f"{b.functie}: {b.naam}" if b.functie else b.naam
                for b in context.bewindspersonen
            ],
            stukken=list(context.stukken),
            openstaand=openstaand,
            spreker=beurt.spreker,
            interruptie=beurt.soort == SOORT_INTERRUPTER,
            tekst=beurt.tekst,
            onderbroken=beurt.onderbroken,
            initiatiefnemers=context.initiatiefnemers,
        )
        if result.fout:
            logger.warning(
                "Spreekbeurt van %s in sessie %s niet beoordeeld: model %s",
                _hhmm(beurt.start),
                beurt.sessie_id,
                result.fout,
            )
            return Beoordeling(
                UITKOMST_LLM_ONBEREIKBAAR
                if result.fout == DEBAT_VRAGEN_ONBEREIKBAAR
                else UITKOMST_LLM_ONBRUIKBAAR,
                threads=threads,
            )

        nieuw, herhaald, afgevallen = lees_antwoord(
            result.vragen,
            beurt.tekst,
            context.stukken,
            {nummer for nummer, _, _ in openstaand},
            context.onderwerp,
        )
        if not nieuw and not herhaald:
            return Beoordeling(
                UITKOMST_GEEN_VRAAG, threads=threads, afgevallen=afgevallen
            )

        ids = await self._leg_vast(
            beurt, nieuw, herhaald, {nummer: id_ for nummer, _, _, id_ in open_ids}
        )
        if ids is None:
            # Someone else stored this turn while the model was reading.
            eerder = await self._eerder_beoordeeld(beurt.sessie_id, beurt.sleutel)
            return Beoordeling(
                UITKOMST_AL_BEOORDEELD, markering_ids=eerder or (), threads=threads
            )

        for markering_id in ids:
            if await self._post_thread(markering_id):
                threads += 1
        await self._werk_statusregels_bij(beurt.sessie_id)
        logger.info(
            "Spreekbeurt van %s: %d vragen gemarkeerd, %d herhaald",
            _hhmm(beurt.start),
            len(ids),
            len(herhaald),
        )
        return Beoordeling(
            UITKOMST_GEMARKEERD,
            markering_ids=ids,
            herhaald=tuple(h.volgnummer for h in herhaald),
            threads=threads,
            afgevallen=afgevallen,
        )

    def _overslaan(self, beurt: Beurt, context: DebatContext) -> str:
        """Why this turn is not sent to the model, or an empty string."""
        if beurt.soort == SOORT_CHAIRMAN:
            # The chairman gives the floor and keeps order.
            return "voorzitter"
        if beurt.is_bewindspersoon or _is_aan_tafel(beurt, context):
            # An answer, not a question.
            return "bewindspersoon"
        if len(beurt.tekst.split()) < MIN_WOORDEN:
            return "te kort"
        if (
            beurt.soort == SOORT_INTERRUPTER
            and not beurt.onderbroken_is_bewindspersoon
            and not _noemt_bewindspersoon(beurt.tekst)
        ):
            # "Bent u het daarmee eens?" in an interruption is a question
            # to whoever is interrupted. On a real debate the model read
            # that as a question to the minister in two runs out of three,
            # so it is not left to the model: an interruption of someone
            # else only counts when it names the bewindspersoon.
            return "interruptie van een ander"
        return ""

    async def _eerder_beoordeeld(
        self, sessie_id: uuid.UUID, sleutel: str
    ) -> tuple[uuid.UUID, ...] | None:
        """The markeringen of a turn that was stored before, or ``None``.

        A turn that held nothing is not stored, so it is ``None`` here and
        is read again. That costs a call and changes nothing.
        """
        ids = (
            (
                await self.session.execute(
                    select(DebatMarkering.id)
                    .where(
                        DebatMarkering.sessie_id == sessie_id,
                        DebatMarkering.beurt_sleutel == sleutel,
                    )
                    .order_by(DebatMarkering.volgnummer)
                )
            )
            .scalars()
            .all()
        )
        if ids:
            return tuple(ids)
        vermelding = (
            await self.session.execute(
                select(DebatMarkeringVermelding.id)
                .where(
                    DebatMarkeringVermelding.sessie_id == sessie_id,
                    DebatMarkeringVermelding.beurt_sleutel == sleutel,
                )
                .limit(1)
            )
        ).first()
        return () if vermelding is not None else None

    async def _openstaand(
        self, sessie_id: uuid.UUID, spreker: str
    ) -> list[tuple[int, str, str, uuid.UUID]]:
        """The open questions of this speaker, as (number, who, summary, id).

        Only their own. A question is the same question when the same
        member asks it again; two members who ask about the same thing each
        expect an answer. On a real debate the model, given everyone's open
        questions, filed new questions of one member under a question of
        another because they shared a subject, and a question that is filed
        gets no thread.

        The most recent `MAX_OPENSTAAND`, in the order they were asked.
        """
        rows = (
            await self.session.execute(
                select(
                    DebatMarkering.volgnummer,
                    DebatMarkering.spreker,
                    DebatMarkering.samenvatting,
                    DebatMarkering.citaat,
                    DebatMarkering.id,
                )
                .where(
                    DebatMarkering.sessie_id == sessie_id,
                    DebatMarkering.soort == SOORT_VRAAG,
                    DebatMarkering.status == STATUS_OPEN,
                    DebatMarkering.spreker == spreker,
                )
                .order_by(DebatMarkering.volgnummer.desc())
                .limit(MAX_OPENSTAAND)
            )
        ).all()
        return [
            (r[0], _kort(r[1], 80), _kort(r[2] or r[3], MAX_SAMENVATTING), r[4])
            for r in sorted(rows, key=lambda r: r[0])
        ]

    async def _leg_vast(
        self,
        beurt: Beurt,
        nieuw: list[_Nieuw],
        herhaald: list[_Herhaling],
        open_ids: dict[int, uuid.UUID],
    ) -> tuple[uuid.UUID, ...] | None:
        """Store what the model found in this turn, in one commit.

        ``None`` if the turn was stored in the meantime, or the debate is
        gone. The lock on the sessie makes two calls for the same debate
        take turns here: the second sees what the first stored, and the
        numbers are handed out once.
        """
        locked = (
            await self.session.execute(
                select(DebatSessie.id)
                .where(DebatSessie.id == beurt.sessie_id)
                .with_for_update()
            )
        ).first()
        if locked is None:
            await self.session.commit()
            return None
        if await self._eerder_beoordeeld(beurt.sessie_id, beurt.sleutel) is not None:
            await self.session.commit()
            return None

        hoogste = (
            await self.session.execute(
                select(func.max(DebatMarkering.volgnummer)).where(
                    DebatMarkering.sessie_id == beurt.sessie_id
                )
            )
        ).scalar() or 0
        ids: list[uuid.UUID] = []
        for i, vraag in enumerate(nieuw, start=1):
            ids.append(
                (
                    await self.session.execute(
                        insert(DebatMarkering)
                        .values(
                            sessie_id=beurt.sessie_id,
                            spreekbeurt_id=beurt.spreekbeurt_id,
                            beurt_sleutel=beurt.sleutel,
                            volgnummer=hoogste + i,
                            soort=SOORT_VRAAG,
                            status=STATUS_OPEN,
                            channel_id=beurt.channel_id,
                            beurt_post_id=beurt.post_id,
                            spreker=beurt.spreker,
                            fractie=beurt.fractie,
                            gericht_aan=vraag.gericht_aan,
                            citaat=vraag.citaat,
                            samenvatting=vraag.samenvatting,
                            stuk=vraag.stuk,
                            moment=beurt.start,
                            moment_url=beurt.moment_url,
                        )
                        .returning(DebatMarkering.id)
                    )
                ).scalar_one()
            )
        for herhaling in herhaald:
            await self.session.execute(
                insert(DebatMarkeringVermelding).values(
                    # The number came from this list, so it is in it.
                    markering_id=open_ids[herhaling.volgnummer],
                    sessie_id=beurt.sessie_id,
                    spreekbeurt_id=beurt.spreekbeurt_id,
                    beurt_sleutel=beurt.sleutel,
                    soort=VERMELDING_HERHALING,
                    beurt_post_id=beurt.post_id,
                    spreker=beurt.spreker,
                    fractie=beurt.fractie,
                    citaat=herhaling.citaat,
                    moment=beurt.start,
                    moment_url=beurt.moment_url,
                )
            )
        await self.session.commit()
        return tuple(ids)

    async def _post_thread(self, markering_id: uuid.UUID) -> bool:
        """Post the thread of one markering, if it has none yet.

        The row is locked from the look until the post id is committed, so
        two workers cannot both post it: the second skips a locked row. A
        post that fails counts as an attempt and leaves the row without a
        thread. Whether it is tried again is for the backlog to decide.
        """
        row = (
            await self.session.execute(
                select(
                    DebatMarkering.channel_id,
                    DebatMarkering.beurt_post_id,
                    DebatMarkering.spreker,
                    DebatMarkering.fractie,
                    DebatMarkering.gericht_aan,
                    DebatMarkering.citaat,
                    DebatMarkering.samenvatting,
                    DebatMarkering.stuk,
                    DebatMarkering.moment,
                    DebatMarkering.moment_url,
                )
                .where(
                    DebatMarkering.id == markering_id,
                    DebatMarkering.thread_post_id.is_(None),
                    DebatMarkering.beurt_post_id.is_not(None),
                )
                .with_for_update(skip_locked=True)
            )
        ).first()
        if row is None:
            await self.session.commit()
            return False

        tekst = format_vraag_thread(
            spreker=row[2],
            fractie=row[3],
            gericht_aan=row[4],
            citaat=row[5],
            samenvatting=row[6],
            stuk=row[7],
            moment=row[8],
            moment_url=row[9],
        )
        try:
            post_id = await self.mattermost.send_channel_message(
                row[0], tekst, root_id=row[1]
            )
        except Exception:
            logger.exception("Thread voor markering %s niet geplaatst", markering_id)
            post_id = None

        if post_id:
            # Before anything else: a thread that is in the channel has to
            # be in the database, or the next call posts it a second time.
            await self.session.execute(
                update(DebatMarkering)
                .where(DebatMarkering.id == markering_id)
                .values(thread_post_id=post_id)
            )
        else:
            logger.warning("Thread voor markering %s niet geplaatst", markering_id)
            await self.session.execute(
                update(DebatMarkering)
                .where(DebatMarkering.id == markering_id)
                .values(post_pogingen=DebatMarkering.post_pogingen + 1)
            )
        await self.session.commit()
        return bool(post_id)

    async def _haal_achterstand_in(self, sessie_id: uuid.UUID) -> int:
        """Try again what an earlier call could not put in the channel."""
        ids = (
            (
                await self.session.execute(
                    select(DebatMarkering.id)
                    .where(
                        DebatMarkering.sessie_id == sessie_id,
                        DebatMarkering.thread_post_id.is_(None),
                        DebatMarkering.beurt_post_id.is_not(None),
                        DebatMarkering.post_pogingen < MAX_POST_POGINGEN,
                    )
                    .order_by(DebatMarkering.volgnummer)
                )
            )
            .scalars()
            .all()
        )
        threads = 0
        for markering_id in ids:
            if await self._post_thread(markering_id):
                threads += 1
        await self._werk_statusregels_bij(sessie_id)
        return threads

    async def _werk_statusregels_bij(self, sessie_id: uuid.UUID) -> None:
        """Write the status line of every turn whose line is out of date."""
        post_ids = (
            (
                await self.session.execute(
                    select(DebatMarkering.beurt_post_id)
                    .where(
                        DebatMarkering.sessie_id == sessie_id,
                        DebatMarkering.thread_post_id.is_not(None),
                        DebatMarkering.statusregel_at.is_(None),
                    )
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
        for post_id in post_ids:
            if post_id and await self._schrijf_statusregel(post_id):
                await self.session.execute(
                    update(DebatMarkering)
                    .where(
                        DebatMarkering.beurt_post_id == post_id,
                        DebatMarkering.thread_post_id.is_not(None),
                    )
                    .values(statusregel_at=datetime.now(UTC))
                )
                await self.session.commit()

    async def _schrijf_statusregel(self, post_id: str) -> bool:
        """Put the status block under the message of a turn.

        Reads the message first and replaces only the status block, so the
        transcript that is in it stays. ``True`` when the line is as it
        should be, or never will be because the message is gone.
        """
        blok = await statusblok_voor_post(self.session, post_id)
        try:
            post = await self.mattermost.get_post(post_id)
        except PostNotFoundError:
            logger.info("Bericht %s is weg; geen statusregel", post_id)
            return True
        except Exception:
            logger.exception("Bericht %s niet te lezen voor de statusregel", post_id)
            return False
        if not post:
            return False
        huidig = str(post.get("message") or "")
        nieuw = met_status(huidig, blok)
        if nieuw == huidig:
            return True
        try:
            # The props go back as they came: an update without them is an
            # update that clears them.
            return bool(
                await self.mattermost.update_post(
                    post_id, nieuw, post.get("props") or None
                )
            )
        except Exception:
            logger.exception("Statusregel op bericht %s niet geschreven", post_id)
            return False


def _noemt_bewindspersoon(tekst: str) -> bool:
    laag = tekst.lower()
    return any(woord in laag for woord in _AAN_BEWINDSPERSOON)


def _is_aan_tafel(beurt: Beurt, context: DebatContext) -> bool:
    """Whether the speaker is one of the bewindspersonen of this debate.

    A safety net for a caller that did not set `is_bewindspersoon`. On the
    surname, because the TK API writes initials where Debat Direct writes a
    first name. Someone with a party is a member of parliament, whatever
    they are called.
    """
    if beurt.fractie:
        return False
    woorden = set(re.findall(r"\w+", beurt.spreker.lower()))
    for bewindspersoon in context.bewindspersonen:
        delen = re.findall(r"\w+", bewindspersoon.naam.lower())
        if delen and len(delen[-1]) >= 4 and delen[-1] in woorden:
            return True
    return False
