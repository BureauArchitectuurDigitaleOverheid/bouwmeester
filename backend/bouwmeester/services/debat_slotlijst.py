"""The list of toezeggingen the chairman reads at the end of a debate.

At the end of a commissiedebat the chairman reads out what the griffier
noted: "ik heb de volgende toezeggingen genoteerd". That list is what gets
registered. It confirms the toezeggingen that were marked during the
debate, and it holds the ones that were missed: in the gold set one sure
toezegging stands only there, because the promise itself fell in a hole in
the recording.

The chairman is never read for anything else. So which of the chairman's
words are the list is decided here, by rule, before a model sees any of
them:

* the chairman says it, with the formula (`opens_closing_list`);
* near the end of the debate (`LIST_WITHIN`), and after a bewindspersoon
  answered. A list read at the start is of what was promised in an
  earlier debate;
* it is the plural, "toezeggingen", with a word of reading out or noting
  down close by. "Er zijn zeven moties ingediend" is another list, and
  "dank voor de toezegging" is no list.

The list is what the chairman says from the formula on, to the end of the
debate. A member who corrects an item, or the bewindspersoon who adds a
word, cuts the list into several turns of the chairman: in the one debate
of the gold set with a list, three items stand in three turns. What the
others say in between is not read.

Which sentence is an item, what it promises and which toezegging of the
debate it is, is for the model (`build_debat_slotlijst_prompt`). The code
then checks every answer: the quote stands in the list, it has the form of
an item (`is_listed_commitment`), and an item is one that was marked
before only when the two share their words (`match_listed`).

Pure functions, no I/O.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from bouwmeester.services.debat_toezegging import (
    MIN_SHARED,
    has_commitment_form,
    shared_subject_words,
)
from bouwmeester.services.debat_vraag_vorm import words

# Who said something, for telling the list from the rest of a debate.
CHAIRMAN = "chairman"
MEMBER = "member"
BEWINDSPERSOON = "bewindspersoon"

# How long before the end of the debate the list can begin. In the one
# debate of the gold set with a list it begins 75 seconds before the last
# words; one debate is no measure. A quarter of an hour leaves room for a
# long list, a discussion about an item and the announcement of a
# tweeminutendebat, and is short of the second term of the cabinet, where
# "de toezeggingen" are spoken of without being read out.
LIST_WITHIN = timedelta(minutes=15)
# No more of the chairman's words than this goes to the model. A list of
# ten items is about 2,500 characters.
MAX_LIST = 8000

# The words that make "toezeggingen" a list that is read out: reading,
# noting, going through, counting.
_READ_OUT = (
    r"(?:lees|leest|lezen|voorlezen|voorgelezen|voor te lezen|genoteerd|noteer"
    r"|noteren|genotuleerd|opgeschreven|doornemen|doorlopen|doorloop|langs"
    r"|opsommen|oplezen|geregistreerd|volgende|gaan we naar|komen we bij"
    r"|kom ik bij|er zijn|zijn er|heb ik|ik heb|we hebben|hebben we)"
)
# The plural, and the list words within a few words in front of or behind it.
_FORMULA = (
    re.compile(rf"\b{_READ_OUT} (?:\w+ ){{0,6}}toezeggingen\b"),
    re.compile(rf"\btoezeggingen (?:\w+ ){{0,6}}{_READ_OUT}\b"),
)
# What was promised in an earlier debate, or is still to be kept: a list
# the chairman can read at the start, and no list of this debate.
_EARLIER = re.compile(
    r"\b(?:openstaande|eerdere|vorige|vorig|oude|nagekomen|afgedane|afgedaan)"
    r"(?: \w+){0,3} toezeggingen\b"
    r"|\btoezeggingen (?:\w+ ){0,4}(?:vorige|vorig|eerdere|eerder|openstaan"
    r"|open staan|open|nagekomen|afgedaan)\b"
)
# "Er zijn geen toezeggingen gedaan": nothing to read.
_NONE = re.compile(r"\bgeen toezeggingen\b")


@dataclass(frozen=True)
class Spoken:
    """What one speaker said in a row, in the order of the debate."""

    # `CHAIRMAN`, `MEMBER` or `BEWINDSPERSOON`.
    wie: str
    start: datetime
    tekst: str


@dataclass(frozen=True)
class ClosingList:
    """The chairman's words that are the list, as one text."""

    tekst: str
    # When the chairman began it.
    start: datetime
    # Which of the `Spoken` it was made of, and where each begins in `tekst`.
    delen: tuple[tuple[int, int], ...]

    def deel_van(self, plek: int) -> int:
        """Which `Spoken` the character at `plek` of the text came from."""
        found = self.delen[0][0]
        for index, begin in self.delen:
            if begin <= plek:
                found = index
        return found


