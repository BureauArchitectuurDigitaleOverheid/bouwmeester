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
formula near it.

Every part of the formula is also a thing people say in a debate:
"alles overwegende", "dat is aan de orde van de dag", "de motie van vorig
jaar verzoekt de regering". So a part only counts in the shape the formula
has ("overwegende dat", not "aan de orde van de dag", not "de motie
verzoekt"), and the parts have to stand as close together as they do in a
motie that is read out: a dictum in the last sentence of a turn does not
make a motie of a figure of speech in its first.

An announcement has no formula: "ik zal daar een motie over indienen", "ik
overweeg een motie". That is a rule too, and a narrow one: the word motie,
and the speaker as the subject of a verb of submitting that is not in the
past. Narrow on purpose. Members mention moties of earlier and of others
all the time ("de motie die vorig jaar is aangenomen", at least 8 times in
those debates), and an announcement that is missed is read out later
anyway.

Pure functions, no I/O.
"""

from __future__ import annotations

import bisect
import re
import unicodedata
from dataclasses import dataclass

# How a motie came by.
VORM_INGEDIEND = "ingediend"
VORM_AANGEKONDIGD = "aangekondigd"
VORM_OVERWOGEN = "overwogen"

# How far apart two parts of the formula may stand, in characters. Measured
# on the 9 moties that were read out in the three debates the rule was made
# on: at most 404 between two parts in front of the dictum, and at most 619
# from the dictum to the close. Each limit is about one and a half times
# that.
MAX_GAP = 600
MAX_DICTUM = 900
# A dictum whose close was not heard ends with its sentence, and never runs
# further than this: what follows it is the rest of the turn, with the
# questions that are in it.
MAX_OPEN_DICTUM = 400
# A turn is never this long; a text that is, is not read at all.
MAX_TEXT = 200_000
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
# With "motie" this close in front of it, a dictum is told about and not
# read out: "de motie van vorig jaar verzoekt de regering".
_TOLD_WITHIN = 5

_FIRST_PERSON = frozenset("ik wij we".split())
# An announcement: the speaker and one of these verbs next to each other,
# "ik zal" or "zal ik", and further on "indienen".
_WILL = frozenset("zal zullen ga gaan wil willen kondig kondigen".split())
# "Ik dien een motie in": the verb, and its "in" behind the motie.
_SUBMIT = frozenset("dien dienen".split())
_COME = frozenset("kom komen".split())
# "overwege" is one way a transcript writes "overweeg".
_CONSIDER = frozenset("overweeg overwegen overwege".split())
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
    """The parts of the formula in a turn, as (start, end, kind), in order.

    Each in the shape it has in a motie, and not in the shape it has in
    ordinary speech.
    """
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
            # "Alles overwegende is dit een slecht plan" is no considerans.
            if words[i + 1 : i + 2] == ["dat"]:
                found.append((tokens[i].start, tokens[i].end, _CONSIDERANS))
        elif word in ("verzoekt", "verzoek"):
            # "verzoekt de regering", "verzoekt het kabinet", "verzoekt de
            # minister van ...". The transcript drops the t now and then;
            # "ik verzoek de regering" is a member asking, not a motie.
            if not any(w in _GOVERNMENT for w in words[i + 1 : i + 3]):
                continue
            if word == "verzoek" and any(
                w in _FIRST_PERSON for w in words[max(0, i - 2) : i]
            ):
                continue
            if _is_told(words, i):
                continue
            found.append((tokens[i].start, tokens[i].end, _DICTUM))
        elif word == "spreekt" and words[i + 1 : i + 3] == ["uit", "dat"]:
            # Not "spreekt uit haar hart".
            if not _is_told(words, i):
                found.append((tokens[i].start, tokens[i + 1].end, _DICTUM))
        elif word == "roept" and any(w in _GOVERNMENT for w in words[i + 1 : i + 3]):
            if "op" in words[i + 2 : i + 5] and not _is_told(words, i):
                found.append((tokens[i].start, tokens[i].end, _DICTUM))
        elif word == "orde" and "dag" in words[i + 1 : i + 4]:
            # "gaat over tot de orde van de dag"; the first words of it are
            # what the transcript gets wrong, so they are not asked for.
            # But "dat is aan de orde van de dag" closes nothing.
            if "aan" in words[max(0, i - 2) : i]:
                continue
            last = i + 1 + words[i + 1 : i + 4].index("dag")
            found.append((tokens[i].start, tokens[last].end, _CLOSE))
    return sorted(found)


def _is_told(words: list[str], at: int) -> bool:
    """Whether the dictum at `at` has a motie as its subject.

    "De motie verzoekt de regering om een plan" is someone saying what a
    motie asks. In a motie that is read out the subject is "de Kamer", a
    considerans back. None of the moties in the debates the rule was made
    on has the word this close in front of its dictum.
    """
    return any(w in ("motie", "moties") for w in words[max(0, at - _TOLD_WITHIN) : at])


@dataclass
class _Span:
    start: int
    parts: set[str]
    # Where the last part that was added ends.
    reach: int
    dictum: int | None = None
    # Where it ends: behind its close, or where the next motie begins.
    end: int | None = None


def _spans(tokens: list[_Token]) -> list[_Span]:
    """The stretches of a text that hold parts of the formula close together."""
    spans: list[_Span] = []
    current: _Span | None = None

    def finish(end: int | None) -> None:
        nonlocal current
        if current is not None:
            current.end = end
            spans.append(current)
        current = None

    for start, end, kind in _markers(tokens):
        if current is not None and current.dictum is None:
            if start - current.reach > MAX_GAP:
                # Too far from what came before to be the same motie.
                finish(None)
        if current is not None and current.dictum is not None:
            near = start - current.dictum <= MAX_DICTUM
            if kind == _CLOSE and near:
                current.parts.add(_CLOSE)
                finish(end)
                continue
            if kind == _DICTUM and near:
                # "... en verzoekt de regering tevens ...": one motie.
                current.reach = end
                continue
            # The next motie begins, or this is something else further
            # on: the close of this one was not heard.
            finish(start if near else None)
        if kind == _CLOSE:
            continue
        if current is None:
            current = _Span(start=start, parts=set(), reach=end)
        current.parts.add(kind)
        current.reach = end
        if kind == _DICTUM and current.dictum is None:
            current.dictum = start
    finish(None)
    return spans


def _read_out(text: str, tokens: list[_Token]) -> list[Motie]:
    moties: list[Motie] = []
    for span in _spans(tokens):
        # A dictum, and one other part of the formula that says it is read
        # out and not talked about.
        if span.dictum is None or len(span.parts) < 2:
            continue
        if _CLOSE in span.parts and span.end is not None:
            end = _with_cosigners(text, tokens, span.end)
        else:
            end = _open_end(text, span.dictum, span.end)
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


def _open_end(text: str, dictum: int, limit: int | None) -> int:
    """Where a dictum ends whose close was not heard.

    With its sentence. What comes after that is the rest of the turn, and
    a question in it is a question. `limit` is where the next motie
    begins, if one does.
    """
    limit = min(limit if limit is not None else len(text), len(text))
    stop = _SENTENCE_END.search(text, dictum, min(limit, dictum + MAX_OPEN_DICTUM))
    if stop is not None:
        return stop.end()
    if limit - dictum <= MAX_OPEN_DICTUM:
        return limit
    return _cut_at_word(text, dictum + MAX_OPEN_DICTUM)


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


def _announces(near: list[str], at: int) -> str | None:
    """Whether the words around "motie" say the speaker submits one.

    `near` are the words of its sentence, `at` is where "motie" stands in
    them. The form it is announced in, or ``None``.

    The speaker has to be the subject of the verb: "ik zal", "zal ik",
    "dien ik", "wij overwegen". A first person somewhere in the sentence is
    not enough ("wij zullen de motie die de collega gaat indienen steunen"),
    and neither is a word that looks like the verb ("indien de minister dit
    toezegt", "we dienen die motie uit te voeren").
    """
    if any(word in _NOT_NOW for word in near):
        return None
    if any(pair == ("af", "van") for pair in zip(near, near[1:], strict=False)):
        # "Dan zie ik af van de motie."
        return None
    after = near[at + 1 :]
    for i, word in enumerate(near):
        if word not in _FIRST_PERSON:
            continue
        for verb in (*near[max(0, i - 1) : i], *near[i + 1 : i + 2]):
            if verb in _CONSIDER:
                return VORM_OVERWOGEN
            if verb in _SUBMIT and "in" in after[:4]:
                # "dien ik een motie in", and not "in te trekken".
                particle = after.index("in")
                if after[particle + 1 : particle + 2] != ["te"]:
                    return VORM_AANGEKONDIGD
            if verb in _COME and "met" in near[max(0, at - 3) : at]:
                return VORM_AANGEKONDIGD
            if verb in _WILL and _submits_after(near, at, i):
                return VORM_AANGEKONDIGD
    return None


def _submits_after(near: list[str], at: int, subject: int) -> bool:
    """Whether "indienen" follows, as what the speaker will do with the motie."""
    for i in range(subject + 1, len(near)):
        submits = near[i] == "indienen" or near[max(0, i - 2) : i + 1] == [
            "in",
            "te",
            "dienen",
        ]
        if not submits:
            continue
        # "de motie die de collega gaat indienen" is someone else's.
        return not any(word in ("die", "dat") for word in near[at + 1 : i])
    return False


def _announced(text: str, tokens: list[_Token], read_out: list[Motie]) -> list[Motie]:
    moties: list[Motie] = []
    covered = 0
    ends = [found.end() for found in _SENTENCE_END.finditer(text)]
    for i, token in enumerate(tokens):
        if token.word not in ("motie", "moties") or token.start < covered:
            continue
        if any(m.start <= token.start < m.end for m in read_out):
            continue
        # The sentence the word stands in, and not more than a few words
        # of it on either side: the transcript does not always end one.
        left, right = _sentence(ends, len(text), token.start, token.end)
        first = max(0, i - _ANNOUNCE_BEFORE)
        while tokens[first].start < left:
            first += 1
        near = [
            t.word for t in tokens[first : i + _ANNOUNCE_AFTER + 1] if t.start < right
        ]
        vorm = _announces(near, i - first)
        if vorm is None:
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


def _sentence(ends: list[int], length: int, start: int, end: int) -> tuple[int, int]:
    """The sentence around [start, end), from the ends of all sentences.

    Looked up, not searched for: a text without full stops and with the
    word motie on every line would be read once per motie otherwise.
    """
    before = bisect.bisect_right(ends, start)
    left = ends[before - 1] if before else 0
    after = bisect.bisect_left(ends, end + 1)
    return left, ends[after] if after < len(ends) else length


def find_moties(text: str) -> list[Motie]:
    """The moties in a turn, in the order they stand in it.

    Says nothing about who speaks: the caller leaves out the chairman, who
    reads nothing out, and the bewindspersoon, who gives an oordeel on a
    motie and repeats its words while doing so.
    """
    if len(text) > MAX_TEXT:
        return []
    tokens = _tokens(text)
    read_out = _read_out(text, tokens)
    return sorted(
        [*read_out, *_announced(text, tokens, read_out)], key=lambda m: m.plek
    )


def is_motion_text(quote: str) -> bool:
    """Whether a quote is a piece of a motie that is read out.

    For a quote the model handed in as a question, in a turn where the
    motie itself was not found: its opening fell in the turn before, say.
    On four real debates the model marked the text of a motie as a
    question 6 to 9 times per run.

    On the evidence a motie needs: two different parts of the formula,
    close together. One part is a word people use ("alles overwegende", a
    question about what an earlier motie "verzoekt"), and dropping a
    question for it is worse than letting a dictum through.
    """
    return any(len(span.parts) >= 2 for span in _spans(_tokens(quote)))


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
