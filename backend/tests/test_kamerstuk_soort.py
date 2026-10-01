"""Tests voor de soort-herkenning van kamerstukken.

Waarom dit ertoe doet: zonder het soort heet elk alert "Kamerstuk", en dan
ziet een agenda van een vergadering die over twee dagen is er hetzelfde uit
als een besluitenlijst van een vergadering die geweest is. Het eerste is
een kans om nog iets te doen, het tweede een vaststelling.

De soorten in deze tests zijn gemeten tegen de echte TK-API op 22 september
2026; de documentnummers zijn publieke kamerstukken.
"""

from datetime import date, timedelta

import httpx
import pytest

from bouwmeester.services.kamerstuk_soort import (
    CAT_BIJLAGE,
    CAT_BRIEF,
    CAT_DEBAT,
    CAT_EXTERN,
    CAT_OVERIG,
    CAT_VERGADERING_TERUG,
    CAT_VERGADERING_VOORUIT,
    CAT_VRAAG,
    CAT_WETGEVING,
    KamerstukContext,
    categorie_van,
    haal_context,
)


class TestCategorieVan:
    @pytest.mark.parametrize(
        ("soort", "verwacht"),
        [
            ("Schriftelijke vragen", CAT_VRAAG),
            ("Antwoord schriftelijke vragen", CAT_VRAAG),
            ("Lijst van vragen", CAT_VRAAG),
            ("Agenda procedurevergadering", CAT_VERGADERING_VOORUIT),
            ("Besluitenlijst procedurevergadering", CAT_VERGADERING_TERUG),
            ("Bijlage", CAT_BIJLAGE),
            ("Brief regering", CAT_BRIEF),
            ("Position paper", CAT_EXTERN),
            ("Memorie van toelichting", CAT_WETGEVING),
        ],
    )
    def test_bekende_soorten(self, soort, verwacht):
        assert categorie_van(soort) == verwacht

    @pytest.mark.parametrize(
        ("soort", "verwacht"),
        [
            # Woordelijke verslagen, apart van de besluitenlijst: hier
            # staat wat er gezegd is, niet wat er besloten is.
            ("Stenogram", CAT_DEBAT),
            ("Verslag van een commissiedebat", CAT_DEBAT),
            ("Verslag van een algemeen overleg", CAT_DEBAT),
            ("Verslag van een wetgevingsoverleg", CAT_DEBAT),
            ("Mondelinge vragen", CAT_DEBAT),
            # Vooraf: hier is nog iets mee te doen.
            ("Convocatie commissieactiviteit", CAT_VERGADERING_VOORUIT),
            ("Convocatie inbreng", CAT_VERGADERING_VOORUIT),
            ("Agenda plenaire vergadering", CAT_VERGADERING_VOORUIT),
            ("Brief commissie aan bewindspersoon", CAT_BRIEF),
            ("Advies Afdeling advisering Raad van State", CAT_EXTERN),
            ("Rapport Algemene Rekenkamer", CAT_EXTERN),
            ("Motie (gewijzigd/nader)", CAT_WETGEVING),
            ("Nota van wijziging", CAT_WETGEVING),
        ],
    )
    def test_soorten_die_eerst_overig_waren(self, soort, verwacht):
        """Gemeten tegen de API op 1 oktober 2026.

        Deze stukken kwamen altijd al binnen (een onbekend soort valt in
        `overig` en wordt gewoon gepost), maar zonder label en zonder
        gerichte instructie aan het model. Stenogram en convocatie zijn met
        samen ruim 57.000 stukken de twee grootste soorten die we nog niet
        benoemden.
        """
        assert categorie_van(soort) == verwacht

    def test_elke_categorie_heeft_een_eigen_instructie(self):
        """Anders valt een nieuwe categorie stil terug op de generieke.

        De instructie stuurt de samenvatting én de relevantiescore, en de
        score beslist via de drempel of er een bericht komt. Een categorie
        zonder eigen tekst krijgt "het soort van dit stuk is niet
        vastgesteld" en daarmee precies de duiding die we net hebben
        toegevoegd weer kwijt.
        """
        from bouwmeester.services.kamerstuk_soort import CATEGORIE_PRESENTATIE
        from bouwmeester.services.llm.prompts import _CATEGORIE_CONTEXT

        zonder = sorted(set(CATEGORIE_PRESENTATIE) - set(_CATEGORIE_CONTEXT))
        assert zonder == [], f"categorieën zonder instructie: {zonder}"

    def test_een_debatverslag_is_geen_besluitenlijst(self):
        """Het verschil waar deze categorie voor bestaat.

        Een besluitenlijst zegt wat er is besloten; een verslag zegt wat
        er is gezegd, door wie. Dat vraagt een andere samenvatting, en
        daarom krijgt het model er een andere instructie bij.
        """
        assert categorie_van("Besluitenlijst procedurevergadering") == (
            CAT_VERGADERING_TERUG
        )
        assert categorie_van("Verslag van een commissiedebat") == CAT_DEBAT

    def test_herziene_agenda_valt_terug_op_de_kern(self):
        # Commissies formuleren dit per gelegenheid net anders.
        assert (
            categorie_van("Tweede herziene agenda procedurevergadering")
            == CAT_VERGADERING_VOORUIT
        )

    def test_onbekend_soort_wordt_overig_niet_weggegooid(self):
        # Een breed vangnet mag een stuk niet verzwijgen omdat we het label
        # niet kennen; de TK-API krijgt er soorten bij.
        assert categorie_van("Iets wat in 2030 wordt bedacht") == CAT_OVERIG

    def test_geen_soort(self):
        assert categorie_van(None) == CAT_OVERIG


