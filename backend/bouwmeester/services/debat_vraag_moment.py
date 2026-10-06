"""When in a turn a question was asked, and the link to that moment.

A turn at speaking can take ten minutes, and the question to the
bewindspersoon is often in its last one. The subtitle lines carry the moment
each was spoken, so the line a quote begins in says when the question was
asked. Nothing in here reads or writes anything.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import quote, unquote

from bouwmeester.services.debat_kanaal_service import AMSTERDAM

# How far before the question the link starts playing. Someone who clicks
# wants to hear the question begin, not its second word, and a subtitle line
# is timed a moment after the sound it belongs to.
LEAD_IN = timedelta(seconds=5)

# What may go into a message as a link.
SAFE_URL = re.compile(r"^https://[^\s()<>\[\]]+$")

# The player of Debat Direct does not look an event up. It reads the
# timestamp at the end of the `event` parameter and seeks to it, so any
# moment can be linked to, not only the start of a turn. This is the
# expression its script uses, less the capture.
_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})$"
)
_EVENT = re.compile(r"(?<=[?&])event=([^&#]*)")
# How the feed writes a moment: local time, offset without a colon.
_FEED_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


@dataclass(frozen=True)
class Line:
    """One subtitle line of a turn."""

    # When it was spoken, on the clock of the events: the subtitles are on
    # the clock of the sound, and whoever makes a `Line` has taken off how
    # much later than the events the sound is.
    start: datetime
    text: str


def _ink(text: str) -> str:
    return "".join(text.split())


def moment_of_position(
    lines: Sequence[Line], text: str, position: int
) -> datetime | None:
    """When the character at `position` of the text of a turn was spoken.

    The text of a turn is its lines joined, and how exactly (one space
    within a row, stripped and one space between rows) is not repeated
    here: a place in the text is counted in characters that are not
    whitespace, which is the same number however the lines were joined.

    ``None`` when the lines are not this text: a turn from before lines
    were kept, or a line that moved since the text was read. A moment taken
    from other words than the ones quoted would be a wrong moment that
    looks exact.
    """
    if not lines or not 0 <= position < len(text):
        return None
    inks = [_ink(line.text) for line in lines]
    if "".join(inks) != _ink(text):
        return None
    before = len(_ink(text[:position]))
    seen = 0
    for line, ink in zip(lines, inks, strict=True):
        seen += len(ink)
        if before < seen:
            return line.start
    return None


def question_url(
    turn_url: str | None, moment: datetime, turn_start: datetime
) -> str | None:
    """The link of a turn, made to open at a question asked in it.

    Everything stays as the timeline built it, site path and query; only
    the timestamp at the end of the `event` value becomes the moment of the
    question, a few seconds early and never before the turn began.
    ``None`` when the link has no such timestamp or the result is not safe
    to post: the caller then keeps the link of the turn.
    """
    if not turn_url:
        return None
    event = _EVENT.search(turn_url)
    if event is None:
        return None
    value = unquote(event.group(1))
    stamp = _TIMESTAMP.search(value)
    if stamp is None:
        return None
    at = max(moment - LEAD_IN, turn_start).astimezone(AMSTERDAM)
    # Whole seconds, as the feed has them; rounded down is a little early.
    value = value[: stamp.start()] + at.strftime(_FEED_FORMAT)
    url = turn_url[: event.start(1)] + quote(value, safe="") + turn_url[event.end(1) :]
    return url if SAFE_URL.match(url) else None
