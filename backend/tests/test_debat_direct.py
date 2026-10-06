"""Tests for reading Debat Direct and matching it to an activiteit.

The fixture is a real debate (commissiedebat, 1 October 2026, 233 events
with a suspension, a continuation and a change of chairman), with the
speakers' names replaced by placeholders.
"""

from __future__ import annotations

import json
import pathlib
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from bouwmeester.services import debat_direct as dd
from bouwmeester.services.tk_activiteit import Activiteit

FIXTURE = json.loads(
    (
        pathlib.Path(__file__).parent / "fixtures/debat_direct_2026-10-01.json"
    ).read_text()
)
CEST = timezone(timedelta(hours=2))


def _client(handler):
    seen: list[httpx.Request] = []

    def recording(request):
        seen.append(request)
        return handler(request)

    return httpx.AsyncClient(transport=httpx.MockTransport(recording)), seen


def _activiteit(**overrides) -> Activiteit:
    values = {
        "id": "a1",
        "nummer": "2026A00001",
        "soort": "Commissiedebat",
        "onderwerp": FIXTURE["debate"]["name"],
        "aanvang": datetime(2026, 10, 1, 10, 0, tzinfo=CEST),
        "einde": None,
        "status": "Gepland",
        "commissie": None,
        "bewindspersonen": (),
        "agendapunten": (),
    }
    values.update(overrides)
    return Activiteit(**values)


def _debat(**overrides) -> dd.DdDebat:
    raw = {
        "id": "d1",
        "name": "Digitale overheid",
        "slug": "digitale-overheid-10-00",
        "debateType": "Commissiedebat",
        "debateDate": "2026-10-01",
        "startsAt": "2026-10-01T10:00:00+0200",
        "locationId": "klompezaal",
        "locationName": "Klompézaal",
        "categoryIds": ["binnenland"],
    }
    raw.update(overrides)
    return dd.parse_debate(raw)


class TestParse:
    def test_real_debate(self):
        debat = dd.parse_debate(FIXTURE["debate"])
        assert debat.id == "5d210dbb-9be4-4c39-8640-63a8ccec5b3a"
        assert debat.location_name == "Klompézaal"
        assert debat.started_at == datetime(2026, 10, 1, 10, 0, 36, tzinfo=CEST)
        assert len(debat.events) == 233

    def test_events_come_out_oldest_first(self):
        """The API returns newest first; a timeline is read the other way."""
        events = dd.parse_debate(FIXTURE["debate"]).events
        assert events[0].type == "debate_start"
        assert events[-1].type == "debate_end"
        assert [e.start for e in events] == sorted(e.start for e in events)

    def test_within_one_second_the_debate_resumes_before_someone_speaks(self):
        """11:34:00 carries both a `continued` and a `speaker`."""
        events = dd.parse_debate(FIXTURE["debate"]).events
        same = [e.type for e in events if e.raw_start == "2026-10-01T11:34:00+0200"]
        assert same == ["continued", "speaker"]

    def test_the_timestamp_is_kept_as_given(self):
        """A link to a moment is built from this exact string."""
        events = dd.parse_debate(FIXTURE["debate"]).events
        assert events[0].raw_start == "2026-10-01T10:00:36+0200"

    def test_duplicate_events_are_dropped(self):
        event = {
            "eventStart": "2026-10-01T10:00:00+0200",
            "eventType": "speaker",
            "objectId": "p1",
        }
        debat = _debat(events=[event, dict(event)])
        assert len(debat.events) == 1

    def test_values_are_cut_to_what_the_database_holds(self):
        """A row that does not fit fails after the message was posted, and
        the message is then posted again on every tick."""
        debat = _debat(
            events=[
                {
                    "eventStart": "2026-10-01T10:00:00+0200",
                    "eventType": "x" * 50,
                    "objectId": "y" * 100,
                }
            ]
        )
        (event,) = debat.events
        assert len(event.type) == 32
        assert len(event.object_id) == 64

    def test_odd_events_are_skipped_not_fatal(self):
        debat = _debat(
            events=[
                None,
                "x",
                {"eventStart": "geen tijd", "eventType": "speaker"},
                {"eventStart": "2026-10-01T10:00:00", "eventType": "speaker"},
                {"eventStart": "2026-10-01T10:00:00+0200"},
                {
                    "eventStart": "2026-10-01T10:00:05+0200",
                    "eventType": "speaker",
                    "objectId": "p1",
                },
            ]
        )
        assert [e.object_id for e in debat.events] == ["p1"]

    def test_without_id_there_is_no_debate(self):
        assert dd.parse_debate({"name": "x"}) is None

    def test_missing_fields_do_not_crash(self):
        debat = dd.parse_debate(
            {"id": "d1", "categoryIds": "geen lijst", "events": "x"}
        )
        assert debat.starts_at is None
        assert debat.category_ids == ()
        assert debat.events == ()


