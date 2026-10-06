"""Turn a recorded debate into the turns of a gold file.

Reads subtitle lines (a directory of WebVTT files, or a `cues.jsonl`) and
the events of Debat Direct, and puts each line under whoever had the floor,
the way production does: `parse_vtt` and `place_cues` with the offset the
feed gives, speakers and their labels from `fetch_sprekers`, and
`is_bewindspersoon` to tell who answers. Voices are not used, so around a
change of speaker a sentence can sit one turn too early or too late.

The output has no labels yet: `items` and `negatieven` are empty lists for
a person to fill in. It holds real names and real text. Write it outside
the repository.

    DEV_NO_AUTH=1 PYTHONPATH=scripts uv run python -m debat_eval.build_turns \
        --debate-id <id> --vtt-dir <dir> --cache <dir> --out <file>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx

from bouwmeester.services import debat_direct as dd
from bouwmeester.services.debat_subtitles import Cue, SubtitleError, parse_vtt
from bouwmeester.services.debat_transcript import append_text, place_cues
from bouwmeester.services.debat_vraag_service import is_bewindspersoon

TURN_KINDS = (dd.EVENT_SPEAKER, dd.EVENT_INTERRUPTER, dd.EVENT_CHAIRMAN)
_STAMP_NAME = re.compile(r"^(\d{14})(\d{3})\.vtt$")
_TICKS_NAME = re.compile(r"^Segment-(\d+)\.")
_HEADERS = {"User-Agent": "Mozilla/5.0"}


def segment_start(name: str) -> datetime | None:
    """When the segment of a subtitle file began, read from its name.

    Two shapes: `20261005080140160.vtt` (UTC, to the millisecond) and
    `Segment-<ticks>...` where ticks / 1e7 is the unix time.
    """
    stamp = _STAMP_NAME.match(name)
    if stamp:
        whole = datetime.strptime(stamp.group(1), "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        return whole + timedelta(milliseconds=int(stamp.group(2)))
    ticks = _TICKS_NAME.match(name)
    if ticks:
        return datetime.fromtimestamp(int(ticks.group(1)) / 1e7, tz=UTC)
    return None


def read_vtt_dir(directory: Path) -> list[Cue]:
    cues: list[Cue] = []
    for path in sorted(directory.iterdir()):
        start = segment_start(path.name)
        if start is None:
            continue
        try:
            cues.extend(parse_vtt(path.read_text(encoding="utf-8"), start))
        except SubtitleError:
            continue
    return cues


def read_cues_jsonl(path: Path) -> list[Cue]:
    cues: list[Cue] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        cues.append(
            Cue(
                datetime.fromisoformat(raw["start"]),
                datetime.fromisoformat(raw["end"]),
                raw["text"],
            )
        )
    return cues


def unique_cues(cues: list[Cue]) -> list[Cue]:
    """One of every line: recordings of the same stretch overlap."""
    seen: set[tuple[int, str]] = set()
    kept: list[Cue] = []
    for cue in sorted(cues, key=lambda c: c.start):
        key = (round(cue.start.timestamp() * 10), cue.text)
        if key not in seen:
            seen.add(key)
            kept.append(cue)
    return kept


def cached_json(url: str, target: Path) -> dict:
    """Fetch once, then read from disk: the API is not ours to hammer."""
    if not target.exists():
        request = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(request, timeout=30) as response:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(response.read())
    return json.loads(target.read_text(encoding="utf-8"))


def sprekers_from(actors: dict, day: date) -> dict[str, dd.Spreker]:
    """The speakers of a day, read by the application's own `fetch_sprekers`."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=actors)

    async def read() -> dict[str, dd.Spreker]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await dd.fetch_sprekers(client, day)

    return asyncio.run(read())


