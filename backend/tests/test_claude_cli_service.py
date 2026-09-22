"""Tests voor de Claude Code CLI als LLM-provider.

Deze provider draait op een abonnementstoken in plaats van een
API-sleutel. Dat token werkt alleen via de CLI-binary, dus dit is een
subproces en geen HTTP-client — met de risico's die daarbij horen: een
omgeving die te veel meegeeft, een binary die ontbreekt, en een login die
stilletjes stuk is.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from bouwmeester.services.llm.claude_cli_service import (
    ENV_WHITELIST,
    ClaudeCliLLMService,
    ClaudeCliUnavailableError,
    _parse_envelope,
    strip_code_fences,
)


class TestEnvWhitelist:
    """De CLI krijgt alleen wat hij nodig heeft."""

    def test_secrets_of_the_worker_do_not_leak(self, monkeypatch):
        # Het workerproces draagt deze; een samenvattings-subproces niet.
        monkeypatch.setenv("DATABASE_URL", "postgresql://geheim")
        monkeypatch.setenv("MATTERMOST_BOT_TOKEN", "xoxb-geheim")
        monkeypatch.setenv("VLAM_API_KEY", "geheim")
        monkeypatch.setenv("PATH", "/usr/bin")

        env = ClaudeCliLLMService(model="m")._env()

        assert "DATABASE_URL" not in env
        assert "MATTERMOST_BOT_TOKEN" not in env
        assert "VLAM_API_KEY" not in env
        assert env["PATH"] == "/usr/bin"

    def test_token_is_passed_through(self):
        env = ClaudeCliLLMService(model="m", oauth_token="sk-test")._env()
        assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "sk-test"

    def test_autoupdater_off(self):
        # Een CLI die zichzelf bijwerkt in een draaiende container is een
        # verrassing die je niet wilt.
        env = ClaudeCliLLMService(model="m")._env()
        assert env["DISABLE_AUTOUPDATER"] == "1"

    def test_whitelist_has_no_secret_looking_names(self):
        verdacht = [
            k
            for k in ENV_WHITELIST
            if any(w in k for w in ("PASS", "SECRET", "DATABASE", "WEBHOOK"))
        ]
        assert verdacht == []


class TestEnvelope:
    def test_parses_plain_json(self):
        raw = _parse_envelope('{"result": "hoi", "is_error": false}')
        assert raw["result"] == "hoi"

    def test_tolerates_surrounding_noise(self):
        # Een CLI-update die een regel logt mag niet meteen alles breken.
        raw = _parse_envelope('waarschuwing\n{"result": "hoi"}\n')
        assert raw["result"] == "hoi"

    def test_empty_is_none(self):
        assert _parse_envelope("") is None

    def test_garbage_is_none(self):
        assert _parse_envelope("helemaal geen json") is None

    def test_non_dict_is_none(self):
        assert _parse_envelope("[1, 2, 3]") is None


class TestCodeFences:
    def test_strips_json_fence(self):
        assert strip_code_fences('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_leaves_plain_text(self):
        assert strip_code_fences('{"a": 1}') == '{"a": 1}'


def _proc(stdout: str, returncode: int = 0, stderr: str = ""):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), stderr.encode()))
    proc.returncode = returncode
    return proc


class TestComplete:
    @pytest.mark.asyncio
    async def test_returns_result_field(self):
        envelop = json.dumps({"result": "de samenvatting", "is_error": False})
        with patch("asyncio.create_subprocess_exec", return_value=_proc(envelop)):
            svc = ClaudeCliLLMService(model="m")
            assert await svc._complete("prompt") == "de samenvatting"

    @pytest.mark.asyncio
    async def test_missing_binary_is_unavailable_not_crash(self):
        """Zonder binary een duidelijke fout, geen FileNotFoundError."""
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            svc = ClaudeCliLLMService(model="m")
            with pytest.raises(ClaudeCliUnavailableError, match="ontbreekt"):
                await svc._complete("prompt")

    @pytest.mark.asyncio
    async def test_broken_login_fails_loudly(self):
        """Een verlopen abonnementstoken gaat niet vanzelf over.

        Stil doorgaan zou elke samenvatting leeg maken zonder dat iemand
        weet waarom, dus dit hoort een eigen fout te zijn.
        """
        envelop = json.dumps({"result": "Invalid API key", "is_error": True})
        with patch("asyncio.create_subprocess_exec", return_value=_proc(envelop, 1)):
            svc = ClaudeCliLLMService(model="m")
            with pytest.raises(ClaudeCliUnavailableError, match="login"):
                await svc._complete("prompt")

    @pytest.mark.asyncio
    async def test_other_error_is_ordinary_runtime_error(self):
        # Niet elke fout is fataal: een overbelaste dienst mag de volgende
        # ronde gewoon opnieuw geprobeerd worden.
        envelop = json.dumps({"result": "overloaded", "is_error": True})
        with patch("asyncio.create_subprocess_exec", return_value=_proc(envelop, 1)):
            svc = ClaudeCliLLMService(model="m")
            with pytest.raises(RuntimeError) as exc:
                await svc._complete("prompt")
            assert not isinstance(exc.value, ClaudeCliUnavailableError)

    @pytest.mark.asyncio
    async def test_unparseable_output_raises(self):
        with patch("asyncio.create_subprocess_exec", return_value=_proc("rommel")):
            svc = ClaudeCliLLMService(model="m")
            with pytest.raises(RuntimeError, match="JSON-envelop"):
                await svc._complete("prompt")

    @pytest.mark.asyncio
    async def test_runs_in_an_empty_working_directory(self):
        """De CLI leest CLAUDE.md uit zijn cwd; dat mag de repo niet zijn."""
        envelop = json.dumps({"result": "ok"})
        with patch(
            "asyncio.create_subprocess_exec", return_value=_proc(envelop)
        ) as spawn:
            svc = ClaudeCliLLMService(model="m")
            await svc._complete("prompt")
            cwd = spawn.call_args.kwargs["cwd"]
            assert "bouwmeester-claude-cli" in cwd
            assert not cwd.endswith("/bouwmeester")

    @pytest.mark.asyncio
    async def test_no_tools(self):
        """Tekst in, tekst uit: geen bestandssysteem, geen web."""
        envelop = json.dumps({"result": "ok"})
        with patch(
            "asyncio.create_subprocess_exec", return_value=_proc(envelop)
        ) as spawn:
            await ClaudeCliLLMService(model="m")._complete("prompt")
            args = spawn.call_args.args
            assert "--tools" in args
            assert args[args.index("--tools") + 1] == ""


class TestCapabilities:
    def test_public_data_only(self):
        from bouwmeester.services.llm.base import DataSensitivity

        caps = ClaudeCliLLMService.capabilities
        assert caps.supports(DataSensitivity.PUBLIC)
        assert not caps.supports(DataSensitivity.CONFIDENTIAL)