@pytest.mark.asyncio
class TestFetch:
    async def test_agenda(self):
        client, seen = _client(
            lambda r: httpx.Response(
                200, json={"debates": [FIXTURE["debate"], "x", {}]}
            )
        )
        debates = await dd.fetch_agenda(client, date(2026, 10, 1), base_url="http://dd")
        assert [d.id for d in debates] == ["5d210dbb-9be4-4c39-8640-63a8ccec5b3a"]
        assert seen[0].url.path == "/agenda/2026-10-01"
        # Without a browser-like agent the CDN refuses.
        assert "Mozilla" in seen[0].headers["user-agent"]

    async def test_debate(self):
        client, seen = _client(lambda r: httpx.Response(200, json=FIXTURE["debate"]))
        debat = await dd.fetch_debate(client, "5d210dbb", base_url="http://dd")
        assert len(debat.events) == 233
        assert seen[0].url.path == "/debates/5d210dbb"

    async def test_unknown_debate_is_none(self):
        client, _ = _client(lambda r: httpx.Response(404))
        assert await dd.fetch_debate(client, "weg") is None

    @pytest.mark.parametrize("call", ["agenda", "debate", "sprekers"])
    async def test_a_failing_api_raises(self, call):
        """With a body that parses: only the status says it went wrong."""
        client, _ = _client(lambda r: httpx.Response(503, json={"debates": []}))
        with pytest.raises(dd.DebatDirectError):
            if call == "agenda":
                await dd.fetch_agenda(client, date(2026, 10, 1))
            elif call == "debate":
                await dd.fetch_debate(client, "d1")
            else:
                await dd.fetch_sprekers(client, date(2026, 10, 1))

    async def test_network_error_raises(self):
        def boom(request):
            raise httpx.ConnectError("x", request=request)

        client, _ = _client(boom)
        with pytest.raises(dd.DebatDirectError):
            await dd.fetch_agenda(client, date(2026, 10, 1))

    async def test_html_instead_of_json_raises(self):
        client, _ = _client(lambda r: httpx.Response(200, text="<html>"))
        with pytest.raises(dd.DebatDirectError):
            await dd.fetch_debate(client, "d1")

    async def test_sprekers_with_party_and_function(self):
        client, seen = _client(lambda r: httpx.Response(200, json=FIXTURE["actors"]))
        sprekers = await dd.fetch_sprekers(
            client, date(2026, 10, 1), base_url="http://dd"
        )
        assert seen[0].url.path == "/actors/2026-10-01"
        assert len(sprekers) == 8
        labels = sorted(s.label for s in sprekers.values())
        assert "Bewindspersoon A (Minister van Voorbeeldzaken)" in labels
        assert "Kamerlid A (CDA)" in labels

    async def test_party_ids_match_whatever_their_case(self):
        """The two lists write the same id in different case."""
        body = {
            "politicians": [{"id": "p1", "name": "Kamerlid X", "partyId": "abc-DEF"}],
            "parties": [{"id": "ABC-def", "shorthand": "XYZ"}],
        }
        client, _ = _client(lambda r: httpx.Response(200, json=body))
        sprekers = await dd.fetch_sprekers(client, date(2026, 10, 1))
        assert sprekers["p1"].fractie == "XYZ"


