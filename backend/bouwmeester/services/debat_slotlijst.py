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
* it is the plural, "toezeggingen", in a sentence that reads them out or
  notes them down. "Er zijn zeven moties ingediend" is another list, and
  "ik dank de minister voor de toezeggingen" is no list.

The list is what the chairman says from the formula on, to the end of the
debate. A member who corrects an item, or the bewindspersoon who adds a
word, cuts the list into several turns of the chairman: in the one debate
of the gold set with a list, three items stand in three turns. What the
others say in between is not read.

Which sentence is an item, what it promises and which toezegging of the
debate it is, is for the model (`build_debat_slotlijst_prompt`). The code
then checks every answer: the quote stands in the list, it has the form of
an item (`is_listed_commitment`), and an item is one that was marked
before only when the model says which and the two share their words
(`match_listed`).

Pure functions, no I/O.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from bouwmeester.services.debat_toezegging import (
    _MOMENT,
    _PRODUCT,
    MIN_SHARED,
    has_commitment_form,
    shared_subject_words,
)
from bouwmeester.services.debat_vraag_vorm import words

# Who said something, for telling the list from the rest of a debate.
CHAIRMAN = "chairman"
MEMBER = "member"
BEWINDSPERSOON = "bewindspersoon"

# How long before the end of the debate the list can begin, counted from
# the turn of the chairman that holds the formula. The list is by its
# nature the last thing of a debate: behind it come a correction of an
# item, the announcement of a tweeminutendebat and the closing words. In
# the one debate of the gold set with a list it begins 75 seconds before
# the last words; one debate is no measure. Half an hour, because the start
# of a turn can be minutes before the formula in it, and a list that is not
# read is lost for good: the end of the debate is looked at once. It is
# still short of the second term of the cabinet, and what the formula lets
# through there the model and the checks on its answer still have to pass.
LIST_WITHIN = timedelta(minutes=30)
# No more of the chairman's words than this goes to the model. A list of
# ten items is about 2,500 characters.
MAX_LIST = 8000

# The plural, as speech recognition writes it: also "toe zeggingen",
# "toezegging en", and "de toezeggingslijst".
_TZ = r"(?:toe ?zeggingen|toe ?zegging en|toe ?zeggingslijst|toe ?zeggingenlijst)"
_NOTED = r"(?:genoteerd|genotuleerd|opgeschreven|geregistreerd|vastgelegd)"
# The formula of reading the list out. Not the bare word with any verb next
# to it: "ik dank de minister voor de toezeggingen die we hebben gekregen"
# and "we hebben vandaag veel toezeggingen gehoord" open no list, and what
# opens one sends everything the chairman says after it to the model.
_FORMULA = tuple(
    re.compile(pattern)
    for pattern in (
        # "ik lees de toezeggingen voor", "ik lees ze zo voor, de toezeggingen"
        rf"\b(?:lees|leest|lezen) (?:\w+ ){{0,5}}{_TZ}(?: \w+){{0,4}} voor\b",
        rf"\b(?:voorlezen|voor te lezen|oplezen|opsommen|doornemen|doorlopen"
        rf"|noteren|noteer)(?: \w+){{0,6}} {_TZ}\b",
        rf"\b{_TZ}(?: \w+){{0,6}} (?:voorlezen|voor te lezen|oplezen|opsommen"
        rf"|doornemen|doorlopen|{_NOTED})\b",
        # "ik heb de volgende toezeggingen genoteerd", "genoteerd zijn de
        # toezeggingen"
        rf"\b{_NOTED}(?: \w+){{0,6}} {_TZ}\b",
        rf"\bvolgende {_TZ}\b",
        # "dan loop ik de toezeggingen met u langs", "ik neem de
        # toezeggingslijst door"
        rf"\b(?:loop|lopen|neem|nemen) (?:\w+ ){{0,4}}{_TZ}(?: \w+){{0,4}}"
        r" (?:door|langs|na)\b",
        # "dan komen we bij de toezeggingen", "dan de toezeggingen"
        rf"\b(?:gaan we naar|komen we bij|komen we tot|kom ik bij|kom ik tot|dan)"
        rf" de {_TZ}\b",
        # Counted or announced, and then summed up: "er zijn twee
        # toezeggingen gedaan. De eerste ...", "een aantal toezeggingen,
        # namelijk ...".
        rf"\b{_TZ}(?: \w+){{0,25}} (?:namelijk|de eerste|ten eerste"
        r"|eerste toezegging|toezegging een|zegt toe|toegezegd)\b",
    )
)
# What was promised in an earlier debate, or is still to be kept: a list
# the chairman can read at the start, and no list of this debate.
_EARLIER = re.compile(
    r"\b(?:openstaande|eerdere|vorige|vorig|oude|nagekomen|afgedane|afgedaan)"
    rf"(?: \w+){{0,3}} {_TZ}\b"
    rf"|\b{_TZ} (?:\w+ ){{0,4}}(?:vorige|vorig|eerdere|eerder|openstaan"
    r"|open staan|open|nagekomen|afgedaan)\b"
)
# "Er zijn geen toezeggingen gedaan": nothing to read.
_NONE = re.compile(r"\bgeen toe ?zegging")
# How far around the formula a word takes it back, in words. No further:
# "heb ik geen toezeggingen gemist" or "eerder vandaag" elsewhere in what
# the chairman says is about something else, and a transcript does not
# always say where a sentence ends.
_VETO_REACH = 10
_SENTENCE = re.compile(r"(?<=[.?!])\s+")


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


