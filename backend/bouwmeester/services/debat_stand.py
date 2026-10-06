"""Where a debate stands right now, as far as Debat Direct's agenda says.

For the debates page: is this one running, and since when. Read from the
agenda of today alone, which is one call for all debates together. The
agenda says when a debate started and ended; it does not carry the events,
so a break within a debate is not in it.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx

from bouwmeester.services import debat_direct as dd
from bouwmeester.services.debat_kanaal_service import AMSTERDAM
from bouwmeester.services.tk_activiteit import Activiteit

logger = logging.getLogger(__name__)

STAND_NIET_BEGONNEN = "niet_begonnen"
STAND_BEZIG = "bezig"
STAND_GESCHORST = "geschorst"
STAND_AFGELOPEN = "afgelopen"

# A debate in one of these is on now.
STAND_NU = (STAND_BEZIG, STAND_GESCHORST)

# How long one reading of the agenda is used. The page refetches every
# minute for every person who has it open; this makes that one call to
# Debat Direct per half minute, whatever the number of people.
CACHE_SECONDS = 30.0
# The page waits for this, so it is short: a list without the marks is
# better than a list that takes a quarter of a minute.
_HTTP_TIMEOUT = 5.0


@dataclass(frozen=True)
class Stand:
    stand: str
    # When the first part started, once it has.
    begonnen_om: datetime | None = None


def stand_of(parts: Collection[dd.DdDebat]) -> Stand | None:
    """Where a debate stands, from its parts on Debat Direct.

    ``None`` without parts: Debat Direct does not know the debate, which
    says nothing about it.

    Debat Direct cuts a plenary debate in two around a break. A part that
    ended while a later one is still to start is that break. The later part
    usually only appears when it starts, so most of the time the break
    reads as ended here; whoever follows the debate knows better, from its
    events.
    """
    if not parts:
        return None
    started = [p.started_at for p in parts if p.started_at is not None]
    begonnen_om = min(started) if started else None
    running = [p for p in parts if p.started_at is not None and p.ended_at is None]
    if running:
        return Stand(STAND_BEZIG, begonnen_om)
    ended = [p for p in parts if p.ended_at is not None]
    if len(ended) == len(parts):
        return Stand(STAND_AFGELOPEN, begonnen_om)
    if ended:
        return Stand(STAND_GESCHORST, begonnen_om)
    return Stand(STAND_NIET_BEGONNEN)


def parts_of(
    activiteit: Activiteit, agenda: list[dd.DdDebat], known_ids: Collection[str] = ()
) -> list[dd.DdDebat]:
    """The parts of this activiteit in the agenda.

    The ids the timeline already found go first. Matching compares with the
    planned start, and Debat Direct replaces that with the real one once a
    debate runs: a debate that began two hours late no longer matches
    itself, and the timeline knew which one it was before that.
    """
    known = [debat for debat in agenda if debat.id in known_ids]
    if known:
        return known
    if activiteit.aanvang is None:
        # Without a start only the subject is left to go on, and the same
        # subject comes back on other days.
        return []
    return dd.match_debates(activiteit, agenda)


class AgendaCache:
    """Today's agenda of Debat Direct, read at most once per half minute."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = asyncio.Lock()
        self._day: date | None = None
        self._read_at = 0.0
        self._agenda: list[dd.DdDebat] | None = None

    def clear(self) -> None:
        self._day = None
        self._agenda = None

    def _fresh(self, day: date) -> bool:
        return self._day == day and self._clock() - self._read_at < CACHE_SECONDS

    async def today(self, now: datetime | None = None) -> list[dd.DdDebat] | None:
        """The agenda of today, or ``None`` if Debat Direct cannot be read.

        A failure is remembered as long as an answer: a Debat Direct that is
        down is not asked again by every request, each waiting for the
        timeout.
        """
        day = (now or datetime.now(UTC)).astimezone(AMSTERDAM).date()
        if self._fresh(day):
            return self._agenda
        async with self._lock:
            # Whoever waited for the lock finds what the first one read.
            if self._fresh(day):
                return self._agenda
            try:
                async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                    agenda: list[dd.DdDebat] | None = await dd.fetch_agenda(client, day)
            except dd.DebatDirectError:
                logger.warning("Agenda van Debat Direct niet te lezen", exc_info=True)
                agenda = None
            self._day = day
            self._read_at = self._clock()
            self._agenda = agenda
            return agenda


AGENDA = AgendaCache()