class TestSprekerLabel:
    def test_party_behind_the_name(self):
        assert (
            dd.Spreker("Kamerlid A", "CDA", "Tweede Kamerlid").label
            == "Kamerlid A (CDA)"
        )

    def test_function_for_someone_without_a_party(self):
        assert (
            dd.Spreker("Bewindspersoon A", None, "Minister van X").label
            == "Bewindspersoon A (Minister van X)"
        )

    def test_a_member_without_a_known_party_is_just_the_name(self):
        """ "(Tweede Kamerlid)" says nothing the reader does not know."""
        assert dd.Spreker("Kamerlid A", None, "Tweede Kamerlid").label == "Kamerlid A"


class TestUrls:
    def test_debate_page(self):
        debat = dd.parse_debate(FIXTURE["debate"])
        assert dd.debate_url(debat) == (
            "https://debatdirect.tweedekamer.nl/2026-10-01/internationaal/klompezaal/"
            "informele-raad-buitenlandse-zaken-ontwikkeling-van-8-en-9-oktober-2026-10-00"
        )

    def test_moment_is_the_event_type_and_the_raw_timestamp(self):
        """What the site's own "spreekmomenten" link to."""
        debat = dd.parse_debate(FIXTURE["debate"])
        event = next(e for e in debat.events if e.type == "speaker")
        assert dd.moment_url(debat, event) == (
            dd.debate_url(debat) + "?event=speaker2026-10-01T10%3A01%3A20%2B0200"
        )

    def test_without_a_category_the_site_uses_overig(self):
        assert "/2026-10-01/overig/klompezaal/" in dd.debate_url(_debat(categoryIds=[]))

    @pytest.mark.parametrize("missing", ["slug", "locationId", "debateDate"])
    def test_no_link_without_what_the_url_is_made_of(self, missing):
        debat = _debat(**{missing: None})
        assert dd.debate_url(debat) is None
        event = dd.DdEvent(datetime(2026, 10, 1, tzinfo=CEST), "speaker", "p", "x")
        assert dd.moment_url(debat, event) is None


class TestSimilarity:
    def test_identical(self):
        assert dd.similarity("Digitale overheid", "Digitale overheid") == 1.0

    def test_shortened_subject_counts_as_nearly_equal(self):
        assert (
            dd.similarity(
                "Algemene Financiële Beschouwingen",
                "Algemene Financiële Beschouwingen (inclusief Belastingplan)",
            )
            >= 0.92
        )

    def test_a_short_name_inside_a_long_subject_is_the_same_debate(self):
        """Without the bonus for containment these score far too low:
        Debat Direct shows the first words, OData the whole title."""
        lang = (
            "Mensenrechtenbeleid en de inzet van Nederland in de "
            "Mensenrechtenraad van de Verenigde Naties en andere fora"
        )
        assert dd.similarity("Mensenrechtenbeleid", lang) == 0.92

    def test_accents_brackets_and_case_do_not_matter(self):
        assert (
            dd.similarity(
                "Financiële beschouwingen (voortzetting)", "FINANCIELE BESCHOUWINGEN"
            )
            == 1.0
        )

    def test_different_subjects(self):
        assert dd.similarity("Digitale overheid", "Mensenrechtenbeleid") < 0.5

    def test_empty_is_never_alike(self):
        assert dd.similarity("", "") == 0.0


