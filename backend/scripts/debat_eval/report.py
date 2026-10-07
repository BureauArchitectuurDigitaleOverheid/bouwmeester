"""Score a saved run against its gold files and print the report.

    PYTHONPATH=scripts uv run python -m debat_eval.report <run.json> \
        [--compare <earlier-run.json>] [--check vraagvorm] [--gold-dir <dir>]

Asks no model and needs no database: a run holds everything the model
answered, so a changed gold file or a check on the quotes can be scored
again for free.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import gold as gold_file
from .scoring import (
    KindScore,
    Marking,
    answer_turns,
    format_comparison,
    format_report,
    gold_items,
    gold_negatives,
    miss_reasons,
    run_markings,
    score,
)
from .variants import CHECKS


def load_golds(run: dict, gold_dir: Path | None = None) -> dict[str, dict]:
    """The gold file of every debate in a run, by the name the run uses."""
    golds: dict[str, dict] = {}
    for debat in run["debatten"]:
        path = Path(debat["gold"])
        if gold_dir is not None:
            path = gold_dir / path.name
        golds[debat["naam"]] = gold_file.load(path)
    return golds


def apply_check(
    markings: list[Marking], check: str | None, kind: str = gold_file.KIND_VRAAG
) -> tuple[list[Marking], list[Marking]]:
    """The markings a check lets through, and the ones it stops."""
    if check is None:
        return markings, []
    passes = CHECKS[check]
    kept = [m for m in markings if m.soort != kind or passes(m.citaat)]
    return kept, [m for m in markings if m.soort == kind and not passes(m.citaat)]


# The kinds the production code marks today. A kind that is added there is
# added here, and its gold items start to count.
MARKED_KINDS: tuple[str, ...] = (
    gold_file.KIND_VRAAG,
    gold_file.KIND_MOTIE,
    gold_file.KIND_TOEZEGGING,
)


def score_run(
    run: dict,
    golds: dict[str, dict],
    check: str | None = None,
    kinds: tuple[str, ...] = MARKED_KINDS,
) -> tuple[dict[str, KindScore], list[Marking]]:
    items = [i for name, gold in golds.items() for i in gold_items(name, gold)]
    negatives = [n for name, gold in golds.items() for n in gold_negatives(name, gold)]
    markings, stopped = apply_check(run_markings(run), check)
    # Only what the debates of this run cover: a run cut short with
    # `--max-turns` says nothing about the turns it did not reach.
    reasons = miss_reasons(run)
    items = [i for i in items if (i.debat, i.beurt) in reasons]
    return (
        score(
            markings, items, negatives, reasons, kinds=kinds, answers=answer_turns(run)
        ),
        stopped,
    )


def not_marked(run: dict, golds: dict[str, dict]) -> str:
    """One line on the gold items of kinds the code does not mark yet."""
    reached = set(miss_reasons(run))
    counts: dict[str, int] = {}
    for name, gold in golds.items():
        for item in gold_items(name, gold):
            if item.soort not in MARKED_KINDS and (item.debat, item.beurt) in reached:
                counts[item.soort] = counts.get(item.soort, 0) + 1
    if not counts:
        return ""
    listed = ", ".join(f"{count} {kind}" for kind, count in sorted(counts.items()))
    return f"In de gouden set, door de code nog niet gemarkeerd: {listed}."


def summary_line(run: dict) -> str:
    meta = run.get("meta") or {}
    outcomes: dict[str, int] = {}
    for debat in run["debatten"]:
        for turn in debat["beurten"]:
            outcomes[turn["uitkomst"]] = outcomes.get(turn["uitkomst"], 0) + 1
    calls = sum(d.get("aanroepen", 0) for d in run["debatten"])
    turns = ", ".join(f"{count} {name}" for name, count in sorted(outcomes.items()))
    return (
        f"Run {meta.get('label') or '?'}: {meta.get('provider')} /"
        f" {meta.get('model')} / prompt {meta.get('prompt_variant')};"
        f" {len(run['debatten'])} debatten, {calls} aanroepen van het model;"
        f" beurten: {turns}"
    )


def build_report(
    run: dict,
    golds: dict[str, dict],
    *,
    compare: tuple[dict, dict[str, dict]] | None = None,
    check: str | None = None,
) -> str:
    scores, stopped = score_run(run, golds, check)
    speakers = {
        (name, turn["nr"]): turn["spreker"]
        for name, gold in golds.items()
        for turn in gold["beurten"]
    }
    parts = [summary_line(run)]
    if check is not None:
        parts.append(f"Check `{check}` houdt {len(stopped)} markeringen tegen.")
    parts.append("")
    parts.append(format_report(scores, speakers))
    rest = not_marked(run, golds)
    if rest:
        parts.append("")
        parts.append(rest)
    if compare is not None:
        earlier_run, earlier_golds = compare
        earlier, _ = score_run(earlier_run, earlier_golds)
        label = (earlier_run.get("meta") or {}).get("label") or "de vorige run"
        parts.append("")
        parts.append(format_comparison(scores, earlier, label))
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("run", type=Path)
    parser.add_argument("--compare", type=Path, help="an earlier run")
    parser.add_argument("--check", choices=sorted(CHECKS))
    parser.add_argument("--gold-dir", type=Path, help="where the gold files are now")
    args = parser.parse_args()

    run = json.loads(args.run.read_text(encoding="utf-8"))
    golds = load_golds(run, args.gold_dir)
    compare = None
    if args.compare:
        earlier = json.loads(args.compare.read_text(encoding="utf-8"))
        compare = (earlier, load_golds(earlier, args.gold_dir))
    print(build_report(run, golds, compare=compare, check=args.check))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