def _flat(text: str) -> str:
    return " ".join(words(text))


def opens_closing_list(text: str) -> bool:
    """Whether the chairman begins to read out the toezeggingen here.

    By the words alone: speech recognition gives no punctuation to go by.
    Where in the debate it is said is for `find_closing_list`.
    """
    flat = _flat(text)
    if "toezeggingen" not in flat or _NONE.search(flat) or _EARLIER.search(flat):
        return False
    return any(pattern.search(flat) for pattern in _FORMULA)


def find_closing_list(
    spoken: Sequence[Spoken], end: datetime | None = None
) -> ClosingList | None:
    """The list of toezeggingen in a debate that is over, or ``None``.

    `spoken` is who spoke, in order; `end` when the debate ended, and the
    start of the last of `spoken` when that is not known.

    The first turn of the chairman with the formula that begins within
    `LIST_WITHIN` of the end, with an answer of a bewindspersoon somewhere
    before it. From there on every turn of the chairman belongs to the
    list; nobody else's does.
    """
    if not spoken:
        return None
    end = end or spoken[-1].start
    answered = False
    first: int | None = None
    for index, turn in enumerate(spoken):
        if turn.wie == BEWINDSPERSOON:
            answered = True
            continue
        if (
            turn.wie == CHAIRMAN
            and answered
            and end - turn.start <= LIST_WITHIN
            and opens_closing_list(turn.tekst)
        ):
            first = index
            break
    if first is None:
        return None
    text = ""
    parts: list[tuple[int, int]] = []
    for index in range(first, len(spoken)):
        turn = spoken[index]
        said = turn.tekst.strip()
        if turn.wie != CHAIRMAN or not said:
            continue
        if len(text) + len(said) + 1 > MAX_LIST:
            break
        begin = len(text) + 1 if text else 0
        text = f"{text} {said}" if text else said
        parts.append((index, begin))
    return ClosingList(tekst=text, start=spoken[first].start, delen=tuple(parts))


# Who commits, in the third person: the chairman reads what the griffier
# wrote down about the bewindspersoon.
_WHO = (
    r"(?:de minister|de staatssecretaris|de premier|het kabinet"
    r"|de regering|de bewindspersoon|hij|zij)"
)
_COMMITS = (
    r"(?:zegt|zeggen|zegde|zal|zullen|gaat|gaan|komt|komen|stuurt|sturen"
    r"|informeert|informeren|neemt|nemen|laat|laten|doet|bezorgt|bekijkt"
    r"|onderzoekt|bespreekt)"
)
_LISTED = (
    re.compile(rf"\b{_WHO} (?:\w+ ){{0,3}}{_COMMITS}\b"),
    re.compile(rf"\b{_COMMITS} {_WHO}\b"),
    re.compile(r"\b(?:de kamer|de commissie) (?:\w+ ){0,3}(?:ontvangt|krijgt|wordt)\b"),
    re.compile(r"\btoe te (?:zeggen|sturen)\b|\btoegezegd\b"),
)


# "Dat is een toezegging aan mevrouw A": about the item before it.
_TO_WHOM = re.compile(r"\b(?:een |de )?toezegging aan(?: \w+){1,5}")


