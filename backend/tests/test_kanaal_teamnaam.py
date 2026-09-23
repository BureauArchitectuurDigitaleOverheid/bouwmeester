"""Tests voor de teamnaam bij een Mattermost-kanaal.

Twee kanalen in verschillende teams mogen dezelfde naam dragen. De picker
toonde dan twee identieke regels met een koppel-knop, en kiezen was
gokken.

De naam wordt bij het tonen opgehaald en niet opgeslagen: een opgeslagen
naam veroudert zodra iemand het team in Mattermost hernoemt. Dat maakt de
foutpaden belangrijk, want ze draaien bij elke weergave.
"""

from types import SimpleNamespace

import httpx
import pytest

from bouwmeester.services.mattermost_service import MattermostService


def _svc() -> MattermostService:
    return MattermostService.__new__(MattermostService)


class _Client:
    """Minimale httpx-vervanger die vaste antwoorden teruggeeft."""

    def __init__(self, antwoorden: dict):
        self._antwoorden = antwoorden

    async def get(self, url: str, **_kw):
        for pad, waarde in self._antwoorden.items():
            if pad in url:
                if isinstance(waarde, Exception):
                    raise waarde
                return SimpleNamespace(
                    json=lambda w=waarde: w,
                    raise_for_status=lambda: None,
                )
        raise AssertionError(f"onverwachte url: {url}")


class TestTeamNamen:
    async def test_leest_display_name(self):
        svc = _svc()
        svc._get_client = lambda: _klaar(
            _Client({"users/me/teams": [{"id": "t1", "display_name": "MOZa"}]})
        )
        assert await svc.team_namen() == {"t1": "MOZa"}

    async def test_valt_terug_op_de_slug(self):
        """Zonder display_name is de url-naam beter dan niets."""
        svc = _svc()
        svc._get_client = lambda: _klaar(
            _Client({"users/me/teams": [{"id": "t1", "name": "moza"}]})
        )
        assert await svc.team_namen() == {"t1": "moza"}

    async def test_mattermost_plat_geeft_lege_map(self):
        """Zonder namen is de lijst hetzelfde als voorheen, geen fout."""
        svc = _svc()
        svc._get_client = lambda: _klaar(
            _Client({"users/me/teams": httpx.ConnectError("plat")})
        )
        assert await svc.team_namen() == {}

    async def test_team_zonder_id_wordt_overgeslagen(self):
        svc = _svc()
        svc._get_client = lambda: _klaar(
            _Client({"users/me/teams": [{"display_name": "Zonder id"}]})
        )
        assert await svc.team_namen() == {}


class TestTeamIdPerKanaal:
    """Koppelingen van vóór deze wijziging dragen geen team_id.

    Zonder deze lookup valt er voor die koppelingen niets op te zoeken, en
    zou een migratie nodig zijn die alleen repareert wat er op dat moment
    staat.
    """

    async def test_koppelt_kanaal_aan_team(self):
        svc = _svc()
        svc.get_bot_user_id = _maak_async("bot1")
        svc._get_client = lambda: _klaar(
            _Client({"channels": [{"id": "c1", "team_id": "t1"}]})
        )
        assert await svc.team_id_per_kanaal() == {"c1": "t1"}

    async def test_zonder_bot_geen_lookup(self):
        svc = _svc()
        svc.get_bot_user_id = _maak_async(None)
        assert await svc.team_id_per_kanaal() == {}

    async def test_kanaal_zonder_team_id_valt_af(self):
        svc = _svc()
        svc.get_bot_user_id = _maak_async("bot1")
        svc._get_client = lambda: _klaar(_Client({"channels": [{"id": "c1"}]}))
        assert await svc.team_id_per_kanaal() == {}

    async def test_fout_geeft_lege_map(self):
        svc = _svc()
        svc.get_bot_user_id = _maak_async("bot1")
        svc._get_client = lambda: _klaar(
            _Client({"channels": httpx.ConnectError("plat")})
        )
        assert await svc.team_id_per_kanaal() == {}


def _maak_async(waarde):
    async def f():
        return waarde

    return f


async def _klaar(waarde):
    return waarde


@pytest.fixture
def anyio_backend():
    return "asyncio"
