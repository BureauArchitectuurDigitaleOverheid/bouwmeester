"""Which reaction on the reply of a question means what.

People who follow a debate say what became of a question with one click: a
reaction on the reply of the bot. This module is the table of those
reactions and the rule that turns the reactions on a reply into where the
question stands. The rule is here, apart from who fetches the reactions and
who writes the result, so that it can be read and tested on its own.

Pure functions, no I/O.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from bouwmeester.models.debat_markering import (
    SOORT_MOTIE,
    SOORT_VRAAG,
    STATUS_BEANTWOORD,
    STATUS_OPEN,
    STATUS_TOEGEWEZEN,
    STATUS_VERVALT,
    STATUS_VERWORPEN,
)

# The names Mattermost uses for these emoji, in its events and its API.
REACTIE_BEANTWOORD = "white_check_mark"
REACTIE_OPGEPAKT = "eyes"
REACTIE_VERVALT = "no_entry_sign"
REACTIE_GEEN_VRAAG = "x"

# The one reaction the bot puts under a new reply itself, so that there is
# something to click. It is the bot's, so it never counts as a status.
REACTIE_HINT = REACTIE_BEANTWOORD

STATUS_PER_REACTIE: dict[str, str] = {
    REACTIE_BEANTWOORD: STATUS_BEANTWOORD,
    REACTIE_OPGEPAKT: STATUS_TOEGEWEZEN,
    REACTIE_VERVALT: STATUS_VERVALT,
    REACTIE_GEEN_VRAAG: STATUS_VERWORPEN,
}

# What the reply of a question shows for each status, as (icon, words).
# The icon takes the place of the question mark in front of the question,
# the words go into the line below it. An open question has neither: that
# is what a reply looks like when it is new.
_MARKER: dict[str, tuple[str, str]] = {
    STATUS_BEANTWOORD: ("✅", "beantwoord"),
    STATUS_TOEGEWEZEN: ("👀", "opgepakt"),
    STATUS_VERVALT: ("🚫", "hoeft geen antwoord"),
    STATUS_VERWORPEN: ("❌", "geen vraag"),
}

# The same for a motie. The reactions and the statuses are those of a
# question; only the words differ, because a motie is not answered: the
# bewindspersoon gives an oordeel on it. Reading that oordeel from the
# debate is not built. Until it is, the tick says that it was given, and
# which one it was is for whoever ticks to say in the thread.
_MARKER_MOTIE: dict[str, tuple[str, str]] = {
    STATUS_BEANTWOORD: ("✅", "oordeel gegeven"),
    STATUS_TOEGEWEZEN: ("👀", "opgepakt"),
    STATUS_VERVALT: ("🚫", "hoeft geen oordeel"),
    STATUS_VERWORPEN: ("❌", "geen motie"),
}
_MARKERS: dict[str, dict[str, tuple[str, str]]] = {
    SOORT_VRAAG: _MARKER,
    SOORT_MOTIE: _MARKER_MOTIE,
}

# In the pinned message of a debate channel, so that the reactions can be
# found without the bot putting four of them under every reply.
LEGENDA = (
    "Reageer op een gemarkeerde vraag met ✅ beantwoord · 👀 ik pak dit op · "
    "🚫 hoeft geen antwoord · ❌ geen vraag. Bij een motie betekenen ze: ✅ "
    "oordeel gegeven · 👀 ik pak dit op · 🚫 hoeft geen oordeel · ❌ geen "
    "motie. De laatste reactie telt; haal je je reactie weg, dan telt ze "
    "niet meer."
)


@dataclass(frozen=True)
class Stand:
    """Where a question stands, going by the reactions on its reply."""

    status: str = STATUS_OPEN
    # Who put the reaction that decides, and when. Nobody for an open one.
    mattermost_user_id: str | None = None
    sinds: datetime | None = None


def stand_uit_reacties(reacties: Sequence[dict], bot_user_id: str) -> Stand:
    """Where a question stands, from the reactions that are on its reply now.

    The latest reaction that means something decides, whoever put it. No
    such reaction is an open question, which is also what taking the last
    one away comes to. Reactions of the bot itself are skipped: it puts one
    under every reply as something to click.

    `reacties` is the list as Mattermost gives it for a post. Going by what
    is on the post now, and not by the events as they came in, means an
    event that was missed is made up for by the next one.
    """
    beste: tuple[int, int, str, str] | None = None
    for volgorde, reactie in enumerate(reacties):
        if not isinstance(reactie, dict) or reactie.get("delete_at"):
            continue
        status = STATUS_PER_REACTIE.get(str(reactie.get("emoji_name") or ""))
        user_id = reactie.get("user_id")
        if status is None or not user_id or user_id == bot_user_id:
            continue
        try:
            moment = int(reactie.get("create_at") or 0)
        except (TypeError, ValueError):
            moment = 0
        kandidaat = (moment, volgorde, status, str(user_id))
        if beste is None or kandidaat[:2] > beste[:2]:
            beste = kandidaat
    if beste is None:
        return Stand()
    moment, _, status, user_id = beste
    sinds = datetime.fromtimestamp(moment / 1000, UTC) if moment > 0 else None
    return Stand(status=status, mattermost_user_id=user_id, sinds=sinds)


def stand_marker(
    status: str, door: str = "", soort: str = SOORT_VRAAG
) -> tuple[str, str]:
    """The icon and the few words that say where a markering stands.

    In the words of its kind: a question is "beantwoord", a motie has its
    "oordeel gegeven". A kind without words of its own gets those of a
    question.

    Two empty strings for an open question and for a status that is not
    known here. Apart and not as one string: whoever lays out the reply
    puts them in different places, and should not have to cut a string up
    to find where the icon ends.

    `door` is the name of who picked the question up, already made harmless
    for a message. It is shown for a question that is picked up only: who
    ticked off an answer matters less than who is working on one.
    """
    icoon, woorden = _MARKERS.get(soort, _MARKER).get(status, ("", ""))
    if door and status == STATUS_TOEGEWEZEN:
        woorden = f"{woorden} door {door}"
    return icoon, woorden
