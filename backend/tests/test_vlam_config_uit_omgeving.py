"""VLAM-sleutel, model en base-URL komen alleen uit de omgeving.

Twee plekken om dezelfde instelling te zetten was de oorzaak van een
storing: ``_load_config`` leest AppConfig vóór de omgeving, dus een maanden
oude ``VLAM_MODEL_ID`` in de database overrulede stil wat er in ZAD stond.
De logs toonden een fout met het oude model terwijl het beheerscherm de
nieuwe waarde liet zien, en niets verbond die twee.

``VLAM_API_URL`` blijft wél instelbaar: dat is de noodrem voor een verkeerd
platformadres.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from bouwmeester.api.routes.admin import _DEFAULT_CONFIG, _ensure_default_config
from bouwmeester.models.app_config import AppConfig

VERWIJDERD = ("VLAM_API_KEY", "VLAM_BASE_URL", "VLAM_MODEL_ID")


def _default_keys() -> set[str]:
    return {entry["key"] for entry in _DEFAULT_CONFIG}


class TestBeheerschermBiedtZeNietAan:
    @pytest.mark.parametrize("key", VERWIJDERD)
    def test_staat_niet_in_de_defaults(self, key):
        assert key not in _default_keys()

    def test_api_url_blijft_wel_beschikbaar(self):
        """De noodrem voor een verkeerd platformadres moet blijven."""
        assert "VLAM_API_URL" in _default_keys()

    def test_andere_providers_zijn_niet_geraakt(self):
        """Deze opruiming gaat alleen over VLAM."""
        keys = _default_keys()
        assert "ANTHROPIC_API_KEY" in keys
        assert "LLM_PROVIDER" in keys


@pytest.mark.asyncio
async def test_seeding_maakt_ze_niet_opnieuw_aan(db_session):
    """De migratie ruimt ze op; seeding mag ze niet terugzetten.

    Anders zouden ze onzichtbaar terugkomen en alsnog voorgaan op de
    omgeving — erger dan de situatie die we oplossen, want dan is de
    waarde niet meer via de UI te zien of te wijzigen.
    """
    from bouwmeester.api.routes import admin as admin_mod

    admin_mod._defaults_seeded = False
    await _ensure_default_config(db_session)
    admin_mod._defaults_seeded = False

    rijen = (
        (
            await db_session.execute(
                select(AppConfig.key).where(AppConfig.key.in_(VERWIJDERD))
            )
        )
        .scalars()
        .all()
    )
    assert list(rijen) == []


@pytest.mark.asyncio
async def test_factory_gebruikt_de_omgeving(db_session, monkeypatch):
    """Zonder AppConfig-rijen bouwt de factory op de env-waarden."""
    from bouwmeester.core.config import get_settings
    from bouwmeester.services.llm import factory as fmod

    settings = get_settings()
    monkeypatch.setattr(settings, "VLAM_API_KEY", "sleutel-uit-zad", raising=False)
    monkeypatch.setattr(settings, "VLAM_MODEL_ID", "Kimi-K3-prepaid", raising=False)
    monkeypatch.setattr(
        settings, "VLAM_API_URL", "http://proxy.test:8081", raising=False
    )
    monkeypatch.setattr(settings, "VLAM_BASE_URL", "", raising=False)

    fmod.clear_config_cache()
    await fmod._ensure_services(db_session)
    assert fmod._vlam_cache is not None
    assert fmod._vlam_cache._model == "Kimi-K3-prepaid"
    assert str(fmod._vlam_cache._client.base_url).rstrip("/") == (
        "http://proxy.test:8081/v1"
    )
    fmod.clear_config_cache()