class TestMatch:
    def test_real_debate_matches_its_activiteit(self):
        debat = dd.parse_debate(FIXTURE["debate"])
        assert dd.match_debates(_activiteit(), [debat, _debat()]) == [debat]

    def test_other_subject_does_not_match(self):
        assert (
            dd.match_debates(_activiteit(onderwerp="Mensenrechtenbeleid"), [_debat()])
            == []
        )

    def test_other_kind_of_meeting_does_not_match(self):
        """A procedurevergadering and a debate can carry the same subject."""
        a = _activiteit(onderwerp="Digitale overheid", soort="Procedurevergadering")
        assert dd.match_debates(a, [_debat()]) == []

    def test_kind_with_a_suffix_still_fits(self):
        """OData says "Plenair debat (wetgeving)", Debat Direct "Plenair debat"."""
        a = _activiteit(
            onderwerp="Digitale overheid", soort="Plenair debat (wetgeving)"
        )
        debat = _debat(debateType="Plenair debat")
        assert dd.match_debates(a, [debat]) == [debat]

    def test_too_far_off_in_time_does_not_match(self):
        a = _activiteit(onderwerp="Digitale overheid")
        assert dd.match_debates(a, [_debat(startsAt="2026-10-01T15:00:00+0200")]) == []

    def test_ninety_minutes_is_still_this_debate(self):
        """Debates start late; the measurement allowed this much."""
        a = _activiteit(onderwerp="Digitale overheid")
        debat = _debat(startsAt="2026-10-01T11:30:00+0200")
        assert dd.match_debates(a, [debat]) == [debat]

    def test_the_real_start_counts_over_the_planned_one(self):
        a = _activiteit(onderwerp="Digitale overheid")
        debat = _debat(
            startsAt="2026-10-01T08:00:00+0200", startedAt="2026-10-01T10:20:00+0200"
        )
        assert dd.match_debates(a, [debat]) == [debat]

    def test_a_debate_cut_in_two_gives_both_parts_in_order(self):
        """Debat Direct cuts a plenary debate around a break, against one
        activiteit. The second part starts hours later and is recognised
        by its subject, not by its time."""
        a = _activiteit(
            onderwerp="Algemene Financiële Beschouwingen (inclusief Belastingplan)",
            soort="Plenair debat (wetgeving)",
            aanvang=datetime(2026, 10, 1, 10, 15, tzinfo=CEST),
        )
        tweede = _debat(
            id="d2",
            name="Algemene Financiële Beschouwingen",
            debateType="Plenair debat",
            startsAt="2026-10-01T13:43:00+0200",
        )
        eerste = _debat(
            id="d1",
            name="Algemene Financiële Beschouwingen (voortzetting)",
            debateType="Plenair debat",
            startsAt="2026-10-01T10:15:00+0200",
            endedAt="2026-10-01T13:41:00+0200",
        )
        assert [d.id for d in dd.match_debates(a, [tweede, eerste])] == ["d1", "d2"]

    def _stemmingen(self, id_, start, end, name="Stemmingen"):
        return _debat(
            id=id_,
            name=name,
            debateType="Stemmingen",
            startsAt=f"2026-10-01T{start}:00+0200",
            startedAt=f"2026-10-01T{start}:00+0200",
            endedAt=f"2026-10-01T{end}:00+0200",
        )

    def test_votes_later_that_day_are_not_a_second_part(self):
        """As on 29 September 2026: votes at 15:27 and again at 17:25, each
        with an activiteit of its own. 65 minutes lie between them, which
        is a break's length, so only the name tells them apart."""
        middag = self._stemmingen("middag", "15:27", "16:20")
        avond = self._stemmingen("avond", "17:25", "17:28")
        a = _activiteit(
            onderwerp="Stemmingen",
            soort="Stemmingen",
            aanvang=datetime(2026, 10, 1, 15, 15, tzinfo=CEST),
        )
        assert [d.id for d in dd.match_debates(a, [avond, middag])] == ["middag"]
        later = _activiteit(
            onderwerp="AANSLUITEND: STEMMINGEN (over moties bij het tweeminutendebat)",
            soort="Stemmingen",
            aanvang=datetime(2026, 10, 1, 17, 25, tzinfo=CEST),
        )
        assert [d.id for d in dd.match_debates(later, [avond, middag])] == ["avond"]

    def test_of_two_items_on_time_the_one_named_like_it_is_meant(self):
        """As on 8 September 2026: a minute of "Regeling van werkzaamheden
        (stemmingen)" before the votes and the real one after them, against
        one activiteit. The first was 19 minutes off and the real one 35,
        so the time does not say which."""
        kort = _debat(
            id="kort",
            name="Regeling van werkzaamheden (stemmingen)",
            debateType="Regeling van werkzaamheden",
            startsAt="2026-10-01T15:26:00+0200",
            endedAt="2026-10-01T15:27:00+0200",
        )
        echt = _debat(
            id="echt",
            name="Regeling van werkzaamheden",
            debateType="Regeling van werkzaamheden",
            startsAt="2026-10-01T16:19:00+0200",
            endedAt="2026-10-01T17:01:00+0200",
        )
        a = _activiteit(
            onderwerp="Regeling van werkzaamheden",
            soort="Regeling van werkzaamheden",
            aanvang=datetime(2026, 10, 1, 15, 45, tzinfo=CEST),
        )
        assert [d.id for d in dd.match_debates(a, [kort, echt])] == ["echt"]
        # And with words in front of it, as the activiteit of 24 September.
        a = _activiteit(
            onderwerp="Aanvang middagvergadering: Regeling van werkzaamheden",
            soort="Regeling van werkzaamheden",
            aanvang=datetime(2026, 10, 1, 15, 45, tzinfo=CEST),
        )
        assert [d.id for d in dd.match_debates(a, [kort, echt])] == ["echt"]

    def test_two_meetings_alike_in_name_at_one_hour_are_not_two_parts(self):
        """As on 28 September 2026: two meetings in two rooms, the names
        just alike enough. The one that is named like the activiteit."""
        naam = "Implementatiewet herziene richtlijn zeevaart"
        ander = "Implementatiewet herziene EU-richtlijn luchtvaart"
        assert dd.similarity(naam, ander) >= dd.MIN_SIMILARITY
        deze = _debat(
            id="deze",
            name=naam,
            debateType="Wetgevingsoverleg",
            startsAt="2026-10-01T10:01:00+0200",
            endedAt="2026-10-01T14:49:00+0200",
        )
        andere = _debat(
            id="andere",
            name=ander,
            debateType="Wetgevingsoverleg",
            startsAt="2026-10-01T10:00:00+0200",
            endedAt="2026-10-01T14:18:00+0200",
        )
        a = _activiteit(onderwerp=naam, soort="Wetgevingsoverleg")
        assert [d.id for d in dd.match_debates(a, [andere, deze])] == ["deze"]

    def test_the_subject_counts_before_how_it_is_written(self):
        """Debat Direct shortens a subject. The short one is the same
        subject; another one that happens to be written out as long as the
        activiteit only looks more like it letter by letter."""
        onderwerp = "Tweeminutendebat Zeevaartraad (informeel) d.d. 28-29 september"
        kort = _debat(id="kort", name="Zeevaartraad", debateType="Plenair debat")
        lang = _debat(
            id="lang",
            name="Tweeminutendebat Luchtvaartraad (informeel) d.d. 28-29 september",
            debateType="Plenair debat",
            startsAt="2026-10-01T10:01:00+0200",
        )
        assert dd.similarity(onderwerp, lang.name) >= dd.MIN_SIMILARITY
        assert dd._literal_likeness(onderwerp, lang.name) > dd._literal_likeness(
            onderwerp, kort.name
        )
        a = _activiteit(onderwerp=onderwerp, soort="Plenair debat (tweeminutendebat)")
        assert [d.id for d in dd.match_debates(a, [lang, kort])] == ["kort"]

    def test_the_same_subject_hours_after_the_end_is_another_item(self):
        """As on 24 September 2026: an election, and 193 minutes after it
        one that is named nearly the same."""
        eerste = _debat(
            id="eerste",
            name="Verkiezing van een voorzitter",
            debateType="Constituerende vergadering",
            startsAt="2026-10-01T10:16:00+0200",
            endedAt="2026-10-01T10:19:00+0200",
        )
        tweede = _debat(
            id="tweede",
            name="Verkiezing van een ondervoorzitter",
            debateType="Constituerende vergadering",
            startsAt="2026-10-01T13:32:00+0200",
            endedAt="2026-10-01T13:35:00+0200",
        )
        a = _activiteit(
            onderwerp="Verkiezing van een voorzitter",
            soort="Constituerende vergadering",
            aanvang=datetime(2026, 10, 1, 10, 15, tzinfo=CEST),
        )
        assert [d.id for d in dd.match_debates(a, [eerste, tweede])] == ["eerste"]

    def test_a_break_of_an_hour_is_still_one_debate(self):
        """As on 30 September 2026: 63 minutes between the parts, the
        longest break measured."""
        eerste = _debat(
            id="d1",
            name="Algemene Financiële Beschouwingen",
            debateType="Plenair debat",
            startsAt="2026-10-01T10:35:00+0200",
            endedAt="2026-10-01T13:15:00+0200",
        )
        tweede = _debat(
            id="d2",
            name="Algemene Financiële Beschouwingen",
            debateType="Plenair debat",
            startsAt="2026-10-01T14:19:00+0200",
        )
        a = _activiteit(
            onderwerp="Algemene Financiële Beschouwingen (inclusief begroting)",
            soort="Plenair debat (wetgeving)",
            aanvang=datetime(2026, 10, 1, 10, 35, tzinfo=CEST),
        )
        assert [d.id for d in dd.match_debates(a, [tweede, eerste])] == ["d1", "d2"]

    def test_a_short_first_part_belongs_with_the_part_that_is_nearer(self):
        """Both parts on time, the second nearer to the planned start: the
        part before it is found as well as a part after it."""
        delen = [
            _debat(
                id=id_,
                debateType="Plenair debat",
                startsAt=f"2026-10-01T{start}:00+0200",
                endedAt=f"2026-10-01T{end}:00+0200",
            )
            for id_, start, end in (
                ("d1", "09:40", "09:50"),
                ("d2", "09:58", "12:00"),
                ("d3", "12:30", "14:00"),
            )
        ]
        a = _activiteit(onderwerp="Digitale overheid", soort="Plenair debat")
        assert [d.id for d in dd.match_debates(a, delen[::-1])] == ["d1", "d2", "d3"]

    def test_a_part_that_has_not_ended_has_no_next_part(self):
        eerste = _debat(id="d1", debateType="Plenair debat")
        tweede = _debat(
            id="d2", debateType="Plenair debat", startsAt="2026-10-01T10:30:00+0200"
        )
        a = _activiteit(onderwerp="Digitale overheid", soort="Plenair debat")
        assert [d.id for d in dd.match_debates(a, [eerste, tweede])] == ["d1"]

    def test_an_earlier_debate_with_the_same_subject_is_not_a_part(self):
        """Only parts after the one that matched on time belong to it."""
        a = _activiteit(
            onderwerp="Regeling van werkzaamheden",
            soort="Regeling van werkzaamheden",
            aanvang=datetime(2026, 10, 1, 15, 0, tzinfo=CEST),
        )
        ochtend = _debat(
            id="vroeg",
            name="Regeling van werkzaamheden",
            debateType="Regeling van werkzaamheden",
            startsAt="2026-10-01T10:00:00+0200",
        )
        middag = _debat(
            id="nu",
            name="Regeling van werkzaamheden",
            debateType="Regeling van werkzaamheden",
            startsAt="2026-10-01T15:02:00+0200",
        )
        assert [d.id for d in dd.match_debates(a, [ochtend, middag])] == ["nu"]

    def test_same_subject_but_nothing_near_the_start_is_no_match(self):
        a = _activiteit(
            onderwerp="Digitale overheid",
            aanvang=datetime(2026, 10, 1, 19, 0, tzinfo=CEST),
        )
        assert dd.match_debates(a, [_debat()]) == []

    def test_nothing_to_match_against(self):
        assert dd.match_debates(_activiteit(), []) == []


