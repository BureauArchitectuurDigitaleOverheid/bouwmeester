"""Tests for announcing a debate in the channels of an initiatief.

The builders are pure. The service runs against a real database with a
fake Mattermost and a stubbed TK API, because what matters is which
channels get a message and what the row says afterwards.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.debat_aankondiging import (
    STAND_AANGEKONDIGD,
    STAND_AFGELAST,
    STAND_HERINNERD,
    STAND_VOORBIJ,
    DebatAankondiging,
)
from bouwmeester.models.debat_sessie import DebatSessie
from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.mattermost_channel_link import (
    SCOPE_INITIATIEF,
    MattermostChannelLink,
)
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.services import debat_aankondiging_service as mod
from bouwmeester.services import debat_kanaal_service as kanaal_mod
from bouwmeester.services.debat_aankondiging_service import (
    REACTIE_AANKONDIGEN,
    AlreadyAnnouncedError,
    AnnounceRefusedError,
    DebatAankondigingService,
    announcement_message,
    is_announceable,
    is_over,
    reminder_message,
)
from bouwmeester.services.tk_activiteit import TkApiError
from tests.factories import client_as, make_person
from tests.test_debat_kanaal import AMS, TEAM, FakeMattermost, _activiteit

OTHER_TEAM = "team00000000000000000000bb"
# The morning of the debate `_activiteit` makes: 6 October 2099, 16:30.
MORNING = datetime(2099, 10, 6, 9, 0, tzinfo=AMS)


class Mattermost(FakeMattermost):
    enabled = True

    async def is_enabled(self) -> bool:
        return self.enabled


def _known(monkeypatch, *activiteiten, error: Exception | None = None):
    """Make the TK API know these activiteiten, each by its id."""
    known = {a.id: a for a in activiteiten}
    asked: list[str] = []

    async def fake_fetch(activiteit_id, client, base_url=None):
        asked.append(activiteit_id)
        if error is not None:
            raise error
        return known.get(activiteit_id)

    monkeypatch.setattr(mod, "fetch_activiteit", fake_fetch)
    # `find_successor` lives in the channel service and reads from there.
    monkeypatch.setattr(kanaal_mod, "fetch_activiteit", fake_fetch)
    return asked


@pytest.fixture
async def initiatief(db_session):
    row = Initiatief(id=uuid.uuid4(), naam=f"Initiatief {uuid.uuid4().hex[:8]}")
    db_session.add(row)
    await db_session.flush()
    return row


async def _link(db_session, initiatief, *, team=TEAM, **overrides):
    values = {
        "channel_id": uuid.uuid4().hex[:26],
        "channel_name": "een-kanaal",
        "channel_display_name": "Een kanaal",
        "team_id": team,
        "scope_type": SCOPE_INITIATIEF,
        "scope_id": initiatief.id,
    }
    values.update(overrides)
    link = MattermostChannelLink(**values)
    db_session.add(link)
    await db_session.flush()
    return link


async def _row(db_session, initiatief, activiteit, **overrides):
    values = {
        "initiatief_id": initiatief.id,
        "activiteit_id": activiteit.id,
        "activiteit_nummer": activiteit.nummer,
        "soort": activiteit.soort,
        "onderwerp": activiteit.onderwerp,
        "commissie": activiteit.commissie,
        "aanvang": activiteit.aanvang,
        "einde": activiteit.einde,
    }
    values.update(overrides)
    row = DebatAankondiging(**values)
    db_session.add(row)
    await db_session.flush()
    return row


async def _announce(db_session, mm, initiatief, activiteit):
    return await DebatAankondigingService(db_session, mm).announce(
        initiatief, activiteit.id, person_id=None, door="een collega"
    )


async def _rows(db_session, initiatief):
    stmt = select(DebatAankondiging).where(
        DebatAankondiging.initiatief_id == initiatief.id
    )
    return list((await db_session.execute(stmt)).scalars().all())


class TestMessages:
    def test_announcement_says_what_when_and_for_whom(self):
        tekst = announcement_message(
            _activiteit(), initiatief_naam="Regelrecht", door="een collega"
        )

        assert "[Digitaliserende overheid](https://www.tweedekamer.nl/" in tekst
        assert "details?id=2099A05428" in tekst
        assert "Commissiedebat · dinsdag 6 oktober, 16:30 tot 19:30" in tekst
        assert "vaste commissie voor Digitale Zaken" in tekst
        assert "Aangekondigd door een collega voor **Regelrecht**." in tekst
        assert "Op de dag zelf volgt hier een herinnering." in tekst

    def test_announcement_of_today_promises_no_reminder(self):
        tekst = announcement_message(
            _activiteit(), initiatief_naam="X", door=None, reminder_follows=False
        )

        assert "herinnering" not in tekst
        assert "Aangekondigd voor **X**." in tekst

    def test_subject_cannot_break_out_of_the_link(self):
        tekst = announcement_message(
            _activiteit(onderwerp="Wet [x](http://kwaad) *vet*"),
            initiatief_naam="X",
            door=None,
        )

        assert "](http://kwaad)" not in tekst

    def test_without_nummer_there_is_no_link(self):
        tekst = reminder_message(_activiteit(nummer=None))

        assert "**Vandaag om 16:30: Digitaliserende overheid**" in tekst

    def test_reminder_names_the_time_and_where_to_watch(self):
        tekst = reminder_message(_activiteit(), "debat-digitaal-6-okt")

        assert tekst.startswith("🔔 **Vandaag om 16:30: [Digitaliserende overheid](")
        assert "[Live via Debat Direct](https://debatdirect.tweedekamer.nl)" in tekst
        assert "~debat-digitaal-6-okt" in tekst

    def test_is_over_goes_by_the_end_when_there_is_one(self):
        start = datetime(2026, 10, 6, 10, 0, tzinfo=UTC)
        assert (
            is_over(start, start + timedelta(hours=10), start + timedelta(hours=9))
            is False
        )
        assert (
            is_over(start, start + timedelta(hours=1), start + timedelta(hours=2))
            is True
        )
        # Without an end a meeting is given a few hours.
        assert is_over(start, None, start + timedelta(hours=1)) is False
        assert is_over(start, None, start + timedelta(hours=9)) is True


@pytest.mark.asyncio
class TestAnnounce:
    async def test_posts_in_every_linked_channel_whatever_its_switches(
        self, db_session, initiatief, monkeypatch
    ):
        activiteit = _activiteit()
        _known(monkeypatch, activiteit)
        een = await _link(db_session, initiatief)
        twee = await _link(db_session, initiatief, parlementaire_alerts_enabled=True)
        await _link(db_session, initiatief, disabled_at=datetime.now(UTC))
        other = Initiatief(id=uuid.uuid4(), naam=f"Ander {uuid.uuid4().hex[:8]}")
        db_session.add(other)
        await db_session.flush()
        await _link(db_session, other)
        mm = Mattermost()

        result = await _announce(db_session, mm, initiatief, activiteit)

        assert result.gepost_in == 2
        assert {m[0] for m in mm.messages} == {een.channel_id, twee.channel_id}
        assert all("Debat aangekondigd" in m[1] for m in mm.messages)
        (row,) = await _rows(db_session, initiatief)
        assert row.activiteit_id == activiteit.id
        assert row.activiteit_nummer == "2099A05428"
        assert row.onderwerp == "Digitaliserende overheid"
        assert row.aanvang == activiteit.aanvang
        assert row.stand == STAND_AANGEKONDIGD

    async def test_without_a_channel_the_debate_is_still_listed(
        self, db_session, initiatief, monkeypatch
    ):
        activiteit = _activiteit()
        _known(monkeypatch, activiteit)
        mm = Mattermost()

        result = await _announce(db_session, mm, initiatief, activiteit)

        assert result.gepost_in == 0
        assert mm.messages == []
        assert len(await _rows(db_session, initiatief)) == 1

    async def test_mattermost_off_still_lists_the_debate(
        self, db_session, initiatief, monkeypatch
    ):
        activiteit = _activiteit()
        _known(monkeypatch, activiteit)
        await _link(db_session, initiatief)
        mm = Mattermost()
        mm.enabled = False

        result = await _announce(db_session, mm, initiatief, activiteit)

        assert result.gepost_in == 0
        assert mm.messages == []

    @pytest.mark.parametrize(
        ("overrides", "woord"),
        [
            ({"status": "Geannuleerd"}, "geannuleerd"),
            ({"status": "Verplaatst"}, "verplaatst"),
            (
                {
                    "aanvang": datetime(2020, 1, 7, 10, 0, tzinfo=AMS),
                    "einde": datetime(2020, 1, 7, 12, 0, tzinfo=AMS),
                },
                "al geweest",
            ),
        ],
    )
    async def test_refuses_what_is_off_or_over(
        self, db_session, initiatief, monkeypatch, overrides, woord
    ):
        activiteit = _activiteit(**overrides)
        _known(monkeypatch, activiteit)
        await _link(db_session, initiatief)
        mm = Mattermost()

        with pytest.raises(AnnounceRefusedError, match=woord):
            await _announce(db_session, mm, initiatief, activiteit)

        assert mm.messages == []
        assert await _rows(db_session, initiatief) == []

    async def test_refuses_a_meeting_the_kamer_does_not_know(
        self, db_session, initiatief, monkeypatch
    ):
        _known(monkeypatch)

        with pytest.raises(AnnounceRefusedError, match="niet meer op de agenda"):
            await _announce(db_session, Mattermost(), initiatief, _activiteit())

    async def test_a_second_time_is_refused_and_posts_nothing(
        self, db_session, initiatief, monkeypatch
    ):
        activiteit = _activiteit()
        _known(monkeypatch, activiteit)
        await _link(db_session, initiatief)
        mm = Mattermost()
        await _announce(db_session, mm, initiatief, activiteit)

        with pytest.raises(AlreadyAnnouncedError):
            await _announce(db_session, mm, initiatief, activiteit)

        assert len(mm.messages) == 1
        # The session is still usable after the lost insert.
        assert len(await _rows(db_session, initiatief)) == 1

    async def test_two_initiatieven_can_announce_the_same_debate(
        self, db_session, initiatief, monkeypatch
    ):
        activiteit = _activiteit()
        _known(monkeypatch, activiteit)
        other = Initiatief(id=uuid.uuid4(), naam=f"Ander {uuid.uuid4().hex[:8]}")
        db_session.add(other)
        await db_session.flush()
        mm = Mattermost()

        await _announce(db_session, mm, initiatief, activiteit)
        await _announce(db_session, mm, other, activiteit)

        assert len(await _rows(db_session, other)) == 1

    @pytest.mark.parametrize(
        ("now", "stand", "promised"),
        [
            # The evening before: the reminder is still to come.
            (MORNING - timedelta(hours=10), STAND_AANGEKONDIGD, True),
            # The day itself, before and after the hour the reminder goes
            # out, and while the debate is on.
            (MORNING.replace(hour=6), STAND_HERINNERD, False),
            (MORNING, STAND_HERINNERD, False),
            (MORNING.replace(hour=17), STAND_HERINNERD, False),
        ],
    )
    async def test_a_debate_of_today_is_not_reminded_of_again(
        self, db_session, initiatief, monkeypatch, now, stand, promised
    ):
        activiteit = _activiteit()
        _known(monkeypatch, activiteit)
        await _link(db_session, initiatief)
        mm = Mattermost()

        await DebatAankondigingService(db_session, mm).announce(
            initiatief, activiteit.id, person_id=None, door=None, now=now
        )

        (row,) = await _rows(db_session, initiatief)
        assert row.stand == stand
        assert ("herinnering" in mm.messages[0][1]) is promised

    async def test_names_the_debate_channel_of_the_same_team_only(
        self, db_session, initiatief, monkeypatch
    ):
        activiteit = _activiteit()
        _known(monkeypatch, activiteit)
        same = await _link(db_session, initiatief)
        elsewhere = await _link(db_session, initiatief, team=OTHER_TEAM)
        db_session.add(
            DebatSessie(
                activiteit_id=activiteit.id,
                onderwerp=activiteit.onderwerp,
                team_id=TEAM,
                channel_id=uuid.uuid4().hex[:26],
                channel_name="debat-digitaal-6-okt",
            )
        )
        await db_session.flush()
        mm = Mattermost()

        await _announce(db_session, mm, initiatief, activiteit)

        by_channel = {m[0]: m[1] for m in mm.messages}
        assert "~debat-digitaal-6-okt" in by_channel[same.channel_id]
        assert "~debat-" not in by_channel[elsewhere.channel_id]


@pytest.mark.asyncio
class TestTick:
    async def _tick(self, db_session, mm, now=MORNING):
        return await DebatAankondigingService(db_session, mm).tick(now)

    async def test_reminds_once_on_the_day_itself(
        self, db_session, initiatief, monkeypatch
    ):
        activiteit = _activiteit()
        _known(monkeypatch, activiteit)
        link = await _link(db_session, initiatief)
        row = await _row(db_session, initiatief, activiteit)
        mm = Mattermost()

        result = await self._tick(db_session, mm)
        again = await self._tick(db_session, mm)

        assert result.herinnerd == 1
        assert again.herinnerd == 0
        assert [(m[0], m[2]) for m in mm.messages] == [(link.channel_id, None)]
        assert "Vandaag om 16:30" in mm.messages[0][1]
        assert row.stand == STAND_HERINNERD

    async def test_the_reminder_uses_the_time_as_it_is_now(
        self, db_session, initiatief, monkeypatch
    ):
        activiteit = _activiteit()
        later = replace(
            activiteit,
            aanvang=activiteit.aanvang + timedelta(hours=1),
            einde=activiteit.einde + timedelta(hours=1),
        )
        _known(monkeypatch, later)
        await _link(db_session, initiatief)
        row = await _row(db_session, initiatief, activiteit)
        mm = Mattermost()

        await self._tick(db_session, mm)

        assert "Vandaag om 17:30" in mm.messages[0][1]
        assert row.aanvang == later.aanvang

    async def test_nothing_before_the_morning(
        self, db_session, initiatief, monkeypatch
    ):
        activiteit = _activiteit()
        asked = _known(monkeypatch, activiteit)
        await _link(db_session, initiatief)
        row = await _row(db_session, initiatief, activiteit)
        mm = Mattermost()

        await self._tick(db_session, mm, MORNING.replace(hour=6, minute=59))

        assert asked == []
        assert mm.messages == []
        assert row.stand == STAND_AANGEKONDIGD

    async def test_a_debate_of_tomorrow_is_left_alone(
        self, db_session, initiatief, monkeypatch
    ):
        activiteit = _activiteit()
        asked = _known(monkeypatch, activiteit)
        await _link(db_session, initiatief)
        row = await _row(db_session, initiatief, activiteit)
        mm = Mattermost()

        await self._tick(db_session, mm, MORNING - timedelta(days=1))

        assert asked == []
        assert mm.messages == []
        assert row.stand == STAND_AANGEKONDIGD

    async def test_a_cancelled_debate_is_called_off(
        self, db_session, initiatief, monkeypatch
    ):
        activiteit = _activiteit()
        _known(monkeypatch, replace(activiteit, status="Geannuleerd"))
        await _link(db_session, initiatief)
        row = await _row(db_session, initiatief, activiteit)
        mm = Mattermost()

        result = await self._tick(db_session, mm)

        assert result.afgelast == 1
        assert result.herinnerd == 0
        (bericht,) = mm.messages
        assert "**Digitaliserende overheid** van dinsdag 6 oktober, 16:30" in bericht[1]
        assert "is geannuleerd." in bericht[1]
        assert row.stand == STAND_AFGELAST

    async def test_a_debate_that_is_gone_is_called_off(
        self, db_session, initiatief, monkeypatch
    ):
        activiteit = _activiteit()
        _known(monkeypatch)
        await _link(db_session, initiatief)
        row = await _row(db_session, initiatief, activiteit)
        mm = Mattermost()

        await self._tick(db_session, mm)

        assert "staat niet meer op de agenda" in mm.messages[0][1]
        assert row.stand == STAND_AFGELAST

    async def test_a_moved_debate_is_followed_to_its_new_date(
        self, db_session, initiatief, monkeypatch
    ):
        activiteit = _activiteit()
        new_start = activiteit.aanvang + timedelta(days=7)
        successor = _activiteit(
            nummer="2099A09999",
            aanvang=new_start,
            einde=new_start + timedelta(hours=3),
            vervangen_vanuit=(activiteit.id,),
        )
        moved = replace(activiteit, status="Verplaatst", vervangen_door=(successor.id,))
        _known(monkeypatch, moved, successor)
        await _link(db_session, initiatief)
        row = await _row(db_session, initiatief, activiteit)
        mm = Mattermost()

        result = await self._tick(db_session, mm)

        assert result.verzet == 1
        (bericht,) = mm.messages
        assert "is verzet naar dinsdag 13 oktober, 16:30 tot 19:30" in bericht[1]
        assert "(was dinsdag 6 oktober, 16:30)" in bericht[1]
        assert row.activiteit_id == successor.id
        assert row.activiteit_nummer == "2099A09999"
        assert row.aanvang == new_start
        assert row.stand == STAND_AANGEKONDIGD

        # And on the new day the reminder follows.
        later = await self._tick(db_session, mm, MORNING + timedelta(days=7))

        assert later.herinnerd == 1
        assert row.stand == STAND_HERINNERD

    async def test_a_move_to_a_date_already_announced_says_nothing_twice(
        self, db_session, initiatief, monkeypatch
    ):
        activiteit = _activiteit()
        new_start = activiteit.aanvang + timedelta(days=7)
        successor = _activiteit(aanvang=new_start, einde=new_start + timedelta(hours=3))
        moved = replace(activiteit, status="Verplaatst", vervangen_door=(successor.id,))
        _known(monkeypatch, moved, successor)
        await _link(db_session, initiatief)
        row = await _row(db_session, initiatief, activiteit)
        new_row = await _row(db_session, initiatief, successor)
        mm = Mattermost()

        await self._tick(db_session, mm)

        assert mm.messages == []
        assert row.stand == STAND_AFGELAST
        assert new_row.stand == STAND_AANGEKONDIGD

    async def test_a_move_without_a_new_date_is_called_off(
        self, db_session, initiatief, monkeypatch
    ):
        activiteit = _activiteit()
        _known(monkeypatch, replace(activiteit, status="Verplaatst"))
        await _link(db_session, initiatief)
        row = await _row(db_session, initiatief, activiteit)
        mm = Mattermost()

        result = await self._tick(db_session, mm)

        assert result.afgelast == 1
        assert "is verplaatst. Een nieuwe datum is er nog niet." in mm.messages[0][1]
        assert row.stand == STAND_AFGELAST

    async def test_a_later_day_on_the_same_activiteit_is_followed(
        self, db_session, initiatief, monkeypatch
    ):
        activiteit = _activiteit()
        later = replace(
            activiteit,
            aanvang=activiteit.aanvang + timedelta(days=2),
            einde=activiteit.einde + timedelta(days=2),
        )
        _known(monkeypatch, later)
        await _link(db_session, initiatief)
        row = await _row(db_session, initiatief, activiteit)
        mm = Mattermost()

        result = await self._tick(db_session, mm)

        assert result.verzet == 1
        assert result.herinnerd == 0
        assert "is verzet naar donderdag 8 oktober" in mm.messages[0][1]
        assert row.aanvang == later.aanvang
        assert row.stand == STAND_AANGEKONDIGD

    async def test_a_debate_that_is_over_gets_no_message(
        self, db_session, initiatief, monkeypatch
    ):
        activiteit = _activiteit()
        asked = _known(monkeypatch, activiteit)
        await _link(db_session, initiatief)
        row = await _row(db_session, initiatief, activiteit)
        mm = Mattermost()

        await self._tick(db_session, mm, MORNING + timedelta(days=3))

        assert asked == []
        assert mm.messages == []
        assert row.stand == STAND_VOORBIJ

    async def test_without_a_channel_the_row_still_moves_on(
        self, db_session, initiatief, monkeypatch
    ):
        activiteit = _activiteit()
        _known(monkeypatch, activiteit)
        row = await _row(db_session, initiatief, activiteit)
        mm = Mattermost()

        await self._tick(db_session, mm)

        assert mm.messages == []
        assert row.stand == STAND_HERINNERD

    async def test_an_unreadable_agenda_says_nothing_and_counts_as_a_failure(
        self, db_session, initiatief, monkeypatch
    ):
        activiteit = _activiteit()
        _known(monkeypatch, error=TkApiError("stuk"))
        await _link(db_session, initiatief)
        await _row(db_session, initiatief, activiteit)
        mm = Mattermost()

        result = await self._tick(db_session, mm)

        assert result.fouten == 1
        assert result.herinnerd == 0
        assert mm.messages == []


@pytest.fixture
async def real_session(_test_engine):
    """A session that really commits and really rolls back.

    `db_session` joins an outer transaction, so the rollback after a failed
    row undoes the whole test. What a failed round leaves behind can only
    be seen with rows that are really there.
    """
    session = AsyncSession(bind=_test_engine, expire_on_commit=False)
    made: list[uuid.UUID] = []
    try:
        yield session, made
    finally:
        await session.rollback()
        for initiatief_id in made:
            await session.execute(
                delete(MattermostChannelLink).where(
                    MattermostChannelLink.scope_id == initiatief_id
                )
            )
            # The aankondigingen go with the initiatief.
            await session.execute(
                delete(Initiatief).where(Initiatief.id == initiatief_id)
            )
        await session.commit()
        await session.close()


@pytest.mark.asyncio
class TestFailedRound:
    """One test, on purpose: a round reads every open row there is, so two
    tests that commit rows would find each other's."""

    async def test_a_failed_row_waits_and_does_not_hold_up_the_next(
        self, real_session, _test_engine, monkeypatch
    ):
        session, made = real_session
        initiatief = Initiatief(
            id=uuid.uuid4(), naam=f"Initiatief {uuid.uuid4().hex[:8]}"
        )
        session.add(initiatief)
        made.append(initiatief.id)
        await session.flush()
        link = await _link(session, initiatief)
        # A century on, so no row of another test is on this day.
        start = datetime(2199, 3, 5, 14, 0, tzinfo=AMS)
        morning = start.replace(hour=9)
        first = _activiteit(
            onderwerp="Eerste", aanvang=start, einde=start + timedelta(hours=2)
        )
        second = _activiteit(
            onderwerp="Tweede",
            aanvang=start + timedelta(hours=1),
            einde=start + timedelta(hours=3),
        )
        # The ids and not the rows: a rollback expires what was loaded,
        # and reading an expired row outside the session's own calls fails.
        row_one = (await _row(session, initiatief, first)).id
        row_two = (await _row(session, initiatief, second)).id
        channel_id = link.channel_id
        await session.commit()

        unreadable = {first.id}
        known = {first.id: first, second.id: second}

        async def fake_fetch(activiteit_id, client, base_url=None):
            if activiteit_id in unreadable:
                raise TkApiError("stuk")
            return known.get(activiteit_id)

        monkeypatch.setattr(mod, "fetch_activiteit", fake_fetch)
        mm = Mattermost()

        async def stand(row_id: uuid.UUID) -> str:
            # A session of its own: what counts is what was committed.
            async with AsyncSession(bind=_test_engine) as other:
                return (
                    await other.execute(
                        select(DebatAankondiging.stand).where(
                            DebatAankondiging.id == row_id
                        )
                    )
                ).scalar_one()

        def ours() -> list[str]:
            return [m[1] for m in mm.messages if m[0] == channel_id]

        # The agenda fails for the first, Mattermost refuses the second.
        mm.post_ok = False
        await DebatAankondigingService(session, mm).tick(morning)

        assert ours() == []
        assert await stand(row_one) == STAND_AANGEKONDIGD
        assert await stand(row_two) == STAND_AANGEKONDIGD

        # Mattermost is back. The first still fails and the second goes out.
        mm.post_ok = True
        await DebatAankondigingService(session, mm).tick(morning)

        assert len(ours()) == 1
        assert "Tweede" in ours()[0]
        assert await stand(row_one) == STAND_AANGEKONDIGD
        assert await stand(row_two) == STAND_HERINNERD

        # The agenda is back: the first goes out, the second not again.
        unreadable.clear()
        await DebatAankondigingService(session, mm).tick(morning)

        assert len(ours()) == 2
        assert "Eerste" in ours()[1]
        assert await stand(row_one) == STAND_HERINNERD


