"""Run the production code path for marking over the turns of a gold file.

`DebatVraagService.beoordeel_beurt` is called for every turn, in order,
exactly as the worker does: the service decides itself which turns it
skips, builds the prompt, reads the answer and stores what it accepts. The
database is real, Mattermost is a stand-in that remembers what it is sent,
and the model is whatever `BaseLLMService` is handed in, wrapped so that
its raw answers can be kept and its prompt can be rewritten on the way.

What comes back per turn: what the service made of it, what the model
answered (also what the code dropped afterwards), and what was stored.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.debat_markering import (
    DebatMarkering,
    DebatMarkeringVermelding,
)
from bouwmeester.models.debat_sessie import DebatSessie
from bouwmeester.services.debat_vraag_service import (
    Beurt,
    DebatContext,
    DebatVraagService,
)
from bouwmeester.services.llm import base as llm_base
from bouwmeester.services.llm.base import (
    BaseLLMService,
    DataSensitivity,
    ProviderCapabilities,
)
from bouwmeester.services.tk_activiteit import Bewindspersoon, Initiatiefnemer

from .gold import KIND_VRAAG

CHANNEL = "evalchannel000000000000000"
TEAM = "evalteam000000000000000000"
TURN_TIMEOUT = 300
_TURN_TEXT = re.compile(r"<spreekbeurt>\n(.*)\n</spreekbeurt>", re.DOTALL)


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
    """A model that answers with the gold questions of the turn it is shown.

    For trying the harness without a model, and for tests: what the code
    then misses or drops is the doing of the code alone.
    """

    capabilities = ProviderCapabilities(allowed_data={DataSensitivity.PUBLIC})

    def __init__(self, gold: dict, kinds: tuple[str, ...] = (KIND_VRAAG,)) -> None:
        self.turns = [(t["tekst"], t["nr"]) for t in gold["beurten"]]
        self.items: dict[int, list[dict]] = {}
        for item in gold.get("items") or []:
            if item["soort"] in kinds:
                self.items.setdefault(item["beurt"], []).append(item)

    async def _complete(self, prompt: str, max_tokens: int = 1024) -> str:
        import json

        shown = _TURN_TEXT.search(prompt)
        text = (shown.group(1) if shown else "").removeprefix("(...) ")
        number = next((nr for full, nr in self.turns if full.endswith(text)), None)
        vragen = [
            {
                "citaat": item["citaat"],
                "gericht_aan": f"de {item.get('gericht_aan') or 'minister'}",
                "samenvatting": "Vraag uit de gouden set.",
                "hoort_bij": None,
                "stuk": None,
            }
            for item in self.items.get(number, [])
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


def beurt_from(turn: dict, sessie_id: uuid.UUID) -> Beurt:
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
    )


def _raw_answer(llm: RecordingLLM, text: str) -> list[dict]:
    """What the model said, read the way production reads it."""
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
        for turn in gold["beurten"][:max_turns]:
            beurt = beurt_from(turn, sessie_id)
            mattermost.messages[beurt.post_id] = turn["tekst"][:200]
            before = len(recorder.answers)
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
                }
                for row in (
                    await session.execute(
                        select(
                            DebatMarkering.soort,
                            DebatMarkering.citaat,
                            DebatMarkering.gericht_aan,
                            DebatMarkering.samenvatting,
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
                        )
                    )
                ).all()
            ]
            await session.commit()
            result = {
                "nr": turn["nr"],
                "uitkomst": outcome.uitkomst,
                "reden": outcome.reden,
                "afgevallen": outcome.afgevallen,
                "aanroepen": len(answers),
                "ruw": _raw_answer(recorder, answers[-1]) if answers else [],
                "gemarkeerd": marked,
            }
            block["beurten"].append(result)
            block["aanroepen"] += len(answers)
            if on_turn is not None:
                on_turn(turn, result)
    except BaseException:
        await session.rollback()
        raise
    finally:
        await session.execute(delete(DebatSessie).where(DebatSessie.id == sessie_id))
        await session.commit()
    return block