def build_turns(
    debat: dd.DdDebat, sprekers: dict[str, dd.Spreker], cues: list[Cue]
) -> list[dict]:
    """Every event that gives someone the floor, with what was said in it.

    An interruption remembers who had the floor: the last `speaker` event
    before it, as the worker does. Turns without text are left out.
    """
    events = [e for e in debat.events if e.type in TURN_KINDS]
    placed = place_cues(
        cues, [(i, e.start) for i, e in enumerate(events)], debat.stream_offset
    )
    texts: dict[int, str] = {}
    for index, cue in placed:
        texts[index] = append_text(texts.get(index), cue.text)

    turns: list[dict] = []
    floor: dd.Spreker | None = None
    for index, event in enumerate(events):
        spreker = sprekers.get(event.object_id)
        if event.type == dd.EVENT_SPEAKER:
            floor = spreker
        text = texts.get(index, "")
        if not text:
            continue
        if event.type == dd.EVENT_CHAIRMAN:
            label, fractie, minister = "de voorzitter", None, False
        elif spreker is None:
            label, fractie, minister = "(onbekend)", None, False
        else:
            label, fractie = spreker.label, spreker.fractie
            minister = is_bewindspersoon(spreker)
        onderbroken = floor if event.type == dd.EVENT_INTERRUPTER else None
        turns.append(
            {
                "nr": len(turns) + 1,
                "soort": event.type,
                "spreker": label,
                "fractie": fractie,
                "is_bewindspersoon": minister,
                "start": (event.start + debat.stream_offset).isoformat(),
                "onderbroken": onderbroken.label if onderbroken else None,
                "onderbroken_is_bewindspersoon": bool(
                    onderbroken and is_bewindspersoon(onderbroken)
                ),
                "tekst": text,
            }
        )
    return turns


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--debate-id")
    parser.add_argument("--debate-json", type=Path, help="saved detail call")
    parser.add_argument("--actors-json", type=Path, help="saved actors call")
    parser.add_argument("--vtt-dir", type=Path, action="append", default=[])
    parser.add_argument("--cues-jsonl", type=Path)
    parser.add_argument("--cache", type=Path, help="where fetched JSON is kept")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    if args.debate_json:
        raw = json.loads(args.debate_json.read_text(encoding="utf-8"))
    elif args.debate_id and args.cache:
        raw = cached_json(
            f"{dd.DD_API_URL}/debates/{args.debate_id}",
            args.cache / f"debate-{args.debate_id}.json",
        )
    else:
        parser.error("--debate-json, or --debate-id with --cache")
    debat = dd.parse_debate(raw)
    if debat is None or not debat.debate_date:
        print("Debate has no id or no date", file=sys.stderr)
        return 1

    if args.actors_json:
        actors = json.loads(args.actors_json.read_text(encoding="utf-8"))
    elif args.cache:
        actors = cached_json(
            f"{dd.DD_API_URL}/actors/{debat.debate_date}",
            args.cache / f"actors-{debat.debate_date}.json",
        )
    else:
        parser.error("--actors-json or --cache")
    sprekers = sprekers_from(actors, date.fromisoformat(debat.debate_date))

    cues: list[Cue] = []
    for directory in args.vtt_dir:
        cues.extend(read_vtt_dir(directory))
    if args.cues_jsonl:
        cues.extend(read_cues_jsonl(args.cues_jsonl))
    cues = unique_cues(cues)
    if debat.ended_at is not None:
        # What is said in the room after the debate is another debate.
        last = debat.ended_at + debat.stream_offset
        cues = [cue for cue in cues if cue.start <= last]
    for earlier, later in zip(cues, cues[1:], strict=False):
        if later.start - earlier.end > timedelta(minutes=3):
            print(f"no lines from {earlier.end:%H:%M:%S} to {later.start:%H:%M:%S} UTC")
    turns = build_turns(debat, sprekers, cues)

    aan_tafel = []
    # Who is expected at the table, and whoever spoke without being expected.
    expected = [str(i) for i in raw.get("politicianIds") or []]
    for object_id in dict.fromkeys([*expected, *(e.object_id for e in debat.events)]):
        spreker = sprekers.get(object_id)
        if spreker and is_bewindspersoon(spreker):
            aan_tafel.append({"naam": spreker.naam, "functie": spreker.titel})
    gold = {
        "debat": {
            "id": debat.id,
            "onderwerp": debat.name,
            "soort": debat.debate_type,
            "bewindspersonen": aan_tafel,
            "stukken": [debat.name],
            "initiatiefnemers": "initiatief" in debat.name.lower(),
            "regels_van": cues[0].start.isoformat() if cues else None,
            "regels_tot": cues[-1].end.isoformat() if cues else None,
        },
        "beurten": turns,
        "items": [],
        "negatieven": [],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(gold, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    words = sum(len(t["tekst"].split()) for t in turns)
    print(f"{args.out.name}: {len(cues)} lines, {len(turns)} turns, {words} words")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