class TestLaterParts:
    def _first(self, **overrides):
        values = {
            "id": "d1",
            "name": "Algemene Financiële Beschouwingen",
            "debateType": "Plenair debat",
            "startsAt": "2026-10-01T12:15:00+0200",
            "startedAt": "2026-10-01T12:15:00+0200",
            "endedAt": "2026-10-01T15:00:00+0200",
        }
        values.update(overrides)
        return _debat(**values)

    def _second(self, **overrides):
        values = {
            "id": "d2",
            "name": "Algemene Financiële Beschouwingen (voortzetting)",
            "debateType": "Plenair debat",
            "startsAt": "2026-10-01T16:00:00+0200",
        }
        values.update(overrides)
        return _debat(**values)

    def test_same_subject_and_kind_after_the_known_part(self):
        found = dd.later_parts(
            "Algemene Financiële Beschouwingen", ["d1"], [self._second(), self._first()]
        )
        assert [d.id for d in found] == ["d2"]

    def test_works_however_late_the_first_part_started(self):
        """It compares with the known part, not with the planned time of
        the activiteit, which the debate may have left far behind."""
        first = self._first(
            startedAt="2026-10-01T15:30:00+0200", endedAt="2026-10-01T19:00:00+0200"
        )
        second = self._second(startsAt="2026-10-01T20:00:00+0200")
        found = dd.later_parts(
            "Algemene Financiële Beschouwingen", ["d1"], [first, second]
        )
        assert [d.id for d in found] == ["d2"]

    def test_another_kind_with_the_same_subject_is_not_a_part(self):
        second = self._second(debateType="Stemmingen")
        assert (
            dd.later_parts(
                "Algemene Financiële Beschouwingen", ["d1"], [self._first(), second]
            )
            == []
        )

    def test_an_earlier_debate_is_not_a_later_part(self):
        second = self._second(startsAt="2026-10-01T09:00:00+0200")
        assert (
            dd.later_parts(
                "Algemene Financiële Beschouwingen", ["d1"], [self._first(), second]
            )
            == []
        )

    def test_another_subject_is_not_a_part(self):
        second = self._second(name="Mensenrechtenbeleid")
        assert (
            dd.later_parts(
                "Algemene Financiële Beschouwingen", ["d1"], [self._first(), second]
            )
            == []
        )

    def test_a_known_part_is_not_found_again(self):
        assert (
            dd.later_parts("Algemene Financiële Beschouwingen", ["d1"], [self._first()])
            == []
        )

    def test_two_hours_after_the_end_is_the_longest_break(self):
        """Twice the longest break measured (63 minutes)."""
        binnen = self._second(startsAt="2026-10-01T17:00:00+0200")
        buiten = self._second(startsAt="2026-10-01T17:01:00+0200")
        name = "Algemene Financiële Beschouwingen"
        assert dd.later_parts(name, ["d1"], [self._first(), binnen]) == [binnen]
        assert dd.later_parts(name, ["d1"], [self._first(), buiten]) == []

    def test_what_starts_before_the_known_part_ended_is_not_its_next_part(self):
        second = self._second(startsAt="2026-10-01T14:59:00+0200")
        assert (
            dd.later_parts(
                "Algemene Financiële Beschouwingen", ["d1"], [self._first(), second]
            )
            == []
        )

    def test_while_the_known_part_runs_nothing_follows_it(self):
        """The end is what a break is measured from."""
        first = self._first(endedAt=None)
        assert (
            dd.later_parts(
                "Algemene Financiële Beschouwingen", ["d1"], [first, self._second()]
            )
            == []
        )

    def test_a_third_part_follows_the_second_not_the_first(self):
        """Five hours after the first part ended, an hour after the second."""
        second = self._second(endedAt="2026-10-01T19:00:00+0200")
        third = self._second(id="d3", startsAt="2026-10-01T20:00:00+0200")
        name = "Algemene Financiële Beschouwingen"
        found = dd.later_parts(name, ["d1"], [third, self._first(), second])
        assert [d.id for d in found] == ["d2", "d3"]
        assert dd.later_parts(name, ["d1", "d2"], [third, self._first(), second]) == [
            third
        ]

    @pytest.mark.parametrize(
        "name",
        ["Stemmingen", "Mededelingen", "Regeling van werkzaamheden (stemmingen)"],
    )
    def test_an_item_that_recurs_by_name_is_never_continued(self, name):
        """Votes, announcements and the order of business are on the agenda
        several times a day, within a break's length of each other."""
        first = self._first(name=name, debateType=name.split(" (")[0])
        second = self._second(
            name=name.split(" (")[0],
            debateType=name.split(" (")[0],
            startsAt="2026-10-01T15:04:00+0200",
        )
        assert dd.later_parts(name, ["d1"], [first, second]) == []

    def test_an_item_that_recurs_is_known_by_its_kind_under_a_longer_name(self):
        name = "Stemmingen over moties"
        first = self._first(name=name, debateType="Stemmingen")
        second = self._second(name=name, debateType="Stemmingen")
        assert dd.later_parts(name, ["d1"], [first, second]) == []

    def test_an_item_that_recurs_is_known_by_its_name_without_a_kind(self):
        first = self._first(name="Stemmingen", debateType="Plenair debat")
        second = self._second(name="Stemmingen", debateType="Plenair debat")
        assert dd.later_parts("Stemmingen", ["d1"], [first, second]) == []

    def test_without_the_known_part_on_the_agenda_nothing_is_guessed(self):
        assert (
            dd.later_parts(
                "Algemene Financiële Beschouwingen", ["d1"], [self._second()]
            )
            == []
        )