@pytest.mark.asyncio
class TestRoutes:
    @pytest.fixture
    def mattermost(self, monkeypatch):
        mm = Mattermost()
        monkeypatch.setattr(mod, "MattermostService", lambda session: mm)
        return mm

    async def test_announce_list_and_take_off(
        self, client, db_session, initiatief, monkeypatch, mattermost
    ):
        activiteit = _activiteit()
        _known(monkeypatch, activiteit)
        await _link(db_session, initiatief)
        url = f"/api/initiatieven/{initiatief.id}/debatten"

        created = await client.post(url, json={"activiteit_id": activiteit.id})

        assert created.status_code == 201, created.text
        body = created.json()
        assert body["onderwerp"] == "Digitaliserende overheid"
        assert body["gepost_in"] == 1
        assert body["stand"] == STAND_AANGEKONDIGD
        assert body["agenda_url"].endswith("details?id=2099A05428")
        assert len(mattermost.messages) == 1

        listed = await client.get(url)
        assert [d["id"] for d in listed.json()] == [body["id"]]
        assert listed.json()[0]["gepost_in"] is None

        deleted = await client.delete(f"{url}/{body['id']}")
        assert deleted.status_code == 204
        assert (await client.get(url)).json() == []

    async def test_announcing_twice_is_a_conflict(
        self, client, initiatief, monkeypatch, mattermost
    ):
        activiteit = _activiteit()
        _known(monkeypatch, activiteit)
        url = f"/api/initiatieven/{initiatief.id}/debatten"
        await client.post(url, json={"activiteit_id": activiteit.id})

        resp = await client.post(url, json={"activiteit_id": activiteit.id})

        assert resp.status_code == 409
        assert resp.json()["detail"] == "Dit debat is al aangekondigd."

    async def test_a_cancelled_meeting_is_a_conflict_with_the_reason(
        self, client, initiatief, monkeypatch, mattermost
    ):
        activiteit = _activiteit(status="Geannuleerd")
        _known(monkeypatch, activiteit)

        resp = await client.post(
            f"/api/initiatieven/{initiatief.id}/debatten",
            json={"activiteit_id": activiteit.id},
        )

        assert resp.status_code == 409
        assert resp.json()["detail"] == "Deze vergadering is geannuleerd."

    async def test_an_unreadable_agenda_is_a_503(
        self, client, initiatief, monkeypatch, mattermost
    ):
        _known(monkeypatch, error=TkApiError("stuk"))

        resp = await client.post(
            f"/api/initiatieven/{initiatief.id}/debatten",
            json={"activiteit_id": str(uuid.uuid4())},
        )

        assert resp.status_code == 503

    async def test_unknown_initiatief_is_a_404(self, client, mattermost):
        resp = await client.get(f"/api/initiatieven/{uuid.uuid4()}/debatten")

        assert resp.status_code == 404

    async def test_a_debate_of_another_initiatief_cannot_be_taken_off(
        self, client, db_session, initiatief, mattermost
    ):
        other = Initiatief(id=uuid.uuid4(), naam=f"Ander {uuid.uuid4().hex[:8]}")
        db_session.add(other)
        await db_session.flush()
        row = await _row(db_session, other, _activiteit())

        resp = await client.delete(
            f"/api/initiatieven/{initiatief.id}/debatten/{row.id}"
        )

        assert resp.status_code == 404
        assert len(await _rows(db_session, other)) == 1

    async def test_what_is_long_over_is_not_listed(
        self, client, db_session, initiatief, mattermost
    ):
        old = datetime.now(UTC) - timedelta(days=3)
        await _row(
            db_session,
            initiatief,
            _activiteit(aanvang=old, einde=old + timedelta(hours=2)),
        )
        coming = await _row(db_session, initiatief, _activiteit())

        resp = await client.get(f"/api/initiatieven/{initiatief.id}/debatten")

        assert [d["id"] for d in resp.json()] == [str(coming.id)]


