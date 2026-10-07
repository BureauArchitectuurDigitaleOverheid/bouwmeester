"""Whether a question asks for something on paper, checked in code.

A member who asks "kan de staatssecretaris ons per brief laten weten hoe dat
zit" asks a question, and one that is answered differently: not on the spot but
with a letter, which someone at the ministry has to write. That is a
property of the question and not a kind of its own: marked apart, the same
sentence would hang under a turn twice.

The property is read from the quote by rule, and no model is asked for it.
A rule costs no call, and it cannot name a letter nobody asked for: the
word it shows stands in the quote. What it gives up is the request that
names no product at all, only a wish to see or hear something by a moment;
the labeller was unsure of every one of those in the gold set.

What counts, by the codebook (`scripts/debat_eval/README.md`):

* a form: "per brief", "schriftelijk";
* a product that is asked for: a brief, an overzicht, a rapportage or a
  notitie that is to be sent, received, expected or come back in, or that
  is asked for by a moment ("vóór de begrotingsbehandeling een overzicht
  geven" is not said on the spot); a plan, an evaluatie or a tijdpad only
  when it is to go to the Kamer, because "komt de minister met een plan"
  asks for policy and not for paper;
* "de Kamer informeren" with a moment ("voor de begrotingsbehandeling").
  Without a moment or a form it can be answered on the spot and is an
  ordinary question;
* information the member wants to receive ("wij ontvangen graag de
  gegevens").

What does not count, although the word is there:

* a question about a letter that exists: "in de brief van vorige week
  staat", "wat vindt de minister van het rapport";
* a member announcing something of their own: "ik zal daar een brief over
  sturen", "wij komen met een plan";
* when something comes ("wanneer komt de evaluatie naar de Kamer"): that
  is answered with a date, on the spot.

The dictum of a motie never gets here: `lees_antwoord` drops it as a
question before this is asked.

The transcript comes from speech recognition, so the rule works on the
words alone, without punctuation, and looks a few words to either side of
the product instead of at a sentence.

Pure functions, no I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bouwmeester.services.debat_vraag_vorm import words

# What is shown for each product. Our words, picked by the member's: the
# reply says "vraagt om een brief", never a word a model wrote.
PRODUCT_BRIEF = "een brief"
PRODUCT_OVERZICHT = "een overzicht"
PRODUCT_RAPPORTAGE = "een rapportage"
PRODUCT_NOTITIE = "een notitie"
PRODUCT_PLAN = "een plan"
PRODUCT_EVALUATIE = "een evaluatie"
PRODUCT_TIJDPAD = "een tijdpad"
PRODUCT_SCHRIFTELIJK = "een schriftelijk antwoord"
PRODUCT_BERICHT = "bericht aan de Kamer"
PRODUCT_INFORMATIE = "informatie op papier"
PRODUCTS = frozenset(
    {
        PRODUCT_BRIEF,
        PRODUCT_OVERZICHT,
        PRODUCT_RAPPORTAGE,
        PRODUCT_NOTITIE,
        PRODUCT_PLAN,
        PRODUCT_EVALUATIE,
        PRODUCT_TIJDPAD,
        PRODUCT_SCHRIFTELIJK,
        PRODUCT_BERICHT,
        PRODUCT_INFORMATIE,
    }
)

# A product that is paper by its name: asking to get one is asking for
# paper.
_PAPER = (
    (re.compile(r"(?:kamer|verzamel|voortgangs)?brie(?:f|fje)"), PRODUCT_BRIEF),
    (re.compile(r"overzicht(?:je|en)?"), PRODUCT_OVERZICHT),
    (re.compile(r"(?:voortgangs)?rapportages?"), PRODUCT_RAPPORTAGE),
    (re.compile(r"notitie"), PRODUCT_NOTITIE),
)
# A product that is as often policy as paper: "een plan", "de evaluatie".
# It only counts on its way to the Kamer.
_MAYBE_PAPER = (
    (re.compile(r"plan|actieplan"), PRODUCT_PLAN),
    (re.compile(r"evaluatie"), PRODUCT_EVALUATIE),
    (re.compile(r"tijdpad|routekaart|planning"), PRODUCT_TIJDPAD),
)
# How far from the product the words that ask for it may stand.
_REACH = 8
# On its way to the Kamer.
_TO_KAMER = re.compile(
    r"\b(?:(?:naar|aan|met) (?:de|uw|onze) (?:tweede )?kamer"
    r"|(?:de )?kamer (?:\w+ ){0,5}(?:sturen|stuurt|zenden|informeren|informeert)"
    r"|toe(?:te)?(?:sturen|zenden)|toestuurt|toezendt|nasturen|toekomen"
    r"|ontvang(?:en|t)?)\b"
)
# Asked for, in the looser words that are enough for a letter.
_ASKED_FOR = re.compile(
    r"\b(?:sturen|stuurt|stuur|zenden|krijg(?:en|t)?|verwacht(?:en)?"
    r"|kom(?:t|en)? (?:\w+ ){0,3}met|terug\w*|opstellen|schrijven|schrijft"
    r"|graag|toezeggen|toe te zeggen|bereid)\b"
)
# In front of a product: it is there already, and the question is about it.
_ABOUT = frozenset("in uit volgens over op van".split())
_DEFINITE = frozenset("de die deze het dat dit zijn haar uw hun mijn onze jouw".split())
_EARLIER = frozenset(
    "vorige eerdere laatste recente genoemde gisteren afgelopen".split()
)
# Behind a product: what it says, or when it was sent.
_SAYS = frozenset(
    "staat stond schrijft schreef lees las lezen blijkt bleek zegt meldt noemt"
    " stelt".split()
)
# A member doing it themselves: "ik zal een brief sturen".
_OWN_VERBS = frozenset(
    "zal zullen ga gaan heb hebben kom komen stuur sturen schrijf schrijven"
    " maak maken dien dienen presenteer presenteren bied bieden".split()
)
_FIRST_PERSON = frozenset("ik wij we".split())
_BEWINDSPERSOON = frozenset(
    "minister staatssecretaris kabinet regering bewindspersoon premier hij zij"
    " u".split()
)
# A form of answering, whatever is asked: these need no product.
_PER_BRIEF = re.compile(r"\bper (?:kamer)?brief\b")
# Not "op papier": in a debate that is said of what exists there only,
# once in the gold set and never as a form of answering.
_IN_WRITING = re.compile(r"\bschriftelijk\b")
# "Het schriftelijk overleg" is a procedure of the Kamer, not a request.
_PROCEDURE = frozenset({"overleg"})
_PERFECT = frozenset("heeft heb hebben had hadden".split())
_PARTICIPLE = re.compile(r"ge\w+(?:d|t|en)")
_INFORM = re.compile(r"\b(?:informeren|informeert|informeer|geinformeerd)\b")
_KAMER = frozenset("kamer ons commissie mij".split())
_RECEIVE = re.compile(r"\bontvang(?:en|t)?\b")
_INFORMATION = frozenset("informatie cijfers gegevens stukken documenten".split())

_MONTH = (
    r"(?:januari|februari|maart|april|mei|juni|juli|augustus|september|oktober"
    r"|november|december)"
)
_EVENT = (
    r"(?:begrotingsbehandeling|begroting|zomerreces|zomer|kerstreces|kerst"
    r"|herfstreces|meireces|voorjaarsreces|krokusreces|reces|verkiezingen"
    r"|jaarwisseling|stemmingen|tweede termijn|plenaire behandeling"
    r"|wetsbehandeling|behandeling|commissiedebat|wetgevingsoverleg"
    r"|notaoverleg|debat|voorjaarsnota|najaarsnota|prinsjesdag"
    r"|einde? van (?:het |dit |de )?(?:jaar|maand|week))"
)
# By when, in the words a member asks with. The whole phrase, because it
# is shown as it was said. Only wordings of a deadline: "dit jaar" and "in
# maart" say as often what the letter is to be about ("hoeveel er dit jaar
# zijn bijgekomen") as when it is to come.
_MOMENT = re.compile(
    r"\b(?:(?:nog |ruim |kort |uiterlijk )?(?:voorafgaand aan|voor|bij|rond)"
    r" (?:de |het |dit |deze |die |dat )?(?:volgende |komende |aanstaande )?"
    rf"{_EVENT}"
    r"|(?:voor|uiterlijk|per|rond|begin|eind|medio|half) "
    rf"(?:\d{{1,2}} )?{_MONTH}(?: \d{{4}})?"
    r"|(?:voor|nog|begin|eind) (?:dit|volgend|komend|aankomend)"
    r" (?:jaar|najaar|voorjaar|kwartaal)"
    r"|(?:voor|in) het (?:eerste|tweede|derde|vierde|volgende|komende) kwartaal"
    r"|binnen (?:\w+ ){0,2}(?:dagen|week|weken|maand|maanden)"
    r"|zo (?:snel|spoedig) mogelijk|op korte termijn|binnenkort)\b"
)
# How far in front of what is asked for its moment may begin, and how far
# behind it. Shorter behind: what follows a product is what it is to be
# about ("een brief over wat er vóór de zomer is gebeurd").
_MOMENT_BEFORE = 12
_MOMENT_AFTER = 8
# Behind one of these comes what the letter is to say, and a moment there
# is part of that: "laten weten hoeveel er vóór het reces zijn bijgekomen".
_OPENS_SUBJECT = frozenset(
    "over hoeveel waarin waarom hoe wat welke welk of dat wie waar".split()
)
MAX_MOMENT = 80


@dataclass(frozen=True)
class PaperRequest:
    """What a question asks for on paper.

    `product` is one of `PRODUCTS`: our word for the word the member used.
    `moment` is by when, in the member's words as the transcript has them,
    without capitals or accents; ``None`` when none was named.
    """

    product: str
    moment: str | None = None


def paper_request(quote: str) -> PaperRequest | None:
    """What the quote of a question asks for on paper, or ``None``.

    The first that is found, in the order of the module text: a form, a
    product that is asked for, the Kamer informed by a moment, information
    to receive.
    """
    tokens = words(quote)
    flat = " ".join(tokens)
    found = (
        _form(tokens, flat)
        or _product(tokens, flat)
        or _informed(tokens, flat)
        or _received(tokens, flat)
    )
    if found is None:
        return None
    product, at = found
    return PaperRequest(product, _moment_near(tokens, flat, at))


def _index(flat: str, offset: int) -> int:
    """The number of the word that begins at `offset` in the joined words."""
    return flat.count(" ", 0, offset)


def _around(tokens: list[str], at: int, reach: int) -> str:
    return " ".join(tokens[max(0, at - reach) : at + reach + 1])


def _form(tokens: list[str], flat: str) -> tuple[str, int] | None:
    per_brief = _PER_BRIEF.search(flat)
    if per_brief:
        return PRODUCT_BRIEF, _index(flat, per_brief.start())
    for match in _IN_WRITING.finditer(flat):
        at = _index(flat, match.start())
        if tokens[at + 1 : at + 2] and tokens[at + 1] in _PROCEDURE:
            continue
        # "heeft de minister schriftelijk laten weten", "is schriftelijk
        # geantwoord": told, not asked.
        if any(t in _PERFECT for t in tokens[max(0, at - 6) : at]) and (
            any(_PARTICIPLE.fullmatch(t) for t in tokens[at + 1 : at + 5])
            or tokens[at + 1 : at + 3] == ["laten", "weten"]
        ):
            continue
        return PRODUCT_SCHRIFTELIJK, at
    return None


def _product(tokens: list[str], flat: str) -> tuple[str, int] | None:
    for at, token in enumerate(tokens):
        for nouns, cues in ((_PAPER, (_TO_KAMER, _ASKED_FOR)), (_MAYBE_PAPER, None)):
            product = next((p for rx, p in nouns if rx.fullmatch(token)), None)
            if product is None:
                continue
            if _exists_already(tokens, at) or _is_their_own(tokens, at):
                continue
            # "Wanneer komt de evaluatie naar de Kamer" asks for a date.
            if "wanneer" in tokens[max(0, at - _REACH) : at]:
                continue
            near = _around(tokens, at, _REACH)
            if _TO_KAMER.search(near) or (
                cues and (_ASKED_FOR.search(near) or _moment_near(tokens, flat, at))
            ):
                return product, at
    return None


def _exists_already(tokens: list[str], at: int) -> bool:
    """Whether the product at `at` is one that is there, and spoken about."""
    before = tokens[max(0, at - 3) : at]
    if before and before[-1] in _EARLIER:
        return True
    # "in de brief", "uit het rapport", "over zijn brief".
    if len(before) >= 2 and before[-1] in _DEFINITE and before[-2] in _ABOUT:
        return True
    after = tokens[at + 1 : at + 4]
    if (
        after[:1] == ["van"]
        and after[1:2]
        and (after[1] in _EARLIER or after[1].isdigit())
    ):
        return True
    # "De brief staat vol", "het overzicht waaruit blijkt". Behind "een" it
    # is what the member wants in it: "een brief waarin staat dat".
    return any(t in _SAYS for t in after[:2]) and "een" not in before


def _is_their_own(tokens: list[str], at: int) -> bool:
    """Whether the member says they send or make the product themselves."""
    before = tokens[max(0, at - 6) : at]
    for i in range(len(before) - 1):
        pair = (before[i], before[i + 1])
        if (pair[0] in _FIRST_PERSON and pair[1] in _OWN_VERBS) or (
            pair[1] in _FIRST_PERSON and pair[0] in _OWN_VERBS
        ):
            # "ik zal de minister vragen om een brief" is not their own.
            return not any(t in _BEWINDSPERSOON for t in before[i + 2 :])
    return False


def _informed(tokens: list[str], flat: str) -> tuple[str, int] | None:
    for match in _INFORM.finditer(flat):
        at = _index(flat, match.start())
        if not any(t in _KAMER for t in tokens[max(0, at - 8) : at + 5]):
            continue
        if _moment_near(tokens, flat, at):
            return PRODUCT_BERICHT, at
    return None


def _received(tokens: list[str], flat: str) -> tuple[str, int] | None:
    for match in _RECEIVE.finditer(flat):
        at = _index(flat, match.start())
        if any(t in _INFORMATION for t in tokens[at + 1 : at + _REACH + 1]):
            return PRODUCT_INFORMATIE, at
    return None


def _moment_near(tokens: list[str], flat: str, at: int) -> str | None:
    """The moment that stands closest to the word at `at`, within reach."""
    best: tuple[int, str] | None = None
    for match in _MOMENT.finditer(flat):
        first = _index(flat, match.start())
        if not at - _MOMENT_BEFORE <= first <= at + _MOMENT_AFTER:
            continue
        if any(t in _OPENS_SUBJECT for t in tokens[at + 1 : first]):
            continue
        distance = abs(first - at)
        if best is None or distance < best[0]:
            best = (distance, match.group().strip())
    return best[1][:MAX_MOMENT] if best else None
