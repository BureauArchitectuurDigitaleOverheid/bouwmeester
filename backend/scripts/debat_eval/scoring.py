"""Compare what was marked with what should have been marked.

Nothing in here reads a database or asks a model. A run and a gold file go
in, numbers and lists come out.

The rule for "the same passage": two quotes from the same turn match when
the words they share, in the same order and in runs of at least
`MIN_RUN` words, cover at least `MIN_SHARE` of the shorter quote. A model
that takes one sentence more or less than the labeller still matches; two
different questions that both say "de minister" do not.

Counting, per kind:

* A gold item counts as *required* unless the labeller was unsure of it or
  it repeats an earlier item. An optional item that is found is fine, one
  that is not found is not a miss.
* A marking is *right* when it matches a gold item of its kind, required or
  optional. Two markings on the same gold item are both right: the model
  cut one question in two.
* A marking that only matches a gold item of a kind in `ALSO_ACCEPTED` is
  left out of the count: a request for a letter is put to the bewindspersoon
  and is a question as the code understands it today.
* Every other marking is a false positive, named after the hard negative
  it matches, the other kind it matches, or `ongelabeld`.

Precision is right / (right + false positives), recall is required found /
required.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from .gold import (
    KIND_VERZOEK_OM_BRIEF,
    KIND_VRAAG,
    KINDS,
)

MIN_SHARE = 0.5
MIN_RUN = 3
UNLABELLED = "ongelabeld"

# Gold kinds a marking of the key kind may land on without being wrong.
ALSO_ACCEPTED: dict[str, frozenset[str]] = {
    KIND_VRAAG: frozenset({KIND_VERZOEK_OM_BRIEF}),
}

REASON_NOT_FOUND = "niet gevonden door het model"
REASON_DROPPED = "door het model genoemd, door de code afgekeurd"
REASON_SKIPPED = "beurt overgeslagen"
REASON_NOT_RUN = "beurt niet gedraaid"
REASON_FAILED = "model gaf geen bruikbaar antwoord"


def words(text: str) -> list[str]:
    """The words of a quote, without case, accents or punctuation."""
    flat = unicodedata.normalize("NFKD", text.lower())
    flat = "".join(c for c in flat if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", flat)


def shared_share(a: str, b: str) -> float:
    """How much of the shorter quote the two have in common, 0 to 1."""
    first, second = words(a), words(b)
    shortest = min(len(first), len(second))
    if not shortest:
        return 0.0
    run = min(MIN_RUN, shortest)
    blocks = difflib.SequenceMatcher(
        None, first, second, autojunk=False
    ).get_matching_blocks()
    return sum(b.size for b in blocks if b.size >= run) / shortest


def same_passage(a: str, b: str) -> bool:
    return shared_share(a, b) >= MIN_SHARE


@dataclass(frozen=True)
class Marking:
    """One thing that was marked in a run."""

    debat: str
    beurt: int
    soort: str
    citaat: str
    gericht_aan: str = ""
    samenvatting: str = ""
    herhaling: bool = False


@dataclass(frozen=True)
class GoldItem:
    debat: str
    beurt: int
    soort: str
    citaat: str
    onzeker: bool = False
    herhaling: bool = False
    notitie: str = ""

    @property
    def required(self) -> bool:
        return not self.onzeker and not self.herhaling


@dataclass(frozen=True)
class Negative:
    debat: str
    beurt: int
    type: str
    citaat: str


@dataclass(frozen=True)
class Miss:
    item: GoldItem
    reason: str


@dataclass(frozen=True)
class FalsePositive:
    marking: Marking
    category: str


@dataclass
class KindScore:
    soort: str
    required: int = 0
    found: int = 0
    optional: int = 0
    optional_found: int = 0
    marked: int = 0
    right: int = 0
    left_out: int = 0
    misses: list[Miss] = field(default_factory=list)
    false_positives: list[FalsePositive] = field(default_factory=list)

    @property
    def precision(self) -> float | None:
        counted = self.right + len(self.false_positives)
        return self.right / counted if counted else None

    @property
    def recall(self) -> float | None:
        return self.found / self.required if self.required else None

    @property
    def fp_categories(self) -> Counter[str]:
        return Counter(fp.category for fp in self.false_positives)

    @property
    def miss_reasons(self) -> Counter[str]:
        return Counter(miss.reason for miss in self.misses)


def gold_items(name: str, gold: dict) -> list[GoldItem]:
    return [
        GoldItem(
            debat=name,
            beurt=item["beurt"],
            soort=item["soort"],
            citaat=item["citaat"],
            onzeker=bool(item.get("onzeker")),
            herhaling=bool(item.get("herhaling")),
            notitie=item.get("notitie") or "",
        )
        for item in gold.get("items") or []
    ]


def gold_negatives(name: str, gold: dict) -> list[Negative]:
    return [
        Negative(name, neg["beurt"], neg["type"], neg["citaat"])
        for neg in gold.get("negatieven") or []
    ]


def run_markings(run: dict) -> list[Marking]:
    """Everything a run marked, over all its debates."""
    found: list[Marking] = []
    for debat in run.get("debatten") or []:
        for turn in debat.get("beurten") or []:
            for raw in turn.get("gemarkeerd") or []:
                found.append(
                    Marking(
                        debat=debat["naam"],
                        beurt=turn["nr"],
                        soort=raw["soort"],
                        citaat=raw["citaat"],
                        gericht_aan=raw.get("gericht_aan") or "",
                        samenvatting=raw.get("samenvatting") or "",
                        herhaling=bool(raw.get("herhaling")),
                    )
                )
    return found


def miss_reasons(run: dict) -> dict[tuple[str, int], tuple[str, list[str]]]:
    """Per turn of a run: what became of it, and the quotes the model gave.

    The quotes include those the code dropped afterwards, so a miss can be
    told apart: the model never saw the question, or the code threw it out.
    """
    turns: dict[tuple[str, int], tuple[str, list[str]]] = {}
    for debat in run.get("debatten") or []:
        for turn in debat.get("beurten") or []:
            outcome = turn.get("uitkomst") or ""
            if outcome == "overgeslagen":
                reason = f"{REASON_SKIPPED}: {turn.get('reden') or '?'}"
            elif outcome.startswith("llm_"):
                reason = REASON_FAILED
            else:
                reason = REASON_NOT_FOUND
            raw = [r.get("citaat") or "" for r in turn.get("ruw") or []]
            turns[(debat["naam"], turn["nr"])] = (reason, raw)
    return turns


def _best(quote: str, candidates: Iterable[tuple[str, str]]) -> str | None:
    """The name of the candidate that shares most with the quote, if any does."""
    best_name, best_share = None, 0.0
    for name, text in candidates:
        share = shared_share(quote, text)
        if share >= MIN_SHARE and share > best_share:
            best_name, best_share = name, share
    return best_name


def score(
    markings: Sequence[Marking],
    items: Sequence[GoldItem],
    negatives: Sequence[Negative] = (),
    turns: dict[tuple[str, int], tuple[str, list[str]]] | None = None,
    kinds: Sequence[str] = KINDS,
) -> dict[str, KindScore]:
    """The score per kind. `turns` is `miss_reasons(run)`, for why a miss."""
    by_turn_items: dict[tuple[str, int], list[GoldItem]] = {}
    for item in items:
        by_turn_items.setdefault((item.debat, item.beurt), []).append(item)
    by_turn_negatives: dict[tuple[str, int], list[Negative]] = {}
    for negative in negatives:
        by_turn_negatives.setdefault((negative.debat, negative.beurt), []).append(
            negative
        )
    by_turn_markings: dict[tuple[str, int, str], list[Marking]] = {}
    for marking in markings:
        by_turn_markings.setdefault(
            (marking.debat, marking.beurt, marking.soort), []
        ).append(marking)

    scores: dict[str, KindScore] = {}
    for kind in kinds:
        result = KindScore(kind)
        accepted = ALSO_ACCEPTED.get(kind, frozenset())

        for item in (i for i in items if i.soort == kind):
            marked = by_turn_markings.get((item.debat, item.beurt, kind), [])
            hit = any(same_passage(m.citaat, item.citaat) for m in marked)
            if item.required:
                result.required += 1
                result.found += hit
            else:
                result.optional += 1
                result.optional_found += hit
            if item.required and not hit:
                reason, raw = REASON_NOT_RUN, []
                if turns is not None and (item.debat, item.beurt) in turns:
                    reason, raw = turns[(item.debat, item.beurt)]
                if reason == REASON_NOT_FOUND and any(
                    same_passage(quote, item.citaat) for quote in raw
                ):
                    reason = REASON_DROPPED
                result.misses.append(Miss(item, reason))

        for marking in (m for m in markings if m.soort == kind):
            result.marked += 1
            here = by_turn_items.get((marking.debat, marking.beurt), [])
            if any(
                i.soort == kind and same_passage(marking.citaat, i.citaat) for i in here
            ):
                result.right += 1
                continue
            other = _best(
                marking.citaat, ((i.soort, i.citaat) for i in here if i.soort != kind)
            )
            if other in accepted:
                result.left_out += 1
                continue
            negative = _best(
                marking.citaat,
                (
                    (n.type, n.citaat)
                    for n in by_turn_negatives.get((marking.debat, marking.beurt), [])
                ),
            )
            category = negative or (f"soort:{other}" if other else UNLABELLED)
            result.false_positives.append(FalsePositive(marking, category))
        scores[kind] = result
    return scores


# --- the report --------------------------------------------------------


def _pct(value: float | None) -> str:
    return "   -" if value is None else f"{100 * value:3.0f}%"


def _cut(text: str, limit: int = 220) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def format_table(scores: dict[str, KindScore]) -> str:
    """One line per kind that has gold items or markings."""
    lines = [
        f"{'soort':<18}{'gold':>5}{'gevonden':>9}{'gemist':>7}"
        f"{'gemarkeerd':>11}{'goed':>5}{'fout':>5}{'precisie':>9}{'recall':>7}"
    ]
    for kind, result in scores.items():
        if not result.required and not result.optional and not result.marked:
            continue
        lines.append(
            f"{kind:<18}{result.required:>5}{result.found:>9}"
            f"{len(result.misses):>7}{result.marked:>11}{result.right:>5}"
            f"{len(result.false_positives):>5}{_pct(result.precision):>9}"
            f"{_pct(result.recall):>7}"
        )
    return "\n".join(lines)


def format_report(
    scores: dict[str, KindScore], speakers: dict[tuple[str, int], str] | None = None
) -> str:
    """The table, then per kind the misses and false positives to judge."""
    speakers = speakers or {}

    def where(debat: str, beurt: int) -> str:
        who = speakers.get((debat, beurt))
        return f"{debat} beurt {beurt}" + (f" ({who})" if who else "")

    parts = [format_table(scores)]
    for kind, result in scores.items():
        if not result.misses and not result.false_positives and not result.marked:
            continue
        parts.append(f"\n## {kind}")
        if result.optional:
            parts.append(
                f"Optioneel (onzeker of herhaling): {result.optional_found} van"
                f" {result.optional} gevonden."
            )
        if result.left_out:
            parts.append(
                f"Buiten de telling: {result.left_out} markeringen op een item van"
                " een soort die ook mag."
            )
        if result.misses:
            parts.append(f"\nGemist ({len(result.misses)}):")
            for reason, count in result.miss_reasons.most_common():
                parts.append(f"  {count:>3} × {reason}")
            for miss in result.misses:
                parts.append(
                    f"- {where(miss.item.debat, miss.item.beurt)} [{miss.reason}]"
                    f"\n    {_cut(miss.item.citaat)}"
                )
        if result.false_positives:
            parts.append(f"\nTen onrechte gemarkeerd ({len(result.false_positives)}):")
            for category, count in result.fp_categories.most_common():
                parts.append(f"  {count:>3} × {category}")
            for fp in result.false_positives:
                parts.append(
                    f"- {where(fp.marking.debat, fp.marking.beurt)} [{fp.category}]"
                    f"\n    citaat: {_cut(fp.marking.citaat)}"
                    + (
                        f"\n    samenvatting: {_cut(fp.marking.samenvatting)}"
                        if fp.marking.samenvatting
                        else ""
                    )
                )
    return "\n".join(parts)


def _delta(now: float | None, before: float | None) -> str:
    if now is None or before is None:
        return ""
    return f" ({100 * (now - before):+.0f})"


def format_comparison(
    now: dict[str, KindScore], before: dict[str, KindScore], label: str = "vorige"
) -> str:
    """What changed against an earlier run: the numbers, then the items."""
    lines = [f"## Vergeleken met {label}"]
    for kind, result in now.items():
        earlier = before.get(kind)
        if earlier is None or not (result.marked or earlier.marked):
            continue
        lines.append(
            f"{kind}: precisie {_pct(result.precision).strip()}"
            f"{_delta(result.precision, earlier.precision)}, recall"
            f" {_pct(result.recall).strip()}{_delta(result.recall, earlier.recall)},"
            f" gevonden {result.found} ({result.found - earlier.found:+d}), fout"
            f" {len(result.false_positives)}"
            f" ({len(result.false_positives) - len(earlier.false_positives):+d})"
        )
        missed_now = {
            (m.item.debat, m.item.beurt, m.item.citaat) for m in result.misses
        }
        missed_before = {
            (m.item.debat, m.item.beurt, m.item.citaat) for m in earlier.misses
        }
        for title, keys in (
            ("Nu gevonden, eerder gemist", missed_before - missed_now),
            ("Nu gemist, eerder gevonden", missed_now - missed_before),
        ):
            if keys:
                lines.append(f"  {title} ({len(keys)}):")
                lines.extend(
                    f"  - {debat} beurt {beurt}: {_cut(quote, 160)}"
                    for debat, beurt, quote in sorted(keys)
                )
        for title, new, old in (
            ("Nieuw ten onrechte", result.false_positives, earlier.false_positives),
            ("Niet meer ten onrechte", earlier.false_positives, result.false_positives),
        ):
            changed = [
                fp
                for fp in new
                if not any(
                    o.marking.debat == fp.marking.debat
                    and o.marking.beurt == fp.marking.beurt
                    and same_passage(o.marking.citaat, fp.marking.citaat)
                    for o in old
                )
            ]
            if changed:
                lines.append(f"  {title} ({len(changed)}):")
                lines.extend(
                    f"  - {fp.marking.debat} beurt {fp.marking.beurt}"
                    f" [{fp.category}]: {_cut(fp.marking.citaat, 160)}"
                    for fp in changed
                )
    return "\n".join(lines)
