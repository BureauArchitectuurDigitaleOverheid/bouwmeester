"""The gold file: the turns of one debate and what a person marked in them.

    {
      "debat": {"onderwerp", "soort", "bewindspersonen": [{"naam", "functie"}],
                "stukken": [...], "initiatiefnemers": bool,
                "initiatiefnemer_namen": [{"naam", "fractie"}]},
      "beurten": [{"nr", "soort", "spreker", "fractie", "is_bewindspersoon",
                   "start", "onderbroken", "onderbroken_is_bewindspersoon",
                   "tekst"}],
      "items": [{"beurt", "soort", "citaat", "gericht_aan", "onzeker",
                 "herhaling", "notitie"}],
      "negatieven": [{"beurt", "type", "citaat", "notitie"}]
    }

`items` are what should be marked, `negatieven` are passages that look like
it and should not be. Every quote stands literally in the text of its turn.
"""

from __future__ import annotations

import json
from pathlib import Path

KIND_VRAAG = "vraag"
KIND_TOEZEGGING = "toezegging"
KIND_VERZOEK_OM_BRIEF = "verzoek_om_brief"
KIND_MOTIE = "motie"
KIND_FEITELIJKE_CLAIM = "feitelijke_claim"
KINDS = (
    KIND_VRAAG,
    KIND_TOEZEGGING,
    KIND_VERZOEK_OM_BRIEF,
    KIND_MOTIE,
    KIND_FEITELIJKE_CLAIM,
)

# The hard negatives the codebook names. Others may occur in a gold file.
NEG_RETORISCH = "retorisch"
NEG_AAN_KAMERLID = "aan_kamerlid"
NEG_AAN_INITIATIEFNEMERS = "aan_initiatiefnemers"
NEG_OVER_KABINET = "over_kabinet"
NEG_STELLING = "stelling"


class GoldError(ValueError):
    pass


def validate(gold: dict) -> list[str]:
    """What is wrong with a gold file, as sentences. Empty when sound."""
    problems: list[str] = []
    turns = gold.get("beurten")
    if not isinstance(turns, list) or not turns:
        return ["no turns"]
    texts: dict[int, str] = {}
    for turn in turns:
        number = turn.get("nr")
        if number in texts:
            problems.append(f"turn {number} occurs twice")
        texts[number] = turn.get("tekst") or ""
    for item in gold.get("items") or []:
        where = f"item in turn {item.get('beurt')}"
        if item.get("soort") not in KINDS:
            problems.append(f"{where}: unknown kind {item.get('soort')!r}")
        problems.extend(_quote_problem(where, item, texts))
    for negative in gold.get("negatieven") or []:
        where = f"negative in turn {negative.get('beurt')}"
        if not negative.get("type"):
            problems.append(f"{where}: no type")
        problems.extend(_quote_problem(where, negative, texts))
    return problems


def _quote_problem(where: str, entry: dict, texts: dict[int, str]) -> list[str]:
    text = texts.get(entry.get("beurt"))
    if text is None:
        return [f"{where}: no such turn"]
    quote = entry.get("citaat") or ""
    if not quote:
        return [f"{where}: no quote"]
    if quote not in text:
        return [f"{where}: quote is not in the turn: {quote[:60]!r}"]
    return []


def load(path: Path) -> dict:
    gold = json.loads(path.read_text(encoding="utf-8"))
    problems = validate(gold)
    if problems:
        raise GoldError(f"{path.name}: " + "; ".join(problems[:5]))
    return gold