async def _member(db_session, initiatief, rol: str):
    person = await make_person(db_session, f"Lid {uuid.uuid4().hex[:6]}")
    db_session.add(
        ResourcePermission(
            person_id=person.id,
            resource_type="initiatief",
            resource_id=initiatief.id,
            rol=rol,
        )
    )
    await db_session.flush()
    return person


@pytest.mark.asyncio
class TestWhoMayAnnounce:
    """An announcement makes the bot post in every channel of the
    initiatief. Seeing the initiatief is not enough for that."""

    @pytest.fixture
    def mattermost(self, monkeypatch):
        mm = Mattermost()
        monkeypatch.setattr(mod, "MattermostService", lambda session: mm)
        return mm

    async def test_a_viewer_sees_the_list_and_cannot_announce(
        self, db_session, initiatief, monkeypatch, mattermost
    ):
        activiteit = _activiteit()
        _known(monkeypatch, activiteit)
        await _link(db_session, initiatief)
        row = await _row(db_session, initiatief, _activiteit())
        viewer = await _member(db_session, initiatief, "viewer")
        url = f"/api/initiatieven/{initiatief.id}/debatten"

        async with client_as(db_session, viewer) as client:
            listed = await client.get(url)
            created = await client.post(url, json={"activiteit_id": activiteit.id})
            deleted = await client.delete(f"{url}/{row.id}")

        assert [d["id"] for d in listed.json()] == [str(row.id)]
        assert created.status_code == 403
        assert deleted.status_code == 403
        assert mattermost.messages == []
        assert [r.id for r in await _rows(db_session, initiatief)] == [row.id]

    async def test_a_contributor_can_announce_and_take_off(
        self, db_session, initiatief, monkeypatch, mattermost
    ):
        activiteit = _activiteit()
        _known(monkeypatch, activiteit)
        await _link(db_session, initiatief)
        contributor = await _member(db_session, initiatief, "contributor")
        url = f"/api/initiatieven/{initiatief.id}/debatten"

        async with client_as(db_session, contributor) as client:
            created = await client.post(url, json={"activiteit_id": activiteit.id})
            deleted = await client.delete(f"{url}/{created.json()['id']}")

        assert created.status_code == 201, created.text
        assert deleted.status_code == 204
        # Who announced it is in the message.
        assert f"door {contributor.naam}" in mattermost.messages[0][1]

    async def test_an_outsider_does_not_learn_the_initiatief_exists(
        self, db_session, initiatief, monkeypatch, mattermost
    ):
        activiteit = _activiteit()
        _known(monkeypatch, activiteit)
        outsider = await make_person(db_session, f"Buiten {uuid.uuid4().hex[:6]}")
        url = f"/api/initiatieven/{initiatief.id}/debatten"

        async with client_as(db_session, outsider) as client:
            listed = await client.get(url)
            created = await client.post(url, json={"activiteit_id": activiteit.id})

        assert listed.status_code == 404
        assert created.status_code == 404
        assert mattermost.messages == []


