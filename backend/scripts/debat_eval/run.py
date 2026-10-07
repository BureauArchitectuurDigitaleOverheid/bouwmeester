"""Run the marking of debates over gold files and report how it did.

    DATABASE_URL=postgresql+asyncpg://.../bouwmeester_eval DEV_NO_AUTH=1 \
    PYTHONPATH=scripts uv run python -m debat_eval.run <gold.json>... \
        --out <run.json> [--label baseline] [--provider claude_cli] \
        [--prompt-variant productie] [--compare <earlier-run.json>]

Writes the run (everything the model answered) to `--out` and prints the
report. See README.md for the providers and for what a run costs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import make_url

from bouwmeester.core.config import get_settings
from bouwmeester.services.llm.base import BaseLLMService

from . import gold as gold_file
from .harness import OracleLLM, run_debate
from .replay import VOICES_AT_ONCE, VOICES_NEVER, Clock, replay_debate
from .report import build_report, load_golds
from .timing import timing_report
from .variants import CHECKS, PROMPT_VARIANTS

PROVIDERS = ("claude_cli", "configured", "oracle")


async def provider_for(name: str, model: str | None, session) -> BaseLLMService | None:
    """The model to ask. ``None`` for the oracle, which is made per debate."""
    if name == "oracle":
        return None
    if name == "claude_cli":
        from bouwmeester.services.llm.claude_cli_service import (
            ClaudeCliLLMService,
            cli_available,
        )

        if not cli_available():
            raise SystemExit("The `claude` binary is not on the PATH.")
        return ClaudeCliLLMService(model=model or get_settings().LLM_MODEL)
    from bouwmeester.services.llm import get_llm_service

    llm = await get_llm_service(session)
    if llm is None:
        raise SystemExit("No LLM provider is configured for this environment.")
    return llm


async def run(args: argparse.Namespace) -> dict:
    # Imported here: it builds the engine from DATABASE_URL on import.
    from bouwmeester.core.database import async_session, engine

    golds = {path.stem: (path, gold_file.load(path)) for path in args.gold}
    transform = PROMPT_VARIANTS[args.prompt_variant]
    async with async_session() as session:
        shared = await provider_for(args.provider, args.model, session)
    model = getattr(shared, "_model", None) or ("oracle" if shared is None else "?")

    started = time.monotonic()
    meta = {
        "label": args.label,
        "provider": args.provider,
        "model": model,
        "prompt_variant": args.prompt_variant,
        "gestart": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    clock = None
    if args.replay:
        clock = Clock(
            subtitle_lag=args.subtitle_lag,
            voices=args.voices,
            meelezen=not args.no_running,
            **(
                {}
                if args.running_every is None
                else {"running_every": args.running_every}
            ),
        )
    blocks: dict[str, dict] = {}
    limit = asyncio.Semaphore(args.parallel)

    def save() -> dict:
        result = {
            "meta": {**meta, "seconden": round(time.monotonic() - started)},
            "debatten": [blocks[name] for name in golds if name in blocks],
        }
        args.out.write_text(
            json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        return result

    async def one(name: str, path: Path, gold: dict) -> None:
        total = len(gold["beurten"][: args.max_turns])

        def on_turn(turn: dict, result: dict) -> None:
            print(
                f"[{name}] {turn['nr']}/{total} {result['uitkomst']}"
                + (f" ({result['reden']})" if result["reden"] else "")
                + (
                    f": {len(result['gemarkeerd'])} gemarkeerd"
                    if result["gemarkeerd"]
                    else ""
                ),
                flush=True,
            )

        async with limit, async_session() as session:
            llm = shared if shared is not None else OracleLLM(gold)
            if clock is not None:
                block = await replay_debate(
                    session,
                    llm,
                    gold,
                    name,
                    clock,
                    transform=transform,
                    max_turns=args.max_turns,
                    on_turn=on_turn,
                )
            else:
                block = await run_debate(
                    session,
                    llm,
                    gold,
                    name,
                    transform=transform,
                    max_turns=args.max_turns,
                    on_turn=on_turn,
                )
        block["gold"] = str(path)
        blocks[name] = block
        save()

    try:
        await asyncio.gather(*(one(name, *pair) for name, pair in golds.items()))
    finally:
        await engine.dispose()
    return save()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("gold", type=Path, nargs="+", help="gold files to run over")
    parser.add_argument("--out", type=Path, required=True, help="where the run goes")
    parser.add_argument("--label", default="run")
    parser.add_argument("--provider", choices=PROVIDERS, default="claude_cli")
    parser.add_argument("--model", help="for claude_cli; default is LLM_MODEL")
    parser.add_argument(
        "--prompt-variant", choices=sorted(PROMPT_VARIANTS), default="productie"
    )
    parser.add_argument("--parallel", type=int, default=4, help="debates at a time")
    parser.add_argument("--max-turns", type=int, help="only the first turns")
    parser.add_argument("--compare", type=Path, help="an earlier run to compare with")
    parser.add_argument("--check", choices=sorted(CHECKS))
    parser.add_argument(
        "--replay",
        action="store_true",
        help="play each debate on a clock, in rounds as the worker makes them:"
        " also measures how long after it was said something is marked."
        " Needs gold files with the subtitle lines of every turn",
    )
    parser.add_argument(
        "--no-running",
        action="store_true",
        help="with --replay: read every turn when it is over, also an answer"
        " of the bewindspersoon",
    )
    parser.add_argument(
        "--subtitle-lag",
        type=float,
        default=Clock.subtitle_lag,
        help="with --replay: seconds between a line being said and being read",
    )
    parser.add_argument(
        "--running-every",
        type=float,
        help="with --replay: seconds an answer that goes on is left alone"
        " after a window of it was asked about; the worker's own when not given",
    )
    parser.add_argument(
        "--voices",
        choices=(VOICES_AT_ONCE, VOICES_NEVER),
        default=VOICES_AT_ONCE,
        help="with --replay: the voices decide about a line near a change of"
        " speaker as soon as they may, or never",
    )
    parser.add_argument(
        "--any-database",
        action="store_true",
        help="also run against a database whose name does not end in _eval",
    )
    args = parser.parse_args()

    database = make_url(get_settings().DATABASE_URL).database or ""
    if not database.endswith("_eval") and not args.any_database:
        print(
            f"Refusing to write to database {database!r}: its name does not end"
            " in _eval. Set DATABASE_URL, or pass --any-database.",
            file=sys.stderr,
        )
        return 2

    result = asyncio.run(run(args))
    compare = None
    if args.compare:
        earlier = json.loads(args.compare.read_text(encoding="utf-8"))
        compare = (earlier, load_golds(earlier))
    print()
    print(build_report(result, load_golds(result), compare=compare, check=args.check))
    if args.replay:
        print()
        print(timing_report(result, load_golds(result)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