class TestStream:
    def _debate(self, video: object) -> dd.DdDebat:
        return dd.parse_debate({"id": "d1", "name": "Debat", "video": video})

    def test_the_stream_and_how_far_its_sound_is_behind(self):
        debat = self._debate(
            {"url": "https://stream.example/zaal/index.m3u8", "pdtOffset": 2000}
        )

        assert debat.stream_url == "https://stream.example/zaal/index.m3u8"
        assert debat.stream_offset == timedelta(seconds=2)

    def test_a_debate_without_video(self):
        debat = self._debate(None)

        assert debat.stream_url is None
        assert debat.stream_offset == timedelta(0)

    def test_the_audio_of_the_room_is_kept(self):
        debat = self._debate({"audioUrl": "https://stream.example/zaal/audio.m3u8"})
        assert debat.audio_url == "https://stream.example/zaal/audio.m3u8"

    @pytest.mark.parametrize("url", ["http://stream.example/a.m3u8", "", None, 7])
    def test_audio_that_is_not_https_is_not_kept(self, url):
        assert self._debate({"audioUrl": url}).audio_url is None

    def test_a_debate_without_audio(self):
        assert self._debate({}).audio_url is None

    @pytest.mark.parametrize(
        "url", ["http://stream.example/x.m3u8", "file:///etc/passwd", "", 12]
    )
    def test_only_an_https_address_is_a_stream(self, url):
        assert self._debate({"url": url}).stream_url is None

    @pytest.mark.parametrize("offset", ["2000", None, -5, 60_001, True])
    def test_an_offset_that_makes_no_sense_is_none(self, offset):
        debat = self._debate({"url": "https://x.example/a", "pdtOffset": offset})

        assert debat.stream_offset == timedelta(0)

    def test_an_offset_at_the_edge_counts(self):
        assert self._debate({"pdtOffset": 60_000}).stream_offset == timedelta(minutes=1)
        assert self._debate({"pdtOffset": 0}).stream_offset == timedelta(0)
        assert self._debate({"pdtOffset": 1500.0}).stream_offset == timedelta(
            seconds=1.5
        )