class TestIsAnnounceable:
    EXTRA = {
        "activiteit_id": "cc83dcc6-44ac-46ee-b56d-87371a47f94f",
        "categorie": "vergadering_vooruit",
        "soort": "Agenda procedurevergadering",
        "activiteit_datum": "2026-10-14",
        "activiteit_status": "Gepland",
    }
    TODAY = date(2026, 10, 9)

    def test_an_upcoming_meeting_gets_the_button(self):
        assert is_announceable(self.EXTRA, self.TODAY) is True

    def test_a_convocatie_too(self):
        extra = {**self.EXTRA, "soort": "Convocatie commissieactiviteit"}
        assert is_announceable(extra, self.TODAY) is True

    def test_today_still_counts_and_yesterday_does_not(self):
        assert is_announceable(self.EXTRA, date(2026, 10, 14)) is True
        assert is_announceable(self.EXTRA, date(2026, 10, 15)) is False

    def test_without_a_meeting_there_is_nothing_to_list(self):
        assert (
            is_announceable({**self.EXTRA, "activiteit_id": None}, self.TODAY) is False
        )

    def test_a_deadline_for_written_input_is_not_a_meeting(self):
        extra = {**self.EXTRA, "soort": "Convocatie inbreng"}
        assert is_announceable(extra, self.TODAY) is False

    def test_a_report_of_a_meeting_that_was_gets_no_button(self):
        extra = {**self.EXTRA, "categorie": "vergadering_terug"}
        assert is_announceable(extra, self.TODAY) is False

    @pytest.mark.parametrize("status", ["Geannuleerd", "Verplaatst"])
    def test_a_meeting_that_is_off_gets_no_button(self, status):
        extra = {**self.EXTRA, "activiteit_status": status}
        assert is_announceable(extra, self.TODAY) is False

    def test_no_extra_at_all(self):
        assert is_announceable(None, self.TODAY) is False