class TestPresentatie:
    def test_elke_categorie_heeft_een_vorm(self):
        for cat in (
            CAT_VRAAG,
            CAT_VERGADERING_VOORUIT,
            CAT_VERGADERING_TERUG,
            CAT_BIJLAGE,
            CAT_BRIEF,
            CAT_EXTERN,
            CAT_WETGEVING,
            CAT_OVERIG,
        ):
            p = KamerstukContext(categorie=cat).presentatie
            assert p["emoji"] and p["label"] and p["kleur"].startswith("#")

    def test_soorten_krijgen_verschillende_kleuren(self):
        vraag = KamerstukContext(categorie=CAT_VRAAG).presentatie
        agenda = KamerstukContext(categorie=CAT_VERGADERING_VOORUIT).presentatie
        assert vraag["kleur"] != agenda["kleur"]


class TestDagenTotVergadering:
    def test_vooruit(self):
        ctx = KamerstukContext(activiteit_datum=date(2026, 9, 24))
        assert ctx.dagen_tot_vergadering(date(2026, 9, 22)) == 2

    def test_geweest(self):
        ctx = KamerstukContext(activiteit_datum=date(2026, 9, 20))
        assert ctx.dagen_tot_vergadering(date(2026, 9, 22)) == -2

    def test_zonder_datum(self):
        assert KamerstukContext().dagen_tot_vergadering() is None


def _api(payload: dict):
    """httpx-client die één vaste TK-API-respons teruggeeft."""

    def handler(request):
        return httpx.Response(200, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestHaalContext:
    @pytest.mark.asyncio
    async def test_kamervraag_met_termijn(self):
        async with _api(
            {
                "value": [
                    {
                        "DocumentNummer": "2026D44063",
                        "Soort": "Schriftelijke vragen",
                        "Zaak": [
                            {
                                "Nummer": "2026Z19034",
                                "Termijn": "2026-10-15T00:00:00Z",
                                "Afgedaan": False,
                            }
                        ],
                    }
                ]
            }
        ) as c:
            ctx = await haal_context("2026D44063", c)

        assert ctx.categorie == CAT_VRAAG
        assert ctx.termijn == date(2026, 10, 15)
        assert ctx.afgedaan is False
        assert ctx.zaak_nummer == "2026Z19034"

    @pytest.mark.asyncio
    async def test_bijlage_weet_waar_hij_bij_hoort(self):
        async with _api(
            {
                "value": [
                    {
                        "DocumentNummer": "2026D45065",
                        "Soort": "Bijlage",
                        "BronDocument": [
                            {
                                "DocumentNummer": "2026D45064",
                                "Onderwerp": "Strategische inzet digitalisering",
                            }
                        ],
                    }
                ]
            }
        ) as c:
            ctx = await haal_context("2026D45065", c)

        assert ctx.categorie == CAT_BIJLAGE
        assert ctx.bijlage_bij_nummer == "2026D45064"
        assert "Strategische inzet" in ctx.bijlage_bij_onderwerp

    @pytest.mark.asyncio
    async def test_agenda_in_het_verleden_is_geen_vooruitblik_meer(self):
        """Een agenda van vorige week is een verslag, geen kans.

        Het onderscheid zit in de datum, niet in het soort: dezelfde
        `Agenda procedurevergadering` is vooruitkijkend zolang de
        vergadering nog moet komen.
        """
        gisteren = (date.today() - timedelta(days=1)).isoformat()
        async with _api(
            {
                "value": [
                    {
                        "DocumentNummer": "2026D00001",
                        "Soort": "Agenda procedurevergadering",
                        "Activiteit": [
                            {"Soort": "Procedurevergadering", "Datum": gisteren}
                        ],
                    }
                ]
            }
        ) as c:
            ctx = await haal_context("2026D00001", c)

        assert ctx.categorie == CAT_VERGADERING_TERUG

    @pytest.mark.asyncio
    async def test_agenda_in_de_toekomst_blijft_vooruitblik(self):
        morgen = (date.today() + timedelta(days=1)).isoformat()
        async with _api(
            {
                "value": [
                    {
                        "DocumentNummer": "2026D00002",
                        "Soort": "Agenda procedurevergadering",
                        "Activiteit": [
                            {"Soort": "Procedurevergadering", "Datum": morgen}
                        ],
                    }
                ]
            }
        ) as c:
            ctx = await haal_context("2026D00002", c)

        assert ctx.categorie == CAT_VERGADERING_VOORUIT
        assert ctx.dagen_tot_vergadering() == 1

    @pytest.mark.asyncio
    async def test_onbekend_document_faalt_zacht(self):
        async with _api({"value": []}) as c:
            ctx = await haal_context("2026D99999", c)
        # Geen context is geen reden om het alert te laten vallen.
        assert ctx.categorie == CAT_OVERIG
        assert ctx.soort is None

    @pytest.mark.asyncio
    async def test_api_storing_faalt_zacht(self):
        def handler(request):
            return httpx.Response(503, text="tijdelijk onbereikbaar")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            ctx = await haal_context("2026D44063", c)

        assert ctx.categorie == CAT_OVERIG

    @pytest.mark.asyncio
    async def test_as_extra_data_is_json_serialiseerbaar(self):
        import json

        ctx = KamerstukContext(
            soort="Schriftelijke vragen",
            categorie=CAT_VRAAG,
            termijn=date(2026, 10, 15),
            activiteit_datum=date(2026, 9, 24),
        )
        # extra_data gaat als JSON de database in; datums moeten strings zijn.
        json.dumps(ctx.as_extra_data())
        assert ctx.as_extra_data()["termijn"] == "2026-10-15"
