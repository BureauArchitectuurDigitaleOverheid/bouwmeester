"""Write labels into a gold file from a short text file.

Typing a quote of three sentences by hand goes wrong. A label therefore
names the turn and the first and last words of the passage; the quote is
cut from the text of the turn, so it is in it by construction.

One label a line:

    <turn> <kind> [@whom] [?] [h] :: <first words> >>> <last words> ## note

* `<kind>` is a kind of marking (`vraag`, `toezegging`, `verzoek_om_brief`,
  `motie`, `feitelijke_claim`), or a hard negative written with a dash in
  front (`-retorisch`, `-aan_kamerlid`, `-over_kabinet`, ...).
* `@whom` is who it is put to, `?` marks a label the labeller is unsure
  of, `h` a question that repeats an earlier one.
* Without `>>>` the words before `##` are the whole quote.
* Empty lines and lines that start with `#` are skipped.

    PYTHONPATH=scripts uv run python -m debat_eval.apply_labels \
        <turns.json> <labels.txt> <gold.json>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .gold import KINDS

SPAN = ">>>"


class LabelError(ValueError):
    pass


def cut_quote(text: str, first: str, last: str | None) -> str:
    """The passage of `text` from `first` up to and including `last`."""
    begin = text.find(first)
    if begin == -1:
        raise LabelError(f"not in the turn: {first!r}")
    if last is None:
        return first
    end = text.find(last, begin)
    if end == -1:
        raise LabelError(f"not in the turn after the first words: {last!r}")
    return text[begin : end + len(last)]


def parse_label(line: str, texts: dict[int, str]) -> tuple[str, dict]:
    """One line as (`items` or `negatieven`, the entry)."""
    head, separator, rest = line.partition("::")
    if not separator:
        raise LabelError("no '::'")
    words = head.split()
    if len(words) < 2 or not words[0].isdigit():
        raise LabelError("a label starts with the number of a turn and a kind")
    turn, kind, flags = int(words[0]), words[1], words[2:]
    if turn not in texts:
        raise LabelError(f"no turn {turn}")
    passage, _, note = rest.partition("##")
    first, span, last = passage.partition(SPAN)
    quote = cut_quote(texts[turn], first.strip(), last.strip() if span else None)
    entry: dict = {"beurt": turn}
    whom = [flag[1:] for flag in flags if flag.startswith("@")]
    unknown = [f for f in flags if not f.startswith("@") and f not in ("?", "h")]
    if unknown:
        raise LabelError(f"unknown flag {unknown[0]!r}")
    if kind.startswith("-"):
        entry |= {"type": kind[1:], "citaat": quote}
        target = "negatieven"
    elif kind in KINDS:
        entry |= {
            "soort": kind,
            "citaat": quote,
            "gericht_aan": whom[0] if whom else None,
            "onzeker": "?" in flags,
            "herhaling": "h" in flags,
        }
        target = "items"
    else:
        raise LabelError(f"unknown kind {kind!r}")
    if note.strip():
        entry["notitie"] = note.strip()
    return target, entry


def apply_labels(gold: dict, lines: list[str]) -> list[str]:
    """Replace the labels of `gold` by those in `lines`; returns the errors."""
    texts = {turn["nr"]: turn["tekst"] for turn in gold["beurten"]}
    found: dict[str, list[dict]] = {"items": [], "negatieven": []}
    errors: list[str] = []
    for number, line in enumerate(lines, start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            target, entry = parse_label(line, texts)
        except LabelError as exc:
            errors.append(f"line {number}: {exc}")
            continue
        found[target].append(entry)
    gold["items"] = found["items"]
    gold["negatieven"] = found["negatieven"]
    return errors


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__.split("\n\n")[-1].strip(), file=sys.stderr)
        return 2
    turns, labels, target = (Path(arg) for arg in sys.argv[1:])
    gold = json.loads(turns.read_text(encoding="utf-8"))
    errors = apply_labels(gold, labels.read_text(encoding="utf-8").splitlines())
    for error in errors:
        print(error, file=sys.stderr)
    target.write_text(
        json.dumps(gold, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(
        f"{target.name}: {len(gold['items'])} items,"
        f" {len(gold['negatieven'])} negatives, {len(errors)} errors"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