POST = "post000000000000000000aaaa"
USER = "user000000000000000000aaaa"


@pytest.mark.asyncio
class TestAnnounceFromAlert:
    """The megaphone under an alert: on the list, and a reply in the thread."""

    async def _press(self, db_session, mm, link, activiteit, now=None):
        return await DebatAankondigingService(db_session, mm).announce_from_alert(
            extra={"activiteit_id": activiteit.id},
            channel_id=link.channel_id,
            post_id=POST,
            mattermost_user_id=USER,
            now=now,
        )

    async def test_lists_the_meeting_and_answers_in_the_thread(
        self, db_session, initiatief, monkeypatch
    ):
        activiteit = _activiteit()
        _known(monkeypatch, activiteit)
        link = await _link(db_session, initiatief)
        other = await _link(db_session, initiatief)
        mm = Mattermost()

        outcome = await self._press(db_session, mm, link, activiteit)

        assert outcome == "listed"
        (row,) = await _rows(db_session, initiatief)
        assert row.activiteit_id == activiteit.id
        assert row.stand == STAND_AANGEKONDIGD
        # One reply under the alert, and nothing new in any channel: the
        # alert is the announcement.
        ((channel, tekst, root),) = mm.messages
        assert (channel, root) == (link.channel_id, POST)
        assert other.channel_id != channel
        assert f"op de lijst van **{initiatief.naam}**" in tekst
        assert "Op de ochtend van dinsdag 6 oktober" in tekst
        assert "begint om 16:30" in tekst

    async def test_the_reminder_then_follows_on_the_day(
        self, db_session, initiatief, monkeypatch
    ):
        activiteit = _activiteit()
        _known(monkeypatch, activiteit)
        link = await _link(db_session, initiatief)
        mm = Mattermost()
        await self._press(db_session, mm, link, activiteit)

        result = await DebatAankondigingService(db_session, mm).tick(MORNING)

        assert result.herinnerd == 1
        assert "Vandaag om 16:30" in mm.messages[-1][1]
        assert mm.messages[-1][2] is None

    async def test_a_second_press_says_it_is_there_already(
        self, db_session, initiatief, monkeypatch
    ):
        activiteit = _activiteit()
        _known(monkeypatch, activiteit)
        link = await _link(db_session, initiatief)
        mm = Mattermost()
        await self._press(db_session, mm, link, activiteit)

        outcome = await self._press(db_session, mm, link, activiteit)

        assert outcome == "exists"
        assert "staat al op de lijst" in mm.messages[-1][1]
        assert len(await _rows(db_session, initiatief)) == 1

    async def test_a_meeting_of_today_promises_no_reminder(
        self, db_session, initiatief, monkeypatch
    ):
        activiteit = _activiteit()
        _known(monkeypatch, activiteit)
        link = await _link(db_session, initiatief)
        mm = Mattermost()

        await self._press(db_session, mm, link, activiteit, now=MORNING)

        (row,) = await _rows(db_session, initiatief)
        assert row.stand == STAND_HERINNERD
        assert "herinnering" not in mm.messages[0][1]

    async def test_a_cancelled_meeting_is_answered_with_the_reason(
        self, db_session, initiatief, monkeypatch
    ):
        activiteit = _activiteit(status="Geannuleerd")
        _known(monkeypatch, activiteit)
        link = await _link(db_session, initiatief)
        mm = Mattermost()

        outcome = await self._press(db_session, mm, link, activiteit)

        assert outcome == "refused"
        assert mm.messages[0][1] == "Deze vergadering is geannuleerd."
        assert mm.messages[0][2] == POST

    async def test_an_alert_without_a_meeting_is_answered(self, db_session, initiatief):
        link = await _link(db_session, initiatief)
        mm = Mattermost()

        outcome = await DebatAankondigingService(db_session, mm).announce_from_alert(
            extra={}, channel_id=link.channel_id, post_id=POST, mattermost_user_id=USER
        )

        assert outcome == "refused"
        assert "geen vergadering bekend" in mm.messages[0][1]

    async def test_a_channel_of_a_lead_has_no_list(
        self, db_session, initiatief, monkeypatch
    ):
        activiteit = _activiteit()
        _known(monkeypatch, activiteit)
        link = await _link(db_session, initiatief, scope_type="lead")
        mm = Mattermost()

        outcome = await self._press(db_session, mm, link, activiteit)

        assert outcome == "refused"
        assert "hangt niet aan een initiatief" in mm.messages[0][1]
        assert await _rows(db_session, initiatief) == []


