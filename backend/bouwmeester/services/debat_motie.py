"""Find the moties in a turn at speaking, by rule and without a model.

A motie that is read out follows a fixed formula:

    De Kamer, gehoord de beraadslaging,
    constaterende dat ...; overwegende dat ...;
    verzoekt de regering ...,
    en gaat over tot de orde van de dag.

That formula is what the rule looks for. It costs nothing, it cannot make
anything up, and it also reads the turns the model is not asked about. On
the three debates the rule was made on it found all 9 moties that were
read out and marked nothing else as one; see `scripts/debat_eval` for the
numbers on the debate that was kept apart.

The transcript is speech recognition, so no part of the formula is relied
on alone. In those debates the opening came through with a full stop in
the middle of it and with another word for "gehoord de", the close with
its first words misheard or without its article, and the opening of a
motie fell in the turn of the chairman more than once. So a motie is: a
dictum ("verzoekt de regering") with at least one other part of the
formula around it. A dictum alone is somebody talking about a motie
("onze motie verzoekt de regering om ...").

An announcement has no formula: "ik zal daar een motie over indienen", "ik
overweeg een motie". That is a rule too, and a narrow one: the word motie,
a first person, and a verb of submitting that is not in the past. Narrow on
purpose. Members mention moties of earlier all the time ("de motie die
vorig jaar is aangenomen", at least 8 times in those debates), and an
announcement that is missed is read out later anyway.

Pure functions, no I/O.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# How a motie came by.
VORM_INGEDIEND = "ingediend"
VORM_AANGEKONDIGD = "aangekondigd"
VORM_OVERWOGEN = "overwogen"

# The longest dictum that is kept when the close of the formula is missing.
MAX_DICTUM = 900
# How far behind the close the co-signers are looked for, and how much of
# what is found there is kept.
_COSIGN_WITHIN = 4
_COSIGN_MAX = 120

_OPENING, _CONSIDERANS, _DICTUM, _CLOSE = "opening", "considerans", "dictum", "close"

_GOVERNMENT = frozenset(
    "regering kabinet minister staatssecretaris presidium ministerpresident".split()
)
_COSIGN = frozenset(
    "mede medeingediend medeondertekend ondertekend samen mee meeondertekend".split()
)
# The words that lead up to "orde van de dag".
_CLOSE_LEAD = frozenset("en gaat over tot".split())
_CLOSE_LEAD_WORDS = 5
_SENTENCE_END = re.compile(r"(?<!\.)[.?!](?!\.)")
_COSIGN_STOP = re.compile(r"\.\.\.|[.?!…]")

# An announcement: the verb of submitting, in a form that is not the past.
_SUBMIT = frozenset("indienen indien dien dienen".split())
# "overwege" is one way a transcript writes "overweeg".
_CONSIDER = frozenset("overweeg overwegen overwege".split())
_FIRST_PERSON = frozenset("ik wij we".split())
# With one of these near the word motie it is about a motie of earlier, of
# someone else, or about no motie at all.
_NOT_NOW = frozenset(
    "ingediend aangenomen aangehouden verworpen ontraden uitgevoerd uitvoering"
    " eerder destijds vorig vorige geen niet scheelt".split()
)
_ANNOUNCE_BEFORE = 14
_ANNOUNCE_AFTER = 8
# A sentence that reaches further than this from the word motie, in
# characters, is not shown whole.
_ANNOUNCE_SENTENCE = 200


@dataclass(frozen=True)
class _Token:
    word: str
    start: int
    end: int


@dataclass(frozen=True)
class Motie:
    """One motie found in a turn."""

    # `VORM_INGEDIEND` for one that is read out, `VORM_AANGEKONDIGD` or
    # `VORM_OVERWOGEN` for one the speaker says is coming.
    vorm: str
    # Cut from the turn. For a motie that is read out: the dictum, from
    # "verzoekt de regering" up to and including the close, and who signed
    # it with the speaker if that is read out right behind it.
    citaat: str
    # Where in the turn the quote begins.
    plek: int
    # Where the whole formula stands in the turn, from its first part to
    # its last (end past the last character). Nothing in there is a
    # question to the bewindspersoon.
    start: int
    end: int


def _fold(text: str) -> str:
    flat = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in flat if not unicodedata.combining(c))


def _tokens(text: str) -> list[_Token]:
    """The words of a text with where each one stands.

    Folded per word, so the places stay those of the text as it is.
    """
    return [
        _Token(_fold(found.group(0)).replace("-", ""), found.start(), found.end())
        for found in re.finditer(r"[^\W_]+(?:-[^\W_]+)*", text)
    ]


def _markers(tokens: list[_Token]) -> list[tuple[int, int, str]]:
    """The parts of the formula in a turn, as (start, end, kind), in order."""
    found: list[tuple[int, int, str]] = []
    words = [t.word for t in tokens]
    for i, word in enumerate(words):
        if word.startswith("beraadslag"):
            # "De Kamer, gehoord de beraadslaging", with whatever the
            # transcript made of the words in between.
            before = [
                j for j in range(max(0, i - 4), i) if words[j] in ("kamer", "gehoord")
            ]
            if before:
                first = before[0]
                if words[first] == "kamer" and words[first - 1 : first] == ["de"]:
                    first -= 1
                found.append((tokens[first].start, tokens[i].end, _OPENING))
        elif word in ("constaterende", "overwegende"):
            found.append((tokens[i].start, tokens[i].end, _CONSIDERANS))
        elif word == "verzoekt":
            # "verzoekt de regering", "verzoekt het kabinet", "verzoekt de
            # minister van ...".
            if any(w in _GOVERNMENT for w in words[i + 1 : i + 3]):
                found.append((tokens[i].start, tokens[i].end, _DICTUM))
        elif word == "spreekt" and words[i + 1 : i + 2] == ["uit"]:
            found.append((tokens[i].start, tokens[i + 1].end, _DICTUM))
        elif word == "roept" and any(w in _GOVERNMENT for w in words[i + 1 : i + 3]):
            if "op" in words[i + 2 : i + 5]:
                found.append((tokens[i].start, tokens[i].end, _DICTUM))
        elif word == "orde" and "dag" in words[i + 1 : i + 4]:
            # "gaat over tot de orde van de dag"; the first words of it are
            # what the transcript gets wrong.
            last = i + 1 + words[i + 1 : i + 4].index("dag")
            found.append((tokens[i].start, tokens[last].end, _CLOSE))
    return sorted(found)


@dataclass
class _Span:
    start: int
    parts: set[str]
    dictum: int | None = None
    end: int | None = None


def _read_out(text: str, tokens: list[_Token]) -> list[Motie]:
    spans: list[_Span] = []
    current: _Span | None = None

    def finish(end: int) -> None:
        nonlocal current
        if current is not None:
            current.end = end
            spans.append(current)
        current = None

    for start, end, kind in _markers(tokens):
        if kind == _CLOSE:
            if current is not None:
                current.parts.add(_CLOSE)
                finish(end)
            continue
        if current is not None and current.dictum is not None and kind != _DICTUM:
            # The next motie begins, and the close of this one was not
            # heard: a considerans never follows its dictum.
            finish(start)
        if current is None:
            current = _Span(start=start, parts=set())
        current.parts.add(kind)
        if kind == _DICTUM and current.dictum is None:
            current.dictum = start
    finish(len(text))

    moties: list[Motie] = []
    for span in spans:
        # A dictum, and one other part of the formula that says it is read
        # out and not talked about.
        if span.dictum is None or len(span.parts) < 2:
            continue
        end = span.end if span.end is not None else len(text)
        if _CLOSE in span.parts:
            end = _with_cosigners(text, tokens, end)
        elif end - span.dictum > MAX_DICTUM:
            end = _cut_at_word(text, span.dictum + MAX_DICTUM)
        citaat = text[span.dictum : end].strip()
        if not citaat:
            continue
        moties.append(
            Motie(
                vorm=VORM_INGEDIEND,
                citaat=citaat,
                plek=span.dictum,
                start=span.start,
                end=end,
            )
        )
    return moties


def _cut_at_word(text: str, at: int) -> int:
    while at > 0 and not text[at - 1].isspace():
        at -= 1
    return at


def _with_cosigners(text: str, tokens: list[_Token], end: int) -> int:
    """The end of a motie, with who signed it if that is read out behind it.

    "... orde van de dag. Mede ingediend door het lid B." The names are as
    the transcript heard them, which is often wrong, so they stay part of
    the quote and are not made into anything.
    """
    after = [t for t in tokens if t.start >= end][:_COSIGN_WITHIN]
    signed = next((t for t in after if t.word in _COSIGN), None)
    if signed is None:
        return end
    # Up to where the names stop: the end of the sentence, the dots of a
    # subtitle line that runs on, or the opening of the next motie.
    limit = min(len(text), end + _COSIGN_MAX)
    following = [
        start for start, _, _ in _markers(tokens) if signed.end <= start < limit
    ]
    if following:
        limit = following[0]
    stop = _COSIGN_STOP.search(text, signed.end, limit)
    if stop is not None:
        return stop.start()
    if following or limit == len(text):
        return limit
    return _cut_at_word(text, limit)


def _announced(text: str, tokens: list[_Token], read_out: list[Motie]) -> list[Motie]:
    moties: list[Motie] = []
    covered = 0
    for i, token in enumerate(tokens):
        if token.word not in ("motie", "moties") or token.start < covered:
            continue
        if any(m.start <= token.start < m.end for m in read_out):
            continue
        # The sentence the word stands in, and not more than a few words
        # of it on either side: the transcript does not always end one.
        left, right = _sentence(text, token.start, token.end)
        near = [
            t.word
            for t in tokens[max(0, i - _ANNOUNCE_BEFORE) : i + _ANNOUNCE_AFTER + 1]
            if left <= t.start < right
        ]
        if not any(w in _FIRST_PERSON for w in near):
            continue
        if any(w in _NOT_NOW for w in near):
            continue
        if any(w in _CONSIDER for w in near):
            vorm = VORM_OVERWOGEN
        elif any(w in _SUBMIT for w in near):
            vorm = VORM_AANGEKONDIGD
        else:
            continue
        if any(m.start >= token.start for m in read_out):
            # "Ik dien de volgende motie in", and then the motie itself:
            # one motie, and the one that is read out says more.
            continue
        # The whole sentence when it is one; a transcript without full
        # stops gives the words around the announcement instead.
        begin, stop = left, right
        if token.start - left > _ANNOUNCE_SENTENCE:
            begin = tokens[max(0, i - _ANNOUNCE_BEFORE)].start
        if right - token.end > _ANNOUNCE_SENTENCE:
            stop = tokens[min(len(tokens) - 1, i + _ANNOUNCE_AFTER)].end
        citaat = text[begin:stop].strip()
        begin += len(text[begin:stop]) - len(text[begin:stop].lstrip())
        moties.append(
            Motie(vorm=vorm, citaat=citaat, plek=begin, start=begin, end=stop)
        )
        # "Ik dien twee moties in. De eerste motie ..." is one announcement.
        covered = stop
    return moties


def _sentence(text: str, start: int, end: int) -> tuple[int, int]:
    left = 0
    for found in _SENTENCE_END.finditer(text, 0, start):
        left = found.end()
    closing = _SENTENCE_END.search(text, end)
    return left, closing.end() if closing is not None else len(text)


def find_moties(text: str) -> list[Motie]:
    """The moties in a turn, in the order they stand in it.

    Says nothing about who speaks: the caller leaves out the chairman, who
    reads nothing out, and the bewindspersoon, who gives an oordeel on a
    motie and repeats its words while doing so.
    """
    tokens = _tokens(text)
    read_out = _read_out(text, tokens)
    return sorted(
        [*read_out, *_announced(text, tokens, read_out)], key=lambda m: m.plek
    )


def is_motion_text(quote: str) -> bool:
    """Whether a quote holds a part of the formula of a motie.

    For a quote the model handed in as a question. "Verzoekt de regering"
    is a request to the cabinet in form and a motie in kind: it gets an
    oordeel, not an answer. On four real debates the model marked the text
    of a motie as a question 6 to 9 times per run.
    """
    return bool(_markers(_tokens(quote)))


def dictum_without_close(citaat: str) -> str:
    """The dictum of a motie, without the close of the formula.

    "... en gaat over tot de orde van de dag" says nothing about what is
    asked, and neither does who signed it. For a first line.
    """
    tokens = _tokens(citaat)
    close = next((s for s, _, kind in _markers(tokens) if kind == _CLOSE), None)
    if close is None:
        return citaat.strip()
    at = next(i for i, token in enumerate(tokens) if token.start == close)
    # "en gaat over tot de", or what the transcript made of it: from the
    # first of those words within reach, everything belongs to the close.
    lead = [
        i
        for i in range(max(0, at - _CLOSE_LEAD_WORDS), at)
        if tokens[i].word in _CLOSE_LEAD
    ]
    if lead:
        at = lead[0]
    return citaat[: tokens[at].start].rstrip(" ,;.…")


def motie_vorm(citaat: str) -> str:
    """How a motie came by, read back from the quote that was stored for it.

    The quote of a motie that was read out begins with its dictum; that of
    an announcement holds the word motie and no dictum.
    """
    tokens = _tokens(citaat)
    if any(kind == _DICTUM for *_, kind in _markers(tokens)):
        return VORM_INGEDIEND
    if any(t.word in _CONSIDER for t in tokens):
        return VORM_OVERWOGEN
    return VORM_AANGEKONDIGD
