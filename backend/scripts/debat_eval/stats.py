"""Count what is in gold files: turns, items per kind, hard negatives.

    PYTHONPATH=scripts uv run python -m debat_eval.stats <gold.json>...

"Per hour" is per hour of speech, taken as `WORDS_PER_HOUR` words of
transcript: a recording has holes and suspensions, the words that were
caught do not.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from . import gold as gold_file
from .variants import has_question_form

# Measured on the committee debates of the first gold set: 160 a minute.
WORDS_PER_HOUR = 9600


def describe(golds: dict[str, dict]) -> str:
    lines: list[str] = []
    total_words = 0
    kinds: Counter[str] = Counter()
    unsure: Counter[str] = Counter()
    repeats: Counter[str] = Counter()
    negatives: Counter[str] = Counter()
    who: Counter[tuple[str, str]] = Counter()
    for name, gold in golds.items():
        turns = {turn["nr"]: turn for turn in gold["beurten"]}
        count = sum(len(turn["tekst"].split()) for turn in turns.values())
        total_words += count
        per_kind = Counter(item["soort"] for item in gold["items"])
        lines.append(
            f"{name}: {len(turns)} beurten, {count} woorden"
            f" ({count / WORDS_PER_HOUR:.1f} uur spraak), "
            + ", ".join(f"{per_kind[k]} {k}" for k in gold_file.KINDS)
            + f", {len(gold['negatieven'])} negatieven"
        )
        for item in gold["items"]:
            kind = item["soort"]
            if item.get("herhaling"):
                repeats[kind] += 1
            elif item.get("onzeker"):
                unsure[kind] += 1
            else:
                kinds[kind] += 1
            turn = turns[item["beurt"]]
            if turn["soort"] == "chairman":
                speaker = "voorzitter"
            elif turn["is_bewindspersoon"]:
                speaker = "bewindspersoon"
            else:
                speaker = "Kamerlid"
            who[(kind, speaker)] += 1
        negatives.update(neg["type"] for neg in gold["negatieven"])

    hours = total_words / WORDS_PER_HOUR
    lines.append("")
    lines.append(f"Samen {total_words} woorden, {hours:.1f} uur spraak.")
    lines.append(
        f"{'soort':<18}{'zeker':>6}{'onzeker':>8}{'herhaling':>10}{'per uur':>8}"
        "  in een beurt van"
    )
    for kind in gold_file.KINDS:
        speakers = ", ".join(
            f"{count} {speaker}"
            for (k, speaker), count in sorted(who.items())
            if k == kind
        )
        lines.append(
            f"{kind:<18}{kinds[kind]:>6}{unsure[kind]:>8}{repeats[kind]:>10}"
            f"{kinds[kind] / hours if hours else 0:>8.1f}  {speakers}"
        )
    lines.append("")
    lines.append(
        "Lastige negatieven: "
        + ", ".join(f"{count} {kind}" for kind, count in negatives.most_common())
    )
    questions = [
        item["citaat"]
        for gold in golds.values()
        for item in gold["items"]
        if item["soort"] == gold_file.KIND_VRAAG
    ]
    without = [quote for quote in questions if not has_question_form(quote)]
    lines.append(
        f"Vraagvorm: {len(questions) - len(without)} van {len(questions)}"
        " gouden vragen hebben de vorm van een vraag of verzoek."
    )
    lines.extend(f"  zonder vraagvorm: {quote[:160]}" for quote in without)
    stopped = Counter(
        neg["type"]
        for gold in golds.values()
        for neg in gold["negatieven"]
        if not has_question_form(neg["citaat"])
    )
    lines.append(
        "Negatieven zonder vraagvorm: "
        + ", ".join(
            f"{stopped[kind]}/{count} {kind}" for kind, count in negatives.most_common()
        )
    )
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__.split("\n\n")[1].strip(), file=sys.stderr)
        return 2
    golds = {Path(arg).stem: gold_file.load(Path(arg)) for arg in sys.argv[1:]}
    print(describe(golds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
