"""Run the production code path for marking over the turns of a gold file.

`DebatVraagService.beoordeel_beurt` is called for every turn, in order,
exactly as the worker does: the service decides itself which turns it
skips, builds the prompt, reads the answer and stores what it accepts. The
database is real, Mattermost is a stand-in that remembers what it is sent,
and the model is whatever `BaseLLMService` is handed in, wrapped so that
its raw answers can be kept and its prompt can be rewritten on the way.

When the turns are done, the list of toezeggingen the chairman read out at
the end is looked for the way the worker does it when a debate is over
(`find_closing_list`), and read once if it is there. What that stored is
kept with the turn of the chairman each quote stands in.

What comes back per turn: what the service made of it, what the model
answered (also what the code dropped afterwards), and what was stored.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.debat_markering import (
    VERMELDING_ANTWOORD,
    VERMELDING_BEVESTIGING,
    DebatMarkering,
    DebatMarkeringVermelding,
)
from bouwmeester.models.debat_sessie import DebatSessie
from bouwmeester.services.debat_slotlijst import (
    BEWINDSPERSOON,
    CHAIRMAN,
    MEMBER,
    ClosingList,
    Spoken,
    find_closing_list,
)
from bouwmeester.services.debat_vraag_service import (
    SOORT_CHAIRMAN,
    Beurt,
    DebatContext,
    DebatVraagService,
    locate_citaat,
)
from bouwmeester.services.llm import base as llm_base
from bouwmeester.services.llm.base import (
    BaseLLMService,
    DataSensitivity,
    ProviderCapabilities,
)
from bouwmeester.services.tk_activiteit import Bewindspersoon, Initiatiefnemer

from .gold import KIND_TOEZEGGING, KIND_VRAAG

CHANNEL = "evalchannel000000000000000"
TEAM = "evalteam000000000000000000"
TURN_TIMEOUT = 300
_TURN_TEXT = re.compile(r"<spreekbeurt>\n(.*)\n</spreekbeurt>", re.DOTALL)
_LIST_TEXT = re.compile(r"<voorzitter>\n(.*)\n</voorzitter>", re.DOTALL)


class RecordingLLM(BaseLLMService):
    """A provider that keeps what the model answered.

    Everything but the call itself is the real `BaseLLMService`: the prompt
    builder, the retry and the reading of the answer. `transform` rewrites
    the prompt before it is sent, for trying out a prompt variant.
    """

    capabilities = ProviderCapabilities(allowed_data={DataSensitivity.PUBLIC})

    def __init__(
        self, inner: BaseLLMService, transform: Callable[[str], str] | None = None
    ) -> None:
        self.inner = inner
        self.transform = transform or (lambda prompt: prompt)
        self.prompts: list[str] = []
        self.answers: list[str] = []

    async def _complete(self, prompt: str, max_tokens: int = 1024) -> str:
        prompt = self.transform(prompt)
        self.prompts.append(prompt)
        answer = await self.inner._complete(prompt, max_tokens=max_tokens)
        self.answers.append(answer)
        return answer


class OracleLLM(BaseLLMService):
    """A model that answers with the gold items of the turn it is shown.

    For trying the harness without a model, and for tests: what the code
    then misses or drops is the doing of the code alone. Asked for
    questions it gives the gold questions of the turn, asked for
    toezeggingen the gold toezeggingen. Asked for the chairman's list it
    gives the gold toezeggingen of the chairman's turns that stand in the
    words it is shown, and says of none which earlier one it is: matching
    is then the code's alone.
    """

    capabilities = ProviderCapabilities(allowed_data={DataSensitivity.PUBLIC})

    def __init__(
        self, gold: dict, kinds: tuple[str, ...] = (KIND_VRAAG, KIND_TOEZEGGING)
    ) -> None:
        self.turns = [(t["tekst"], t["nr"]) for t in gold["beurten"]]
        self.chairman = {t["nr"] for t in gold["beurten"] if t["soort"] == CHAIRMAN}
        self.items: dict[int, list[dict]] = {}
        for item in gold.get("items") or []:
            if item["soort"] in kinds:
                self.items.setdefault(item["beurt"], []).append(item)

    async def _complete(self, prompt: str, max_tokens: int = 1024) -> str:
        import json

        listed = _LIST_TEXT.search(prompt)
        if listed is not None:
            toezeggingen = [
                {
                    "citaat": item["citaat"],
                    "samenvatting": "Toezegging uit de gouden set.",
                    "termijn": None,
                    "hoort_bij": None,
                }
                for number in sorted(self.chairman)
                for item in self.items.get(number, [])
                if item["soort"] == KIND_TOEZEGGING
                and item["citaat"] in listed.group(1)
            ]
            return json.dumps({"toezeggingen": toezeggingen}, ensure_ascii=False)
        shown = _TURN_TEXT.search(prompt)
        text = (shown.group(1) if shown else "").removeprefix("(...) ")
        number = next((nr for full, nr in self.turns if full.endswith(text)), None)
        if '{"toezeggingen"' in prompt:
            toezeggingen = [
                {
                    "citaat": item["citaat"],
                    "samenvatting": "Toezegging uit de gouden set.",
                    "termijn": None,
                    "bij_vraag": None,
                    "hoort_bij": None,
                }
                for item in self.items.get(number, [])
                if item["soort"] == KIND_TOEZEGGING
            ]
            return json.dumps({"toezeggingen": toezeggingen}, ensure_ascii=False)
        vragen = [
            {
                "citaat": item["citaat"],
                "gericht_aan": f"de {item.get('gericht_aan') or 'minister'}",
                "samenvatting": "Vraag uit de gouden set.",
                "hoort_bij": None,
                "stuk": None,
            }
            for item in self.items.get(number, [])
            if item["soort"] == KIND_VRAAG
        ]
        return json.dumps({"vragen": vragen}, ensure_ascii=False)


class SilentMattermost:
    """Takes what the service posts and gives it back when asked."""

    def __init__(self) -> None:
        self.messages: dict[str, str] = {}
        self.replies: list[tuple[str | None, str]] = []

    async def send_channel_message(self, channel_id, text, props=None, root_id=None):
        self.replies.append((root_id, text))
        return f"r{uuid.uuid4().hex}"[:26]

    async def get_post(self, post_id):
        return {"id": post_id, "message": self.messages.get(post_id, ""), "props": {}}

    async def update_post(self, post_id, message, props=None) -> bool:
        self.messages[post_id] = message
        return True

    async def add_reaction(self, post_id, emoji_name) -> bool:
        return True


def context_from(gold: dict) -> DebatContext:
    debat = gold["debat"]
    return DebatContext(
        onderwerp=debat["onderwerp"],
        soort=debat.get("soort"),
        bewindspersonen=tuple(
            Bewindspersoon(naam=b["naam"], functie=b.get("functie"))
            for b in debat.get("bewindspersonen") or []
        ),
        stukken=tuple(debat.get("stukken") or ()),
        initiatiefnemers=bool(debat.get("initiatiefnemers")),
        # Optional in a gold file: who they are, as the TK API has them.
        initiatiefnemer_namen=tuple(
            Initiatiefnemer(naam=i["naam"], fractie=i.get("fractie"))
            for i in debat.get("initiatiefnemer_namen") or []
        ),
    )


def interruption_before(turns: list[dict], index: int) -> dict | None:
    """The interruption of a member right before a turn, as the worker has it.

    The chairman's words in between are passed over. ``None`` when what
    came before is not an interruption, or is not by a member.
    """
    for earlier in reversed(turns[:index]):
        if earlier["soort"] == "chairman":
            continue
        if earlier["soort"] == "interrupter" and earlier.get("fractie"):
            return earlier
        return None
    return None


def beurt_from(turn: dict, sessie_id: uuid.UUID, before: dict | None = None) -> Beurt:
    asked = before if turn.get("is_bewindspersoon") else None
    asked_key = beurt_from(asked, sessie_id).sleutel if asked else None
    return Beurt(
        sessie_id=sessie_id,
        spreekbeurt_id=None,
        post_id=f"t{turn['nr']:025d}",
        channel_id=CHANNEL,
        soort=turn["soort"],
        spreker=turn["spreker"],
        fractie=turn.get("fractie"),
        start=datetime.fromisoformat(turn["start"]),
        moment_url=None,
        tekst=turn["tekst"],
        is_bewindspersoon=bool(turn.get("is_bewindspersoon")),
        onderbroken=turn.get("onderbroken"),
        onderbroken_is_bewindspersoon=bool(turn.get("onderbroken_is_bewindspersoon")),
        voorafgaand=asked["spreker"] if asked else None,
        voorafgaand_tekst=asked["tekst"] if asked else "",
        voorafgaand_sleutel=asked_key,
    )


def closing_list_of(turns: list[dict]) -> ClosingList | None:
    """The chairman's list of toezeggingen in the turns of a gold file.

    As the worker finds it when a debate is over. A gold file does not say
    when the debate ended, so the start of its last turn stands in for
    that. The parts of what comes back are indexes into `turns`.
    """
    spoken = [
        Spoken(
            CHAIRMAN
            if turn["soort"] == CHAIRMAN
            else BEWINDSPERSOON
            if turn.get("is_bewindspersoon")
            else MEMBER,
            datetime.fromisoformat(turn["start"]),
            turn["tekst"],
        )
        for turn in turns
    ]
    return find_closing_list(spoken)


def list_beurt(turns: list[dict], closing: ClosingList, sessie_id: uuid.UUID) -> Beurt:
    """The chairman's list as the turn the service reads.

    It hangs under the last message of the chairman it is made of, as in
    production it hangs under the message of the end of the debate.
    """
    last = turns[closing.delen[-1][0]]
    return Beurt(
        sessie_id=sessie_id,
        spreekbeurt_id=None,
        post_id=f"t{last['nr']:025d}",
        channel_id=CHANNEL,
        soort=SOORT_CHAIRMAN,
        spreker=last["spreker"],
        fractie=None,
        start=closing.start,
        moment_url=None,
        tekst=closing.tekst,
        slotlijst=True,
    )


def _raw_answer(llm: RecordingLLM, text: str) -> list[dict]:
    """What the model said, read the way production reads it."""
    try:
        toezeggingen = llm_base._lees_debat_toezeggingen(llm, text)
    except Exception:
        toezeggingen = None
    if toezeggingen is not None:
        return [
            {
                "soort": KIND_TOEZEGGING,
                "citaat": t.citaat,
                "samenvatting": t.samenvatting,
                "termijn": t.termijn,
                "bij_vraag": t.bij_vraag,
                "hoort_bij": t.hoort_bij,
            }
            for t in toezeggingen
        ]
    try:
        vragen = llm_base._lees_debat_vragen(llm, text)
    except Exception:
        return []
    return [
        {
            "citaat": v.citaat,
            "gericht_aan": v.gericht_aan,
            "samenvatting": v.samenvatting,
            "hoort_bij": v.hoort_bij,
        }
        for v in vragen
    ]


async def _read_closing_list(
    session: AsyncSession,
    service: DebatVraagService,
    recorder: RecordingLLM,
    context: DebatContext,
    turns: list[dict],
    block: dict,
    sessie_id: uuid.UUID,
) -> None:
    """Have the chairman's list read, and keep what it stored with the turn
    of the chairman each quote stands in.

    A toezegging that came from the list is a marking of that turn. One
    that the list confirmed is kept as a repeat in that turn, with the
    number of the toezegging it confirmed: the gold set labels what the
    chairman reads out as a repetition, so it scores as one.
    `block["slotlijst"]` says what the list did as a whole.
    """
    closing = closing_list_of(turns)
    if closing is None:
        block["slotlijst"] = None
        return
    beurt = list_beurt(turns, closing, sessie_id)
    before = len(recorder.answers)
    outcome = await asyncio.wait_for(
        service.beoordeel_beurt(beurt, context), TURN_TIMEOUT
    )
    answers = recorder.answers[before:]
    results = {result["nr"]: result for result in block["beurten"]}

    def turn_of(citaat: str) -> dict:
        found = locate_citaat(closing.tekst, citaat)
        index = closing.deel_van(found[1]) if found else closing.delen[0][0]
        return results[turns[index]["nr"]]

    new = (
        await session.execute(
            select(
                DebatMarkering.soort,
                DebatMarkering.citaat,
                DebatMarkering.gericht_aan,
                DebatMarkering.samenvatting,
                DebatMarkering.volgnummer,
                DebatMarkering.termijn,
            )
            .where(
                DebatMarkering.sessie_id == sessie_id,
                DebatMarkering.beurt_sleutel == beurt.sleutel,
            )
            .order_by(DebatMarkering.volgnummer)
        )
    ).all()
    for row in new:
        turn_of(row[1])["gemarkeerd"].append(
            {
                "soort": row[0],
                "citaat": row[1],
                "gericht_aan": row[2],
                "samenvatting": row[3],
                "herhaling": False,
                "volgnummer": row[4],
                "termijn": row[5],
                "bij_volgnummer": None,
                "slotlijst": True,
            }
        )
    confirmed = (
        await session.execute(
            select(
                DebatMarkering.soort,
                DebatMarkeringVermelding.citaat,
                DebatMarkering.volgnummer,
                DebatMarkering.gericht_aan,
                DebatMarkering.termijn,
            )
            .join(
                DebatMarkering,
                DebatMarkering.id == DebatMarkeringVermelding.markering_id,
            )
            .where(
                DebatMarkeringVermelding.sessie_id == sessie_id,
                DebatMarkeringVermelding.beurt_sleutel == beurt.sleutel,
                DebatMarkeringVermelding.soort == VERMELDING_BEVESTIGING,
            )
            .order_by(DebatMarkering.volgnummer)
        )
    ).all()
    for row in confirmed:
        turn_of(row[1])["gemarkeerd"].append(
            {
                "soort": row[0],
                "citaat": row[1],
                "herhaling": True,
                "bevestigt": row[2],
                # What the toezegging says after the list was read: the
                # member and the moment the chairman named fill in what it
                # did not have.
                "gericht_aan": row[3],
                "termijn": row[4],
            }
        )
    await session.commit()
    first = results[turns[closing.delen[0][0]]["nr"]]
    first["ruw"] += [raw for answer in answers for raw in _raw_answer(recorder, answer)]
    first["aanroepen"] += len(answers)
    block["aanroepen"] += len(answers)
    for index, _ in closing.delen:
        result = results[turns[index]["nr"]]
        result["uitkomst"], result["reden"] = outcome.uitkomst, "slotlijst"
    block["slotlijst"] = {
        "beurten": [turns[index]["nr"] for index, _ in closing.delen],
        "uitkomst": outcome.uitkomst,
        "nieuw": [row[4] for row in new],
        "bevestigd": [row[2] for row in confirmed],
        "afgevallen": outcome.afgevallen,
    }


async def run_debate(
    session: AsyncSession,
    llm: BaseLLMService,
    gold: dict,
    name: str,
    *,
    transform: Callable[[str], str] | None = None,
    max_turns: int | None = None,
    on_turn: Callable[[dict, dict], None] | None = None,
) -> dict:
    """Judge every turn of one debate; returns its block of the run file.

    The debate gets a sessie of its own, which is removed again with all
    that was stored under it.
    """
    recorder = RecordingLLM(llm, transform)
    mattermost = SilentMattermost()
    sessie = DebatSessie(
        activiteit_id=str(uuid.uuid4()),
        onderwerp=gold["debat"]["onderwerp"][:500],
        team_id=TEAM,
    )
    session.add(sessie)
    await session.commit()
    sessie_id = sessie.id
    service = DebatVraagService(session, mattermost, recorder)
    context = context_from(gold)
    block: dict = {"naam": name, "beurten": [], "aanroepen": 0}
    try:
        for index, turn in enumerate(gold["beurten"][:max_turns]):
            beurt = beurt_from(
                turn, sessie_id, interruption_before(gold["beurten"], index)
            )
            mattermost.messages[beurt.post_id] = turn["tekst"][:200]
            before = len(recorder.answers)
            outcome = await asyncio.wait_for(
                service.beoordeel_beurt(beurt, context), TURN_TIMEOUT
            )
            # A long answer is read a window per call, as the worker does
            # it over several rounds.
            while outcome.meer and not outcome.opnieuw_proberen:
                beurt = replace(beurt, gelezen_tot=outcome.gelezen_tot)
                outcome = await asyncio.wait_for(
                    service.beoordeel_beurt(beurt, context), TURN_TIMEOUT
                )
            answers = recorder.answers[before:]
            marked = [
                {
                    "soort": row[0],
                    "citaat": row[1],
                    "gericht_aan": row[2],
                    "samenvatting": row[3],
                    "herhaling": False,
                    "volgnummer": row[4],
                    "termijn": row[5],
                    "bij_volgnummer": row[6],
                }
                for row in (
                    await session.execute(
                        select(
                            DebatMarkering.soort,
                            DebatMarkering.citaat,
                            DebatMarkering.gericht_aan,
                            DebatMarkering.samenvatting,
                            DebatMarkering.volgnummer,
                            DebatMarkering.termijn,
                            DebatMarkering.bij_volgnummer,
                        )
                        .where(
                            DebatMarkering.sessie_id == sessie_id,
                            DebatMarkering.beurt_sleutel == beurt.sleutel,
                        )
                        .order_by(DebatMarkering.volgnummer)
                    )
                ).all()
            ]
            marked += [
                {"soort": row[0], "citaat": row[1], "herhaling": True}
                for row in (
                    await session.execute(
                        select(DebatMarkering.soort, DebatMarkeringVermelding.citaat)
                        .join(
                            DebatMarkering,
                            DebatMarkering.id == DebatMarkeringVermelding.markering_id,
                        )
                        .where(
                            DebatMarkeringVermelding.sessie_id == sessie_id,
                            DebatMarkeringVermelding.beurt_sleutel == beurt.sleutel,
                            # A toezegging that answers a question leaves a
                            # vermelding on that question. That is a link,
                            # not a second marking of the question.
                            DebatMarkeringVermelding.soort != VERMELDING_ANTWOORD,
                        )
                    )
                ).all()
            ]
            await session.commit()
            result = {
                "nr": turn["nr"],
                "uitkomst": outcome.uitkomst,
                "bewindspersoon": bool(turn.get("is_bewindspersoon")),
                "reden": outcome.reden,
                "afgevallen": outcome.afgevallen,
                "aanroepen": len(answers),
                # Every answer: a long turn of the bewindspersoon is asked
                # about in parts.
                "ruw": [
                    raw for answer in answers for raw in _raw_answer(recorder, answer)
                ],
                "gemarkeerd": marked,
            }
            block["beurten"].append(result)
            block["aanroepen"] += len(answers)
            if on_turn is not None:
                on_turn(turn, result)
        await _read_closing_list(
            session,
            service,
            recorder,
            context,
            gold["beurten"][:max_turns],
            block,
            sessie_id,
        )
    except BaseException:
        await session.rollback()
        raise
    finally:
        await session.execute(delete(DebatSessie).where(DebatSessie.id == sessie_id))
        await session.commit()
    return block
