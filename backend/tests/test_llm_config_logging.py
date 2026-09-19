"""Tests voor de diagnose-logging van de LLM-configuratie.

"De taalmodel-dienst is niet bereikbaar" en "er is geen taalmodel-dienst
ingesteld" zien er van buitenaf hetzelfde uit, maar vragen om een ander
antwoord: wachten versus een beheerder. Het eerste doet een netwerkcall die
faalt, het tweede doet er geen. De configuratie zit in de pod-omgeving en is
dus niet van buiten te inspecteren — vandaar dat dit in de log moet.
"""

from __future__ import annotations

import logging

import pytest

from bouwmeester.services.llm.factory import _log_llm_configuration

BASIS = {
    "claude_built": True,
    "claude_model": "claude-haiku-4-5",
    "vlam_built": False,
    "vlam_key": "",
    "vlam_url": "",
    "vlam_model": "",
    "platform_url": "",
    "manual_url": "",
    "preferred": "vlam",
}


def _log(caplog, **overrides) -> str:
    """Log één configuratie en geef de logtekst terug.

    Reset eerst de dedupe-guard: die onderdrukt een identieke tweede regel,
    wat tussen tests onbedoeld doorwerkt.
    """
    from bouwmeester.services.llm import factory as fmod

    fmod._last_logged_summary = None
    with caplog.at_level(logging.INFO, logger="bouwmeester.services.llm.factory"):
        _log_llm_configuration(**{**BASIS, **overrides})
    return caplog.text


class TestVlamActief:
    def test_noemt_adres_en_bron_platform(self, caplog):
        tekst = _log(
            caplog,
            vlam_built=True,
            vlam_key="geheim",
            vlam_url="http://proxy.svc:8081/v1",
            vlam_model="Kimi-K3",
            platform_url="http://proxy.svc:8081",
        )
        assert "http://proxy.svc:8081/v1" in tekst
        assert "platform (VLAM_API_URL)" in tekst
        assert "Kimi-K3" in tekst

    def test_noemt_bron_handmatig(self, caplog):
        tekst = _log(
            caplog,
            vlam_built=True,
            vlam_key="geheim",
            vlam_url="https://vlam-api.rijksweb.nl/v1",
            manual_url="https://vlam-api.rijksweb.nl/v1",
        )
        assert "handmatig (VLAM_BASE_URL)" in tekst

    def test_lekt_de_sleutel_niet(self, caplog):
        tekst = _log(
            caplog,
            vlam_built=True,
            vlam_key="supergeheim-token-42",
            vlam_url="http://proxy.svc:8081/v1",
            platform_url="http://proxy.svc:8081",
        )
        assert "supergeheim-token-42" not in tekst


class TestVlamOntbreekt:
    def test_benoemt_ontbrekende_sleutel(self, caplog):
        tekst = _log(
            caplog,
            vlam_key="",
            vlam_url="http://proxy.svc:8081/v1",
            platform_url="http://proxy.svc:8081",
        )
        assert "VLAM_API_KEY" in tekst

    def test_benoemt_dat_beide_urls_leeg_zijn(self, caplog):
        """Dit is het geval waarin de ZAD-dienst niets injecteert."""
        tekst = _log(caplog, vlam_key="geheim")
        assert "beide leeg" in tekst

    def test_toont_de_onbruikbare_url(self, caplog):
        """Een gezette maar onbruikbare URL moet zichtbaar zijn.

        Anders lijkt het op 'niets ingesteld' terwijl er wél iets staat.
        """
        tekst = _log(
            caplog,
            vlam_key="geheim",
            vlam_url="",
            manual_url="vlam-api.rijksweb.nl",  # geen scheme
        )
        assert "vlam-api.rijksweb.nl" in tekst
        assert "bruikbare URL" in tekst

    def test_waarschuwt_op_warning_niveau(self, caplog):
        """Geen INFO: dit is een toestand die aandacht vraagt."""
        from bouwmeester.services.llm import factory as fmod

        fmod._last_logged_summary = None
        with caplog.at_level(logging.INFO, logger="bouwmeester.services.llm.factory"):
            _log_llm_configuration(**{**BASIS, "vlam_key": "geheim"})
        niveaus = {r.levelno for r in caplog.records}
        assert logging.WARNING in niveaus


