"""Tests voor het bepalen van het VLAM-basisadres.

De OpenAI-client plakt zelf ``/chat/completions`` achter de ``base_url``, dus
daar moet precies één ``/v1`` in staan. De ZAD-dienst levert het adres zonder
pad, een handmatige instelling historisch mét pad. Eén ``/v1`` te veel of te
weinig geeft een 404 die in de logs niet te onderscheiden is van een storing.
"""

from __future__ import annotations

import pytest

from bouwmeester.services.llm.vlam_endpoint import (
    normalize_vlam_base_url,
    resolve_vlam_base_url,
)

# Wat de ZAD-dienst injecteert: basisadres zonder pad. Vorm uit
# opi/services/catalog/vlam/endpoint.py in rig-cluster.
PLATFORM_URL = (
    "http://productie-vlam-proxy-intern.rig-prd-vlam-wt8.svc.cluster.local:8081"
)


class TestNormalize:
    def test_platform_adres_krijgt_v1(self):
        assert normalize_vlam_base_url(PLATFORM_URL) == f"{PLATFORM_URL}/v1"

    def test_bestaande_v1_wordt_niet_verdubbeld(self):
        assert (
            normalize_vlam_base_url("https://vlam-api.rijksweb.nl/v1")
            == "https://vlam-api.rijksweb.nl/v1"
        )

    def test_trailing_slash_verdwijnt(self):
        assert (
            normalize_vlam_base_url("https://vlam-api.rijksweb.nl/v1/")
            == "https://vlam-api.rijksweb.nl/v1"
        )

    def test_langer_pad_blijft_behouden(self):
        """De oude demo-URL had een projectpad vóór de /v1."""
        raw = "https://api.demo.vlam.ai/v2.1/projects/poc/openai-compatible/v1"
        assert normalize_vlam_base_url(raw) == raw

    def test_langer_pad_zonder_v1_krijgt_v1(self):
        raw = "https://api.demo.vlam.ai/v2.1/projects/poc/openai-compatible"
        assert normalize_vlam_base_url(raw) == f"{raw}/v1"

    def test_hoofdletter_v1_wordt_niet_verdubbeld(self):
        """``/V1`` is hetzelfde pad als ``/v1``.

        Zou het hoofdlettergevoelig zijn, dan werd het ``/V1/v1`` en dat is
        een 404 die er in de logs uitziet als een storing.
        """
        assert (
            normalize_vlam_base_url("https://vlam-api.rijksweb.nl/V1")
            == "https://vlam-api.rijksweb.nl/V1"
        )

    def test_v1_als_deel_van_langer_segment_telt_niet(self):
        """``/apiv1`` en ``/v10`` zijn echt andere paden."""
        assert normalize_vlam_base_url("https://h/apiv1") == "https://h/apiv1/v1"
        assert normalize_vlam_base_url("https://h/v10") == "https://h/v10/v1"

    def test_query_en_fragment_verdwijnen(self):
        """Een base_url draagt geen query of fragment; de client plakt er
        zelf een pad achter, dus die zouden middenin de URL belanden."""
        assert normalize_vlam_base_url("https://h/v1?x=1#f") == "https://h/v1"

    def test_spaties_eromheen_storen_niet(self):
        assert normalize_vlam_base_url(f"  {PLATFORM_URL}  ") == f"{PLATFORM_URL}/v1"

    @pytest.mark.parametrize("raw", ["", "   ", None])
    def test_leeg_blijft_leeg(self, raw):
        assert normalize_vlam_base_url(raw) == ""

    @pytest.mark.parametrize(
        "raw",
        [
            "vlam-api.rijksweb.nl",  # geen scheme
            "/v1",  # alleen een pad
            "not a url",
        ],
    )
    def test_onbruikbaar_adres_geeft_leeg(self, raw):
        """Liever leeg dan een half adres: de caller leest leeg als
        'niet geconfigureerd' en bouwt dan geen kapotte client."""
        assert normalize_vlam_base_url(raw) == ""


class TestResolve:
    def test_platform_wint_van_handmatig(self):
        """De handmatige waarde kan verouderd zijn.

        Dat is precies wat er gebeurde toen de demo-omgeving verdween: de
        ingestelde URL bleef naar een dode host wijzen.
        """
        resolved = resolve_vlam_base_url(
            PLATFORM_URL, "https://api.demo.vlam.ai/v2.1/projects/poc/x/v1"
        )
        assert resolved == f"{PLATFORM_URL}/v1"

    def test_handmatig_als_platform_ontbreekt(self):
        """Lokaal draaien zonder ZAD-dienst blijft werken."""
        manual = "https://vlam-api.rijksweb.nl/v1"
        assert resolve_vlam_base_url("", manual) == manual

    def test_onbruikbaar_platform_adres_valt_terug(self):
        """Een lege of kapotte platform-waarde mag de handmatige niet blokkeren."""
        manual = "https://vlam-api.rijksweb.nl/v1"
        assert resolve_vlam_base_url("not a url", manual) == manual

    def test_geen_van_beide_geeft_leeg(self):
        assert resolve_vlam_base_url("", "") == ""
