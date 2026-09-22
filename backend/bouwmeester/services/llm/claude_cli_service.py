"""Claude via de Claude Code CLI op een abonnementstoken — capabilities: PUBLIC only.

Waarom naast `ClaudeLLMService`, die dezelfde modellen aanspreekt: de
Anthropic SDK rekent per token af op een `sk-ant-`-sleutel, deze provider
draait op een abonnement via `CLAUDE_CODE_OAUTH_TOKEN` (eenmalig verkregen
met `claude setup-token`). Dat token werkt uitsluitend via de CLI-binary;
de SDK accepteert het niet. Vandaar een subproces in plaats van een
HTTP-client.

Wat dat betekent voor wie dit beheert:

- De binary moet in de image zitten. Zonder `claude` op het PATH bouwt de
  factory deze provider niet, en valt alles terug op de andere providers.
- Het token is persoonlijk. Wie het heeft, kan het abonnement laten werken.
  Het hoort dus in de secretstore, niet in de repo, en de omgeving van het
  subproces is een whitelist: de worker draagt meer secrets dan de CLI mag
  zien.
- Eén call is één proces. Dat is trager dan een HTTP-call en kost een
  eigen werkmap.

De CLI leest `CLAUDE.md` en `.claude/` uit zijn werkmap, dus die werkmap is
bewust leeg: vanuit de repo zou elke call de hele projectcontext
meesturen.
"""

import asyncio
import json
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path

from bouwmeester.services.llm.base import (
    BaseLLMService,
    DataSensitivity,
    ProviderCapabilities,
)

logger = logging.getLogger(__name__)

CLAUDE_BIN = "claude"

# De CLI krijgt alleen wat hij nodig heeft. Het workerproces draagt
# database-URL's, de Mattermost-bottoken en VLAM-sleutels; die horen niet in
# de omgeving van een subproces dat tekst samenvat.
ENV_WHITELIST = (
    "PATH",
    "HOME",
    "TMPDIR",
    "TZ",
    "LANG",
    "LC_ALL",
    "USER",
    "SHELL",
    "TERM",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "DISABLE_AUTOUPDATER",
    "CLAUDE_CODE_SKIP_PROMPT_HISTORY",
)

DEFAULT_TIMEOUT_SECONDS = 120

# Een kapotte login is structureel: elke volgende call faalt ook, dus die
# hoort luid te falen in plaats van als lege samenvatting door te sijpelen.
_LOGIN_MARKERS = (
    "not logged in",
    "please run /login",
    "invalid api key",
    "oauth token",
    "unauthorized",
    "401",
)


class ClaudeCliUnavailableError(RuntimeError):
    """De CLI kan structureel niet werken (binary weg, login stuk)."""


def cli_available() -> bool:
    """Staat de `claude`-binary op het PATH?"""
    return shutil.which(CLAUDE_BIN) is not None


class ClaudeCliLLMService(BaseLLMService):
    """Claude Code CLI op een abonnementstoken.

    Alleen publieke data: kamerstukken, tagnamen. Dezelfde klasse als
    `ClaudeLLMService`, want het is hetzelfde model bij dezelfde partij —
    alleen de betaalroute verschilt.
    """

    capabilities = ProviderCapabilities(
        allowed_data={DataSensitivity.PUBLIC},
    )

    def __init__(
        self,
        model: str,
        oauth_token: str | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._model = model
        self._oauth_token = oauth_token
        self._timeout = timeout_seconds
        # Lege werkmap, zodat de CLI geen projectcontext meestuurt.
        self._cwd = Path(tempfile.gettempdir()) / "bouwmeester-claude-cli"

    def _env(self) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if k in ENV_WHITELIST}
        if self._oauth_token:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = self._oauth_token
        env.setdefault("DISABLE_AUTOUPDATER", "1")
        env.setdefault("CLAUDE_CODE_SKIP_PROMPT_HISTORY", "true")
        return env

    async def _complete(self, prompt: str, max_tokens: int = 1024) -> str:
        """Eén `claude -p`-call.

        `max_tokens` wordt genegeerd: de CLI kent die vlag niet. De prompts
        vragen zelf om een begrensd antwoord (een samenvatting van hooguit
        drie zinnen), dus dat is hier geen verlies.
        """
        self._cwd.mkdir(parents=True, exist_ok=True)
        args = [
            "-p",
            "--model",
            self._model,
            "--output-format",
            "json",
            "--no-session-persistence",
            # Geen tools: dit is tekst in, tekst uit. Zonder deze vlag kan
            # de CLI het bestandssysteem en het web aanraken.
            "--tools",
            "",
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                CLAUDE_BIN,
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._cwd),
                env=self._env(),
            )
        except FileNotFoundError as exc:
            raise ClaudeCliUnavailableError(
                f"`{CLAUDE_BIN}`-binary ontbreekt in deze image"
            ) from exc

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(prompt.encode()), timeout=self._timeout
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError(
                f"`{CLAUDE_BIN} -p` overschreed {self._timeout}s"
            ) from None

        stderr_tail = stderr.decode(errors="replace").strip()[-300:]
        raw = _parse_envelope(stdout.decode(errors="replace"))

        if proc.returncode != 0 or (raw or {}).get("is_error"):
            melding = str((raw or {}).get("result") or stderr_tail)[:300]
            if any(m in melding.lower() for m in _LOGIN_MARKERS):
                # Luid falen: een verlopen abonnementstoken is niet iets wat
                # vanzelf overgaat, en stil doorgaan zou elke samenvatting
                # leeg maken zonder dat iemand weet waarom.
                raise ClaudeCliUnavailableError(f"CLI-login stuk: {melding}")
            raise RuntimeError(f"`{CLAUDE_BIN} -p` faalde: {melding}")

        if raw is None:
            raise RuntimeError(f"`{CLAUDE_BIN} -p` gaf geen leesbare JSON-envelop")

        kosten = raw.get("total_cost_usd")
        if kosten:
            logger.debug(
                "claude-cli call: $%.4f, %s turns", kosten, raw.get("num_turns")
            )

        return str(raw.get("result") or "")


def _parse_envelope(stdout: str) -> dict | None:
    """Lees de `--output-format json`-envelop.

    Die draagt `result`, `is_error`, `num_turns`, `total_cost_usd` en
    `usage`. Een update van de CLI die er tekst omheen zet mag niet meteen
    alles breken, vandaar de tolerante tweede poging.
    """
    stdout = stdout.strip()
    if not stdout:
        return None
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        start, end = stdout.find("{"), stdout.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            parsed = json.loads(stdout[start : end + 1])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def strip_code_fences(text: str) -> str:
    """Haal ```json-fences weg.

    `BaseLLMService._parse_json` doet dit ook, maar de CLI voegt vaker een
    fence toe dan de SDK, dus het is hier geen overbodige tweede poging.
    """
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    return text
