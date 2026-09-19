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