def _formula_at(text: str) -> int | None:
    """Where in a text, as its words with one space between them, the
    chairman begins to read out the toezeggingen; ``None`` when nowhere.

    The formula of reading out or noting down (`_FORMULA`), not taken
    back: "geen toezeggingen", or the toezeggingen of an earlier debate.
    Only the sentence it is in can take it back, and only within
    `_VETO_REACH` words of it.
    """
    if "zegging" not in _flat(text):
        return None

    def first(flat: str, crossing: tuple[int, ...] | None = None) -> int | None:
        for pattern in _FORMULA:
            for found in pattern.finditer(flat):
                if crossing is not None and not any(
                    found.start() < edge < found.end() for edge in crossing
                ):
                    continue
                before = flat[: found.start()].split()[-_VETO_REACH:]
                after = flat[found.end() :].split()[:_VETO_REACH]
                around = " ".join((*before, found.group(), *after))
                if not (_NONE.search(around) or _EARLIER.search(around)):
                    return found.start()
        return None

    offset = 0
    edges: list[int] = []
    for sentence in _SENTENCE.split(text):
        flat = _flat(sentence)
        if not flat:
            continue
        found = first(flat)
        if found is not None:
            return offset + found
        offset += len(flat) + 1
        edges.append(offset)
    # A formula can run over the end of a sentence the transcript made up:
    # "ik lees de. Toezeggingen voor".
    return first(_flat(text), tuple(edges[:-1]))


def opens_closing_list(text: str) -> bool:
    """Whether the chairman begins to read out the toezeggingen here.

    By the words alone (`_formula_at`). Where in the debate it is said is
    for `find_closing_list`.
    """
    return _formula_at(text) is not None


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

    The feed can cut the chairman's words in two in the middle of the
    formula. Two turns of the chairman that follow each other are
    therefore also read together, and the list then begins at the first.
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
        if turn.wie != CHAIRMAN or not answered or end - turn.start > LIST_WITHIN:
            continue
        opens = opens_closing_list(turn.tekst)
        if not opens and index + 1 < len(spoken) and spoken[index + 1].wie == CHAIRMAN:
            # Begun in this turn and finished in the next.
            begins = _formula_at(f"{turn.tekst} {spoken[index + 1].tekst}")
            opens = begins is not None and begins < len(_flat(turn.tekst))
        if opens:
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
    r"(?:zal|zullen|gaat|gaan|komt|komen|stuurt|sturen|informeert|informeren"
    r"|neemt|nemen|laat|laten|doet|bezorgt|bekijkt|onderzoekt|bespreekt)"
)
# The shapes an item has. Who commits and a verb of doing it, in either
# order; or nobody named as who does it, the way a griffier writes it down:
# "er komt voor de zomer een brief", "de Kamer ontvangt de evaluatie", "de
# Kamer wordt voor het reces geinformeerd".
_SHAPES = (
    re.compile(rf"\b{_WHO} (?:\w+ ){{0,3}}{_COMMITS}\b"),
    re.compile(rf"\b{_COMMITS} {_WHO}\b"),
    re.compile(r"\b(?:de kamer|de commissie) (?:\w+ ){0,3}(?:ontvangt|krijgt|wordt)\b"),
    re.compile(r"\b(?:ontvangt|krijgt|wordt) (?:de kamer|de commissie)\b"),
    re.compile(r"\ber (?:komt|volgt|wordt|worden|gaat)\b"),
    re.compile(r"\b(?:komt|volgt|wordt|worden|gaat) er\b"),
)
# The promise named as one: "de minister zegt toe", "toegezegd is dat".
_EXPLICIT = re.compile(
    r"\bzeg\w* (?:\w+ ){0,5}toe\b|\btoegezegd\b|\btoe te zeggen\b|\bzegde\w* toe\b"
)
# What makes a sentence of that shape a toezegging when the promise is not
# named: coming back to it, informing the Kamer, taking it along. With a
# product or a moment (`_PRODUCT`, `_MOMENT`) that is what an item holds.
# "Hij gaat nu naar een ander debat" and "de minister zal de moties van een
# oordeel voorzien" have the shape and none of this.
_DELIVERS = re.compile(
    r"\bterug\w*|\binform\w*|\bgeinformeerd\b|\bmeenemen\b|\bmeeneemt\b"
    r"|\bmee te nemen\b|\bde kamer\b|\bde commissie\b|\buitzoeken\b"
    r"|\buit te zoeken\b|\bna te gaan\b|\bnagaan\b"
)

