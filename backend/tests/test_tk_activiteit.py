"""Tests for reading an activiteit and its agenda from the TK API.

The response in `RAW` has the shape of a real one (commissiedebat
Leefomgeving, 6 October 2026), shortened to what the parser touches.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from bouwmeester.services.tk_activiteit import (
    TkApiError,
    fetch_activiteit,
    parse_activiteit,
)

ID = "cc83dcc6-44ac-46ee-b56d-87371a47f94f"


def _doc(nummer: str, **extra) -> dict:
    return {
        "DocumentNummer": nummer,
        "Soort": "Brief regering",
        "Onderwerp": f"Onderwerp van {nummer}",
        "Verwijderd": False,
        **extra,
    }


def _raw(**overrides) -> dict:
    raw = {
        "Id": ID,
        "Nummer": "2026A05428",
        "Soort": "Commissiedebat",
        "Onderwerp": "Leefomgeving",
        "Aanvangstijd": "2026-10-06T16:30:00+02:00",
        "Eindtijd": "2026-10-06T21:30:00+02:00",
        "Status": "Gepland",
        "Voortouwnaam": "vaste commissie voor Infrastructuur en Waterstaat",
        "Verwijderd": False,
        "Agendapunt": [
            {
                "Onderwerp": "Bestuurlijk Overleg over aandachtlocaties PFAS",
                "Volgorde": 9,
                "Verwijderd": False,
                "Document": [],
                "Zaak": [
                    {
                        "Nummer": "2026Z19444",
                        "Onderwerp": "Bestuurlijk Overleg PFAS",
                        "Verwijderd": False,
                        "Document": [_doc("2026D45092")],
                    }
                ],
            },
            {
                "Onderwerp": "Advies geurregelgeving veehouderijen",
                "Volgorde": 1,
                "Verwijderd": False,
                "Document": [],
                "Zaak": [
                    {
                        "Nummer": "2026Z12093",
                        "Onderwerp": "Advies geurregelgeving",
                        "Verwijderd": False,
                        "Document": [_doc("2026D27459"), _doc("2026D27460")],
                    }
                ],
            },
        ],
        "ActiviteitActor": [
            {
                "ActorNaam": "A.W.H. Bertram",
                "Relatie": "Bewindspersoon c.a.",
                "Functie": "staatssecretaris van Infrastructuur en Waterstaat",
                "Verwijderd": False,
            },
            {
                "ActorNaam": "S. van Veldhoven",
                "Relatie": "Afgemeld",
                "Functie": "minister van Klimaat en Groene Groei",
                "Verwijderd": False,
            },
            {
                "ActorNaam": "I. Kostić",
                "Relatie": "Deelnemer",
                "Functie": "Tweede Kamerlid",
                "Verwijderd": False,
            },
        ],
    }
    raw.update(overrides)
    return raw


class TestParse:
    def test_basic_fields(self):
        a = parse_activiteit(_raw())
        assert a.id == ID
        assert a.nummer == "2026A05428"
        assert a.soort == "Commissiedebat"
        assert a.onderwerp == "Leefomgeving"
        assert a.status == "Gepland"
        assert a.commissie == "vaste commissie voor Infrastructuur en Waterstaat"

    def test_times_keep_their_offset(self):
        a = parse_activiteit(_raw())
        assert a.aanvang == datetime(
            2026, 10, 6, 16, 30, tzinfo=timezone(timedelta(hours=2))
        )
        assert a.einde.hour == 21

    def test_agenda_follows_volgorde_not_api_order(self):
        """The API returns agendapunten in no particular order."""
        a = parse_activiteit(_raw())
        assert [p.volgorde for p in a.agendapunten] == [1, 9]
        assert a.agendapunten[0].onderwerp == "Advies geurregelgeving veehouderijen"

    def test_agendapunt_without_volgorde_goes_last(self):
        raw = _raw()
        raw["Agendapunt"].append(
            {"Onderwerp": "Rondvraag", "Volgorde": None, "Verwijderd": False}
        )
        a = parse_activiteit(raw)
        assert [p.onderwerp for p in a.agendapunten][-1] == "Rondvraag"

    def test_documents_come_from_the_zaak(self):
        a = parse_activiteit(_raw())
        punt = a.agendapunten[0]
        assert punt.zaak_nummer == "2026Z12093"
        assert [d.nummer for d in punt.documenten] == ["2026D27459", "2026D27460"]
        assert punt.documenten[0].soort == "Brief regering"

    def test_each_document_knows_its_own_zaak(self):
        raw = _raw()
        raw["Agendapunt"][1]["Zaak"].append(
            {
                "Nummer": "2026Z99999",
                "Verwijderd": False,
                "Document": [_doc("2026D99999")],
            }
        )
        a = parse_activiteit(raw)
        zaken = {d.nummer: d.zaak_nummer for d in a.agendapunten[0].documenten}
        assert zaken == {
            "2026D27459": "2026Z12093",
            "2026D27460": "2026Z12093",
            "2026D99999": "2026Z99999",
        }

    def test_document_directly_on_the_agendapunt_has_no_zaak(self):
        raw = _raw()
        raw["Agendapunt"][1]["Zaak"] = []
        raw["Agendapunt"][1]["Document"] = [_doc("2026D00001")]
        a = parse_activiteit(raw)
        assert a.agendapunten[0].documenten[0].zaak_nummer is None

    @pytest.mark.parametrize(
        ("value", "expected"),
        [(True, True), (False, False), (None, False), ("ja", False)],
    )
    def test_besloten(self, value, expected):
        assert parse_activiteit(_raw(Besloten=value)).besloten is expected

    def test_document_on_both_routes_counts_once(self):
        raw = _raw()
        raw["Agendapunt"][1]["Document"] = [_doc("2026D27459")]
        a = parse_activiteit(raw)
        assert [d.nummer for d in a.agendapunten[0].documenten] == [
            "2026D27459",
            "2026D27460",
        ]

    def test_deleted_rows_are_dropped(self):
        """`Verwijderd` rows stay in the API; an agenda that lists them
        shows documents that were taken off."""
        raw = _raw()
        raw["Agendapunt"][0]["Verwijderd"] = True
        raw["Agendapunt"][1]["Zaak"][0]["Document"][1]["Verwijderd"] = True
        a = parse_activiteit(raw)
        assert len(a.agendapunten) == 1
        assert [d.nummer for d in a.agendapunten[0].documenten] == ["2026D27459"]

    def test_agendapunt_without_zaak_is_kept(self):
        """ "Indicatieve spreektijd 4 minuten" is on the agenda too."""
        a = parse_activiteit(
            _raw(
                Agendapunt=[
                    {"Onderwerp": "Indicatieve spreektijd", "Volgorde": 1, "Zaak": []}
                ]
            )
        )
        assert a.agendapunten[0].documenten == ()
        assert a.agendapunten[0].zaak_nummer is None

    def test_only_bewindspersonen_who_come(self):
        """Someone who cancelled has relation "Afgemeld", a member of
        parliament "Deelnemer"; neither is at the table as bewindspersoon."""
        a = parse_activiteit(_raw())
        assert [b.naam for b in a.bewindspersonen] == ["A.W.H. Bertram"]
        assert a.bewindspersonen[0].functie.startswith("staatssecretaris")

    def test_odd_fields_do_not_crash(self):
        a = parse_activiteit(
            {
                "Id": ID,
                "Onderwerp": None,
                "Aanvangstijd": 12345,
                "Eindtijd": "geen datum",
                "Agendapunt": "geen lijst",
                "ActiviteitActor": [None, "x", {"Relatie": None}],
            }
        )
        assert a.onderwerp == ""
        assert a.aanvang is None
        assert a.einde is None
        assert a.agendapunten == ()
        assert a.bewindspersonen == ()

    def test_naive_time_is_not_a_time(self):
        """Comparing a naive time with now raises; better no time at all."""
        a = parse_activiteit(_raw(Aanvangstijd="2026-10-06T16:30:00"))
        assert a.aanvang is None

    def test_true_is_not_an_order(self):
        raw = _raw()
        raw["Agendapunt"][0]["Volgorde"] = True
        a = parse_activiteit(raw)
        assert [p.volgorde for p in a.agendapunten] == [1, None]


def _client(handler) -> tuple[httpx.AsyncClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def recording(request):
        seen.append(request)
        return handler(request)

    return httpx.AsyncClient(transport=httpx.MockTransport(recording)), seen


@pytest.mark.asyncio
class TestFetch:
    async def test_asks_for_this_activiteit_with_its_agenda(self):
        client, seen = _client(lambda r: httpx.Response(200, json={"value": [_raw()]}))
        a = await fetch_activiteit(ID, client, base_url="http://tk.test")
        assert a.nummer == "2026A05428"
        params = seen[0].url.params
        assert seen[0].url.path == "/Activiteit"
        assert params["$filter"] == f"Id eq {ID}"
        # OData returns only what is asked for. Without these the agenda
        # is empty while the test data above still has it.
        for veld in (
            "Aanvangstijd",
            "Eindtijd",
            "Status",
            "Verwijderd",
            "Nummer",
            "Besloten",
        ):
            assert veld in params["$select"]
        for entiteit in ("Agendapunt(", "Zaak(", "Document(", "ActiviteitActor("):
            assert entiteit in params["$expand"]
        assert "Volgorde" in params["$expand"]
        assert "Relatie" in params["$expand"]

    async def test_unknown_id_is_none(self):
        client, _ = _client(lambda r: httpx.Response(200, json={"value": []}))
        assert await fetch_activiteit(ID, client) is None

    async def test_deleted_activiteit_is_none(self):
        client, _ = _client(
            lambda r: httpx.Response(200, json={"value": [_raw(Verwijderd=True)]})
        )
        assert await fetch_activiteit(ID, client) is None

    async def test_server_error_is_not_none(self):
        """ "Gone" and "could not ask" lead to different messages."""
        # With a body that parses as "no rows": only the status tells
        # this apart from a meeting that was taken off the agenda.
        client, _ = _client(lambda r: httpx.Response(503, json={"value": []}))
        with pytest.raises(TkApiError):
            await fetch_activiteit(ID, client)

    async def test_network_error_raises(self):
        def boom(request):
            raise httpx.ReadTimeout("slow", request=request)

        client, _ = _client(boom)
        with pytest.raises(TkApiError):
            await fetch_activiteit(ID, client)

    async def test_html_instead_of_json_raises(self):
        client, _ = _client(lambda r: httpx.Response(200, text="<html>"))
        with pytest.raises(TkApiError):
            await fetch_activiteit(ID, client)

    @pytest.mark.parametrize("bad", ["", "x' or 1 eq 1", "2026A05428", None])
    async def test_non_guid_never_reaches_the_api(self, bad):
        client, seen = _client(lambda r: httpx.Response(200, json={"value": [_raw()]}))
        with pytest.raises(TkApiError):
            await fetch_activiteit(bad, client)
        assert seen == []