def is_listed_commitment(quote: str) -> bool:
    """Whether a quote has the form of an item of the chairman's list.

    "De minister zegt toe de Kamer voor de zomer een brief te sturen", "de
    staatssecretaris zal dat meenemen in de voortgangsrapportage", "de
    Kamer ontvangt in het voorjaar de evaluatie". Not "dat waren de
    toezeggingen", "ik dank de minister" or "er is een tweeminutendebat
    aangevraagd": the chairman says those in the same breath, and they
    promise nothing.
    """
    # Who it was promised to says "een toezegging", and promises nothing.
    flat = _TO_WHOM.sub(" ", _flat(quote))
    return any(pattern.search(flat) for pattern in _LISTED) or has_commitment_form(flat)


def match_listed(
    item: str,
    named: int | None,
    eerdere: Mapping[int, str],
    onderwerp: str = "",
    taken: frozenset[int] | set[int] = frozenset(),
) -> int | None:
    """The toezegging of this debate an item of the list is, or ``None``.

    `item` is the summary and the quote of the item together, `eerdere`
    the toezeggingen that were marked in this debate by number, each as
    its summary and quote together, `named` the number the model gave.
    `taken` are the ones another item of the list was matched to already:
    the list names every toezegging once.

    The model's number is believed when the two share `MIN_SHARED` words
    that say what they are about. Without a number from the model, or
    with one the words do not bear out, the code looks itself: the one
    toezegging that shares at least `MIN_SHARED` words with the item, and
    more than any other.

    Erring either way costs something. An item that is matched wrongly
    confirms a toezegging the chairman did not read, and is itself lost;
    an item that is not matched is stored a second time.

    Measured on the one list of the gold set, against what twelve runs
    had marked, by the quotes alone: the item that was promised nowhere
    else shares at most one word with any toezegging of the debate, in
    every run. Of the two items that repeat one, one shares two words with
    it in every run and the other in 2 of 12: that one is matched when
    the model's number or the summaries bear it out, which was so in 4 of
    the 6 runs that read the list. Asking for three words would match
    neither without the model.
    """
    if (
        named is not None
        and named in eerdere
        and named not in taken
        and len(shared_subject_words(item, eerdere[named], onderwerp)) >= MIN_SHARED
    ):
        return named
    counts = sorted(
        (
            (len(shared_subject_words(item, text, onderwerp)), number)
            for number, text in eerdere.items()
            if number not in taken
        ),
        reverse=True,
    )
    if not counts or counts[0][0] < MIN_SHARED:
        return None
    if len(counts) > 1 and counts[1][0] == counts[0][0]:
        return None
    return counts[0][1]


# "Dat is een toezegging aan mevrouw A", said behind an item.
_PROMISED_TO = re.compile(
    r"\btoezegging aan (?:de heer|meneer|mevrouw|het lid|kamerlid|de leden)"
    r" ((?:\w+ ){0,3}\w+)"
)
# What stands in front of a surname and is no name.
_PARTICLES = frozenset("van der den de ter ten te het el al la le di da du op".split())
# How far behind an item its "toezegging aan" can stand, in characters: a
# sentence that finishes the item can come in between. In the one list of
# the gold set the name ends 41 to 121 characters behind the item; this is
# twice the furthest.
PROMISED_TO_WITHIN = 240


def promised_to(after: str, leden: Sequence[str]) -> str:
    """The member the chairman names behind an item, as one of `leden`.

    `after` is the list from the end of the item up to the next item,
    `leden` the labels of the members who spoke in this debate ("Kamerlid
    A (X)"). The chairman says a surname, and the transcript often gets it
    wrong: only a name that is the surname of exactly one of the members
    is taken. Anything else is nobody, which is shown as "not known".

    Not when another item stands between the two: the model can pass over
    an item, and the name behind that one is not this one's.
    """
    flat = _flat(after[:PROMISED_TO_WITHIN])
    found = _PROMISED_TO.search(flat)
    if found is None:
        return ""
    if any(pattern.search(flat[: found.start()]) for pattern in _LISTED):
        return ""
    # The first word that is a name: "van der A" is A.
    said = next((w for w in found.group(1).split() if w not in _PARTICLES), "")
    if not said:
        return ""
    matches = set()
    for label in leden:
        name = [w for w in words(label.split("(")[0]) if w not in _PARTICLES]
        # Any part of the surname, and not the first name in front of it.
        if said in (name[1:] or name):
            matches.add(label)
    return matches.pop() if len(matches) == 1 else ""
