"""How long after it was said a gold item was marked, and what a run cost.

    PYTHONPATH=scripts uv run python -m debat_eval.timing <run.json> \
        [--gold-dir <dir>]

For a run made with `run.py --replay`. Counted on the gold items a run
found: a marking of the same kind in the same turn that is the same
passage (`scoring.same_passage`). The delay is from the moment the line
was spoken in which the quote of the gold item begins, to the moment on
the clock of the replay at which the marking was stored. A gold item that
was not found has no delay; how many were, is said.

Next to it, per item, how long it would have waited for its turn to be
over and final: what reading every turn at its end costs on the same
clock, before the round and the call that then still follow.
"""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime
from pathlib import Path

from .gold import KIND_MOTIE, KIND_TOEZEGGING, KIND_VRAAG
from .replay import said_at
from .report import load_golds
from .scoring import same_passage
from .stats import WORDS_PER_HOUR

KINDS = (KIND_TOEZEGGING, KIND_VRAAG, KIND_MOTIE)


def percentile(values: list[float], share: float) -> float:
    """The value at a share of a sorted list, the nearest one that is there."""
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(share * (len(ordered) - 1)))]


def delays(run: dict, golds: dict[str, dict]) -> dict[str, list[tuple[float, float]]]:
    """Per kind, for every gold item a run found: the seconds from said to
    marked, and the seconds from said to the end of its turn."""
    found: dict[str, list[tuple[float, float]]] = {kind: [] for kind in KINDS}
    for debat in run.get("debatten") or []:
        gold = golds.get(debat["naam"])
        if gold is None:
            continue
        turns = {turn["nr"]: turn for turn in gold["beurten"]}
        results = {result["nr"]: result for result in debat["beurten"]}
        for item in gold.get("items") or []:
            result = results.get(item["beurt"])
            if item["soort"] not in found or result is None:
                continue
            said = said_at(turns[item["beurt"]], item["citaat"])
            marked = [
                datetime.fromisoformat(m["gemarkeerd_om"])
                for m in result.get("gemarkeerd") or []
                if m.get("gemarkeerd_om")
                and m["soort"] == item["soort"]
                and same_passage(m["citaat"], item["citaat"])
            ]
            if said is None or not marked or not result.get("klaar_om"):
                continue
            over = datetime.fromisoformat(result["klaar_om"])
            found[item["soort"]].append(
                (
                    (min(marked) - said).total_seconds(),
                    (over - said).total_seconds(),
                )
            )
    return found


def timing_report(run: dict, golds: dict[str, dict]) -> str:
    lines: list[str] = []
    clocks = [d.get("klok") for d in run.get("debatten") or [] if d.get("klok")]
    if not clocks:
        return "Deze run is niet op een klok afgespeeld (run.py --replay)."
    clock = clocks[0]
    lines.append(
        "Klok: ondertitels {subtitle_lag:.0f} s achter, stemmen {voices},"
        " een ronde per {round_seconds:.0f} s, een aanroep {call_seconds:.0f} s,"
        " meelezen {aan}.".format(aan="aan" if clock["meelezen"] else "uit", **clock)
    )
    lines.append(
        f"{'soort':<12}{'gevonden':>9}{'mediaan':>9}{'p90':>7}{'max':>7}"
        f"   tot einde beurt: {'mediaan':>7}{'p90':>7}{'max':>7}"
    )
    for kind, pairs in delays(run, golds).items():
        if not pairs:
            lines.append(f"{kind:<12}{0:>9}")
            continue
        own = [pair[0] for pair in pairs]
        end = [pair[1] for pair in pairs]
        lines.append(
            f"{kind:<12}{len(pairs):>9}{statistics.median(own):>9.0f}"
            f"{percentile(own, 0.9):>7.0f}{max(own):>7.0f}"
            f"   {'':17}{statistics.median(end):>7.0f}"
            f"{percentile(end, 0.9):>7.0f}{max(end):>7.0f}"
        )
    words = sum(
        len(turn["tekst"].split())
        for gold in golds.values()
        for turn in gold["beurten"]
    )
    hours = words / WORDS_PER_HOUR
    calls = sum(d.get("aanroepen", 0) for d in run.get("debatten") or [])
    answers = sum(
        turn.get("aanroepen", 0)
        for d in run.get("debatten") or []
        for turn in d["beurten"]
        if turn.get("bewindspersoon")
    )
    lines.append(
        f"Aanroepen: {calls} in {hours:.1f} uur spraak, waarvan {answers} voor"
        f" antwoorden van de bewindspersoon ({answers / hours:.1f} per uur)."
        if hours
        else f"Aanroepen: {calls}."
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("run", type=Path)
    parser.add_argument("--gold-dir", type=Path, help="where the gold files are now")
    args = parser.parse_args()
    run = json.loads(args.run.read_text(encoding="utf-8"))
    print(timing_report(run, load_golds(run, args.gold_dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
