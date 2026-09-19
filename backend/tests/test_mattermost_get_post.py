"""Tests voor MattermostService.get_post en de LLM-foutafhandeling.

Twee onderscheidingen die de herverwerkings-wachtrij nodig heeft:

1. Een post die echt weg is (404 of soft-delete) mag definitief uit de
   wachtrij. Een time-out of 5xx niet — anders schrijft één Mattermost-hik
   een hele batch echte leads af als "verwijderd".
2. Een onbereikbare LLM is een storing (opnieuw proberen); een onbruikbaar
   LLM-antwoord is dat niet (opnieuw proberen levert hetzelfde op).
"""

from __future__ import annotations

import httpx
import pytest

from bouwmeester.services.llm.base import (
    BaseLLMService,
    DataSensitivity,
    ProviderCapabilities,
)
from bouwmeester.services.mattermost_service import (
    MattermostService,
    PostNotFoundError,
)


def _service_returning(monkeypatch, outcome):
    """MattermostService waarvan de HTTP-client ``outcome`` teruggeeft."""

    class FakeClient:
        async def get(self, url):
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    async def fake_get_client(self):
        return FakeClient()

    monkeypatch.setattr(MattermostService, "_get_client", fake_get_client)
    return MattermostService(None)


def _response(status: int, json_body: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status,
        json=json_body if json_body is not None else {},
        request=httpx.Request("GET", "http://mm.test/api/v4/posts/abc"),
    )


@pytest.mark.asyncio
class TestGetPost:
    async def test_404_is_definitief(self, monkeypatch):
        svc = _service_returning(monkeypatch, _response(404))
        with pytest.raises(PostNotFoundError):
            await svc.get_post("abc")

    async def test_soft_delete_is_definitief(self, monkeypatch):
        """Mattermost geeft een verwijderde post terug met 200 + delete_at."""
        svc = _service_returning(
            monkeypatch, _response(200, {"id": "abc", "delete_at": 1_700_000_000_000})
        )
        with pytest.raises(PostNotFoundError):
            await svc.get_post("abc")

    async def test_gewone_post_komt_door(self, monkeypatch):
        svc = _service_returning(
            monkeypatch, _response(200, {"id": "abc", "message": "hoi", "delete_at": 0})
        )
        post = await svc.get_post("abc")
        assert post is not None
        assert post["message"] == "hoi"

    async def test_timeout_is_tijdelijk(self, monkeypatch):
        """None, geen PostNotFoundError: volgende ronde opnieuw proberen."""
        svc = _service_returning(monkeypatch, httpx.ReadTimeout("te traag"))
        assert await svc.get_post("abc") is None

    async def test_500_is_tijdelijk(self, monkeypatch):
        svc = _service_returning(monkeypatch, _response(500))
        assert await svc.get_post("abc") is None

    async def test_429_is_tijdelijk(self, monkeypatch):
        svc = _service_returning(monkeypatch, _response(429))
        assert await svc.get_post("abc") is None


class _LLM(BaseLLMService):
    capabilities = ProviderCapabilities(allowed_data={DataSensitivity.CONFIDENTIAL})

    def __init__(self, antwoord=None, fout=None):
        self._antwoord = antwoord
        self._fout = fout

    async def _complete(self, prompt, max_tokens=1024):
        if self._fout is not None:
            raise self._fout
        return self._antwoord


@pytest.mark.asyncio
class TestClassificatieFoutafhandeling:
    async def _classify(self, llm):
        return await llm.classify_mattermost_lead_candidate(
            message="Hoofd wetgevingsbeleid wil capaciteit vrijmaken",
            initiatief_naam="RegelRecht",
            channel_display_name="leads",
            recent_leads=[],
        )

    async def test_onbereikbare_llm_is_een_storing(self):
        """failed=True, dus de post gaat de herverwerkings-wachtrij in."""
        result = await self._classify(_LLM(fout=httpx.ConnectError("geen verbinding")))
        assert result.is_lead is False
        assert result.failed is True

    async def test_onleesbaar_antwoord_is_geen_storing(self):
        """failed=False: opnieuw proberen levert hetzelfde onzin-antwoord op,
        dus die post moet niet elke ronde een LLM-call kosten."""
        result = await self._classify(_LLM(antwoord="dit is geen json"))
        assert result.is_lead is False
        assert result.failed is False

    async def test_afgekapt_antwoord_is_geen_storing(self):
        """De token-limiet kan JSON midden in een veld afkappen."""
        result = await self._classify(_LLM(antwoord='{"is_lead": true, "propos'))
        assert result.failed is False

    async def test_geldig_antwoord_werkt_gewoon(self):
        result = await self._classify(
            _LLM(
                antwoord=(
                    '{"is_lead": true, "confidence": 0.9, '
                    '"proposed_title": "JenV wetgevingsproces", '
                    '"proposed_description": "x", "reasoning": "y"}'
                )
            )
        )
        assert result.is_lead is True
        assert result.failed is False
        assert result.confidence == pytest.approx(0.9)