# "Dat is een toezegging aan mevrouw A": about the item before it.
_TO_WHOM = re.compile(r"\b(?:een |de )?toezegging aan(?: \w+){1,5}")


def _has_item_shape(flat: str) -> bool:
    return bool(_EXPLICIT.search(flat)) or any(p.search(flat) for p in _SHAPES)


def is_listed_commitment(quote: str) -> bool:
    """Whether a quote has the form of an item of the chairman's list.

    "De minister zegt toe de Kamer voor de zomer een brief te sturen", "de
    staatssecretaris zal dat meenemen in de voortgangsrapportage", "de
    Kamer ontvangt in het voorjaar de evaluatie", "er komt voor de zomer
    een brief over de wachttijden". Not "dat waren de toezeggingen", "ik
    dank de minister" or "er is een tweeminutendebat aangevraagd": the
    chairman says those in the same breath, and they promise nothing.

    Either the promise is named ("zegt toe", "toegezegd"), or the sentence
    has the shape of an item and something in it that is delivered: a
    product, a moment, coming back to it or informing the Kamer. The shape
    alone is not enough: "zij gaan nu stemmen" has it.
    """
    # Who it was promised to says "een toezegging", and promises nothing.
    flat = _TO_WHOM.sub(" ", _flat(quote))
    if _EXPLICIT.search(flat):
        return True
    if not (any(p.search(flat) for p in _SHAPES) or has_commitment_form(flat)):
        return False
    return bool(_PRODUCT.search(flat) or _MOMENT.search(flat) or _DELIVERS.search(flat))


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

    It takes both: the model names the toezegging, and the two share
    `MIN_SHARED` words that say what they are about. When the model says
    the item is new, it is new. When the model names a number the words do
    not bear out, it is new too, and the code does not go looking for
    another one.

    The two mistakes do not cost the same. An item that is not matched is
    stored a second time: two replies for one toezegging. An item that is
    matched wrongly puts "bevestigd door de voorzitter", its moment and
    its member on a toezegging the chairman did not read, and is itself
    lost. Words alone make that second mistake: two toezeggingen about one
    regulation share its name and the word "regeling", six letters each.
    An earlier version let the code match by words when the model named
    nothing; on the one list of the gold set that confirmed one repeat
    more in 2 of 6 runs, and a made-up pair about one regulation was
    enough to make it confirm the wrong one.
    """
    if (
        named is not None
        and named in eerdere
        and named not in taken
        and len(shared_subject_words(item, eerdere[named], onderwerp)) >= MIN_SHARED
    ):
        return named
    return None


# "Dat is een toezegging aan mevrouw A", said behind an item.
_PROMISED_TO = re.compile(
    r"\btoezegging aan (de heer|meneer|mevrouw|het lid|kamerlid|de leden)"
    r" ((?:\w+ ){0,3}\w+)"
)
# A second member behind the first: "aan mevrouw A en de heer B".
_AND_ANOTHER = re.compile(r"\ben (?:de heer|meneer|mevrouw|het lid|kamerlid)\b")
# What stands in front of a surname and is no name.
_PARTICLES = frozenset("van der den de ter ten te het el al la le di da du op".split())
# How far behind an item its "toezegging aan" can stand, in characters: a
# sentence that finishes the item can come in between. In the one list of
# the gold set the name ends 41 to 121 characters behind the item; this is
# twice the furthest.
PROMISED_TO_WITHIN = 240


def promised_to(after: str, leden: Sequence[str]) -> str:
    """The member the chairman names behind an item, as one of `leden`.

    `after` is the list from the end of the item up to the next thing the
    model quoted, `leden` the labels of the members who spoke in this
    debate ("Kamerlid A (X)"). The chairman says a surname, and the
    transcript often gets it wrong: only a name that is the surname of
    exactly one of the members is taken. Anything else is nobody, which is
    shown as "not known".

    The name belongs to the item it directly follows. When anything with
    the shape of an item stands between the two, the name is that one's:
    the model can pass over an item, and the code can drop one.

    Two members are nobody: "aan de leden A en B", "aan mevrouw A en de
    heer B". The row has room for one name, and half is not who it was
    promised to.
    """
    flat = _flat(after[:PROMISED_TO_WITHIN])
    found = _PROMISED_TO.search(flat)
    if found is None:
        return ""
    if _has_item_shape(_TO_WHOM.sub(" ", flat[: found.start()])):
        return ""
    if found.group(1) == "de leden" or _AND_ANOTHER.search(found.group(2)):
        return ""
    # The first word that is a name: "van der A" is A.
    said = next((w for w in found.group(2).split() if w not in _PARTICLES), "")
    if not said:
        return ""
    matches = set()
    for label in leden:
        name = [w for w in words(label.split("(")[0]) if w not in _PARTICLES]
        # Any part of the surname, and not the first name in front of it.
        if said in (name[1:] or name):
            matches.add(label)
    return matches.pop() if len(matches) == 1 else ""