@pytest.mark.asyncio
class TestMegaphoneUnderTheAlert:
    async def _post_alert(self, scope_type="initiatief", **extra) -> list[str]:
        from tests.test_wegklikken import (
            TestPostAlertLegtVast,
            _abonnement,
            _Mattermost,
            _Sessie,
        )
        from tests.test_wegklikken import _item as alert_item

        mm = _Mattermost(post_id="post-abc")
        abonnement = _abonnement()
        abonnement.scope_type = scope_type
        svc = TestPostAlertLegtVast()._svc_met_kanaal(mm, _Sessie(), abonnement)
        assert await svc.post_alert(alert_item(relevantie_score=85, **extra)) == 1
        return [emoji for _, emoji in mm.reacties]

    VERGADERING = {
        "categorie": "vergadering_vooruit",
        "soort": "Agenda procedurevergadering",
        "activiteit_id": str(uuid.uuid4()),
        "activiteit_datum": "2099-10-14",
        "activiteit_status": "Gepland",
    }

    async def test_an_agenda_of_an_upcoming_meeting_gets_it(self):
        assert await self._post_alert(**self.VERGADERING) == [
            "x",
            "eyes",
            REACTIE_AANKONDIGEN,
        ]

    async def test_a_brief_does_not(self):
        reactions = await self._post_alert(categorie="brief", soort="Brief regering")
        assert reactions == ["x", "eyes"]

    async def test_a_channel_of_a_lead_does_not(self):
        reactions = await self._post_alert(scope_type="lead", **self.VERGADERING)
        assert reactions == ["x", "eyes"]


