"""From lines of subtitle to the text of a turn, cut into messages.

Nothing in here reads or writes anything. The subtitles say what was said
and when; the events of the timeline say who had the floor from when. Put
together that is the text per turn. A message in Mattermost that grows too
tall is folded behind "Lees meer", and then the part that just came in is
the part that is hidden, so a long turn continues in a next message.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Hashable, Sequence
from datetime import datetime, timedelta

from bouwmeester.services.debat_subtitles import Cue
from bouwmeester.services.mattermost_utils import escape_mattermost_prose

# Mattermost folds a message at about 600 pixels. Counted the way
# claude-threads does (21 pixels a line, 90 characters a line, a threshold
# of 500 with margin) that is some twenty lines of running text.
MESSAGE_LIMIT = 1800
# A cut is not made before this many characters: a message of one sentence
# followed by "vervolg" reads worse than one that is a little long.
MESSAGE_MINIMUM = 500
# How much of what the chairman said goes under a suspension or the end.
CLOSING_LIMIT = 300
CLOSING_MINIMUM = 60

_SENTENCE_END = re.compile(r"[.?!…][\"'”’)]?\s")
_RUNS_ON = re.compile(r"\.\.\.\s+(?=[a-zà-ÿ])")


def place_cues[K: Hashable](
    cues: Sequence[Cue],
    turns: Sequence[tuple[K, datetime]],
    offset: timedelta = timedelta(0),
) -> list[tuple[K, Cue]]:
    """Which turn every line belongs to, going by the time alone.

    `turns` are the moments someone got the floor, oldest first, each with
    whatever the caller knows it by. A line belongs to the last turn that
    began before it did. `offset` is how much later than the event the
    sound is. A line from before the first turn belongs to nobody and is
    left out. The lines come back in order of time.

    This is a first answer. The events are seconds off, so around a change
    of speaker the voices decide again; see `debat_stemmen_service`.
    """
    placed: list[tuple[K, Cue]] = []
    index = -1
    for cue in sorted(cues, key=lambda c: c.start):
        while index + 1 < len(turns) and turns[index + 1][1] + offset <= cue.start:
            index += 1
        if index >= 0:
            placed.append((turns[index][0], cue))
    return placed


def append_text(existing: str | None, more: str) -> str:
    """Text with more of it behind it."""
    return f"{(existing or '').strip()} {more.strip()}".strip()


def text_key(text: str) -> str:
    """A short name for a text, to see later whether it is still that text.

    The text of a turn mostly grows, and then the messages that are full
    stay as they are. When a line moves to another turn it changes in the
    middle. Kept with how much of the text is in the channel, this tells
    the two apart.
    """
    return hashlib.blake2s(text.encode(), digest_size=8).hexdigest()


def split_text(
    text: str, limit: int = MESSAGE_LIMIT, minimum: int = MESSAGE_MINIMUM
) -> list[str]:
    """Cut the text of a turn into pieces that each fit a message.

    A cut falls after the last sentence that still fits, and failing that
    at the last space. Where a cut falls depends only on the text before
    it, so a text that grows keeps the cuts it had: a message that was
    full is never rewritten.
    """
    pieces: list[str] = []
    rest = text.strip()
    while len(rest) > limit:
        window = rest[: limit + 1]
        cut = 0
        for found in _SENTENCE_END.finditer(window):
            if found.end() - 1 >= minimum:
                cut = found.end() - 1
        if not cut:
            cut = window.rfind(" ")
        if cut < 1:
            cut = limit
        pieces.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest or not pieces:
        pieces.append(rest)
    return pieces


def fit_messages(pieces: list[str], available: int) -> list[str]:
    """No more pieces than there may be messages; the last takes the rest.

    A next message can only be started while the turn is the last thing in
    the channel. Once someone else has a message below it, text that still
    comes in has to go into what is there, tall or not.
    """
    if available < 1 or len(pieces) <= available:
        return pieces
    return [*pieces[: available - 1], " ".join(pieces[available - 1 :])]


def last_sentences(text: str, limit: int = CLOSING_LIMIT) -> str:
    """The end of a text: as many whole last sentences as fit.

    For what the chairman said before a suspension. The last sentences are
    the ones that say until when; what came before is the debate.
    """
    text = text.strip()
    if len(text) <= limit:
        return text
    window = text[-limit:]
    starts = [found.end() for found in _SENTENCE_END.finditer(window)]
    # Whole sentences, unless that leaves next to nothing: "Ja." after a
    # long sentence says less than the end of that sentence.
    if starts and len(window) - starts[0] >= CLOSING_MINIMUM:
        return window[starts[0] :].strip()
    space = window.find(" ")
    return "…" + (window[space:] if space >= 0 else window)


def render_closing(kop: str, text: str) -> str:
    """A suspension or the end, with what the chairman said to announce it."""
    words = escape_mattermost_prose(_RUNS_ON.sub(" ", last_sentences(text))).strip()
    return f"{kop}\nVoorzitter: {words}" if words else kop


def render(kop: str, piece: str, *, vervolg: bool = False) -> str:
    """One message: who and when on the first line, what was said below."""
    head = f"{kop} · vervolg" if vervolg else kop
    # The subtitles end a line that runs on with three dots and go on in
    # lower case. Read as one text, those dots are in the way.
    body = escape_mattermost_prose(_RUNS_ON.sub(" ", piece)).strip()
    return f"{head}\n{body}" if body else head