@pytest.mark.asyncio
async def test_ensure_services_logt_bij_opbouw(db_session, caplog):
    """De regel verschijnt echt bij het opbouwen, niet alleen in isolatie."""
    from bouwmeester.services.llm.factory import _ensure_services, clear_config_cache

    clear_config_cache()
    with caplog.at_level(logging.INFO, logger="bouwmeester.services.llm.factory"):
        await _ensure_services(db_session)
    clear_config_cache()
    assert "LLM-providers:" in caplog.text


@pytest.mark.asyncio
class TestConfigCacheTTL:
    """De worker is een ander proces dan de webserver.

    Een wijziging via Beheer > Instellingen leegt alleen de cache van de
    webserver. Zonder TTL bleef de worker — die de lead-classificatie doet —
    het oude model gebruiken tot een herstart, terwijl het beheerscherm de
    wijziging als opgeslagen toonde.
    """

    async def _set(self, db_session, key: str, value: str) -> None:
        from sqlalchemy.dialects.postgresql import insert

        from bouwmeester.models.app_config import AppConfig

        stmt = (
            insert(AppConfig)
            .values(key=key, value=value, is_secret=False)
            .on_conflict_do_update(index_elements=["key"], set_={"value": value})
        )
        await db_session.execute(stmt)
        await db_session.flush()

    async def test_gewijzigd_model_wordt_opgepikt_na_ttl(self, db_session, monkeypatch):
        """Zonder clear_config_cache: alleen de TTL doet het werk."""
        from bouwmeester.services.llm import factory as fmod

        fmod.clear_config_cache()
        await self._set(db_session, "VLAM_API_KEY", "sleutel")
        await self._set(db_session, "VLAM_API_URL", "http://proxy.test:8081")
        await self._set(db_session, "VLAM_MODEL_ID", "oud-model")

        await fmod._ensure_services(db_session)
        assert fmod._vlam_cache._model == "oud-model"

        # Beheerder past het model aan in een ANDER proces: deze cache
        # krijgt geen clear_config_cache() te zien.
        await self._set(db_session, "VLAM_MODEL_ID", "nieuw-model")
        await fmod._ensure_services(db_session)
        assert fmod._vlam_cache._model == "oud-model", "binnen de TTL blijft het oud"

        # TTL verlopen.
        monkeypatch.setattr(
            fmod, "_config_cache_ts", fmod._config_cache_ts - 999, raising=False
        )
        await fmod._ensure_services(db_session)
        assert fmod._vlam_cache._model == "nieuw-model"
        fmod.clear_config_cache()

    async def test_db_fout_wordt_niet_gecachet(self, db_session, monkeypatch):
        """Anders zit je een hele TTL vast aan een lege configuratie."""
        from bouwmeester.services.llm import factory as fmod

        fmod.clear_config_cache()

        async def kapot(*args, **kwargs):
            raise RuntimeError("db weg")

        monkeypatch.setattr(db_session, "execute", kapot)
        assert await fmod._load_config(db_session) == {}
        assert fmod._config_cache is None or fmod._config_cache_ts == 0.0
        fmod.clear_config_cache()


def test_dezelfde_configuratie_logt_niet_twee_keer(caplog):
    """De TTL laat _ensure_services elke minuut draaien; dat mag geen
    logregel per minuut opleveren."""
    from bouwmeester.services.llm import factory as fmod

    fmod._last_logged_summary = None
    actief = {
        **BASIS,
        "vlam_built": True,
        "vlam_key": "geheim",
        "vlam_url": "http://proxy.test:8081/v1",
        "platform_url": "http://proxy.test:8081",
    }
    with caplog.at_level(logging.INFO, logger="bouwmeester.services.llm.factory"):
        _log_llm_configuration(**actief)
        eerste = len(caplog.records)
        _log_llm_configuration(**actief)
        tweede = len(caplog.records)
    assert eerste > 0
    assert tweede == eerste, "tweede identieke aanroep hoort stil te zijn"

    # Een echte wijziging logt wél weer.
    with caplog.at_level(logging.INFO, logger="bouwmeester.services.llm.factory"):
        _log_llm_configuration(**{**actief, "vlam_model": "ander-model"})
    assert len(caplog.records) > tweede
    fmod._last_logged_summary = None