@pytest.mark.asyncio
class TestReactionReachesTheService:
    async def _react(self, db_session, monkeypatch, *, emoji, post_id, user=USER):
        from contextlib import asynccontextmanager

        from bouwmeester.services import mattermost_websocket_service as ws_mod

        calls: list[dict] = []

        class FakeService:
            def __init__(self, session):
                pass

            async def announce_from_alert(self, **kwargs):
                calls.append(kwargs)
                return "listed"

            async def close(self):
                pass

        monkeypatch.setattr(mod, "DebatAankondigingService", FakeService)

        @asynccontextmanager
        async def _session():
            yield db_session

        monkeypatch.setattr(ws_mod, "async_session", _session)
        svc = ws_mod.MattermostWebsocketService.__new__(
            ws_mod.MattermostWebsocketService
        )
        svc._bot_user_id = "bot0000000000000000000aaaa"
        await svc._dispatch_reaction_added(
            {
                "event": "reaction_added",
                "data": {
                    "reaction": {
                        "user_id": user,
                        "post_id": post_id,
                        "emoji_name": emoji,
                    }
                },
            }
        )
        return calls

    async def _alert(self, db_session) -> tuple[str, str, str]:
        from bouwmeester.models.parlementair_alert_post import ParlementairAlertPost
        from tests.test_debat_kanaal import _item

        activiteit_id = str(uuid.uuid4())
        item = await _item(db_session, activiteit_id)
        post_id = f"post{uuid.uuid4().hex[:22]}"
        channel_id = uuid.uuid4().hex[:26]
        db_session.add(
            ParlementairAlertPost(
                parlementair_item_id=item.id, channel_id=channel_id, post_id=post_id
            )
        )
        await db_session.flush()
        return activiteit_id, channel_id, post_id

    async def test_the_megaphone_on_an_alert_reaches_the_service(
        self, db_session, monkeypatch
    ):
        activiteit_id, channel_id, post_id = await self._alert(db_session)

        calls = await self._react(
            db_session, monkeypatch, emoji=REACTIE_AANKONDIGEN, post_id=post_id
        )

        assert calls == [
            {
                "extra": {"activiteit_id": activiteit_id},
                "channel_id": channel_id,
                "post_id": post_id,
                "mattermost_user_id": USER,
            }
        ]

    async def test_another_emoji_does_not(self, db_session, monkeypatch):
        _, _, post_id = await self._alert(db_session)

        calls = await self._react(
            db_session, monkeypatch, emoji="thumbsup", post_id=post_id
        )

        assert calls == []

    async def test_the_megaphone_on_another_post_does_not(
        self, db_session, monkeypatch
    ):
        calls = await self._react(
            db_session,
            monkeypatch,
            emoji=REACTIE_AANKONDIGEN,
            post_id="post000000000000000000zzzz",
        )

        assert calls == []

    async def test_the_megaphone_the_bot_places_itself_does_nothing(
        self, db_session, monkeypatch
    ):
        _, _, post_id = await self._alert(db_session)

        calls = await self._react(
            db_session,
            monkeypatch,
            emoji=REACTIE_AANKONDIGEN,
            post_id=post_id,
            user="bot0000000000000000000aaaa",
        )

        assert calls == []
