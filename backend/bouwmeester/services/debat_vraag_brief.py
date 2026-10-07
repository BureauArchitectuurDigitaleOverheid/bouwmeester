"""Whether a question asks for something on paper, checked in code.

A member who asks "kan de staatssecretaris ons per brief laten weten hoe dat
zit" asks a question, and one that is answered differently: not on the spot
but with a letter, which someone at the ministry has to write. That is a
property of the question and not a kind of its own: marked apart, the same
sentence would hang under a turn twice.

The property is read from the quote by rule, and no model is asked for it.
A rule costs no call, and it cannot name a letter nobody asked for: the
word it shows stands in the quote.

A word for paper near a word for sending is not enough. "De wethouder
stuurt ouders een brief met een boete" and "we krijgen steeds een overzicht
dat niet klopt" have both, and ask nothing. So the rule knows a handful of
ways of asking, and the product has to be what is asked for in one of them:

* the bewindspersoon is asked to send, write or promise it: "kan de
  minister een overzicht naar de Kamer sturen", "is de staatssecretaris
  bereid een notitie op te stellen", "stuurt de minister ons een brief";
* the member wants to get it: "ik zou graag een brief ontvangen", "krijgen
  wij daar een rapportage over", "graag een brief", "wij verwachten een
  briefje", "ik vraag de minister om een overzicht";
* it is named as where an answer can come: "kan dat in een brief", "mag
  dat in een volgende brief, als de minister er dan op terugkomt";
* a form of answering is asked for: "kan de minister daar schriftelijk op
  terugkomen", "per brief", "wil de staatssecretaris dat op papier zetten";
* the Kamer is to be informed by a moment: "kan de minister de Kamer in
  maart informeren". Without a moment it can be answered on the spot and is
  an ordinary question;
* information the member would like to receive: "wij ontvangen graag de
  gegevens".

A plan, an evaluatie, a tijdpad, a planning or a routekaart is as often
policy as paper ("komt de minister met een plan"), and only counts on its
way to the Kamer or to be received.

What does not count, although it fits one of those:

* a letter that is there: "graag een reactie op de brief van vorige week";
* when or why: "wanneer kunnen wij de brief verwachten" is answered with a
  date, on the spot;
* a condition: "ik overweeg een motie tenzij de minister een brief
  toezegt" announces a motie and asks for nothing yet.

The dictum of a motie never gets here: `lees_antwoord` drops it as a
question before this is asked.

The transcript comes from speech recognition. Sentences are cut at the
marks that are there, and within a sentence the rule works on the words
alone, with a few words allowed between the parts of a wording.

Pure functions, no I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bouwmeester.services.debat_vraag_vorm import words

# What is shown for each product: the member's own word, in one spelling.
# The reply never shows a word a model wrote.
PRODUCT_BRIEF = "een brief"
PRODUCT_OVERZICHT = "een overzicht"
PRODUCT_RAPPORTAGE = "een rapportage"
PRODUCT_NOTITIE = "een notitie"
PRODUCT_PLAN = "een plan"
PRODUCT_ACTIEPLAN = "een actieplan"
PRODUCT_EVALUATIE = "een evaluatie"
PRODUCT_TIJDPAD = "een tijdpad"
PRODUCT_PLANNING = "een planning"
PRODUCT_ROUTEKAART = "een routekaart"
PRODUCT_SCHRIFTELIJK = "een schriftelijk antwoord"
PRODUCT_OP_PAPIER = "iets op papier"
PRODUCT_BERICHT = "bericht aan de Kamer"
PRODUCT_INFORMATIE = "informatie op papier"
PRODUCTS = frozenset(
    {
        PRODUCT_BRIEF,
        PRODUCT_OVERZICHT,
        PRODUCT_RAPPORTAGE,
        PRODUCT_NOTITIE,
        PRODUCT_PLAN,
        PRODUCT_ACTIEPLAN,
        PRODUCT_EVALUATIE,
        PRODUCT_TIJDPAD,
        PRODUCT_PLANNING,
        PRODUCT_ROUTEKAART,
        PRODUCT_SCHRIFTELIJK,
        PRODUCT_OP_PAPIER,
        PRODUCT_BERICHT,
        PRODUCT_INFORMATIE,
    }
)

# A product that is paper by its name.
_PAPER_NAMES = (
    (re.compile(r"(?:kamer|verzamel|voortgangs)?brie(?:f|fje)"), PRODUCT_BRIEF),
    (re.compile(r"overzicht(?:je)?"), PRODUCT_OVERZICHT),
    (re.compile(r"(?:voortgangs)?rapportage"), PRODUCT_RAPPORTAGE),
    (re.compile(r"notitie"), PRODUCT_NOTITIE),
)
# A product that is as often policy as paper.
_MAYBE_NAMES = (
    (re.compile(r"plan"), PRODUCT_PLAN),
    (re.compile(r"actieplan"), PRODUCT_ACTIEPLAN),
    (re.compile(r"evaluatie"), PRODUCT_EVALUATIE),
    (re.compile(r"tijdpad"), PRODUCT_TIJDPAD),
    (re.compile(r"planning"), PRODUCT_PLANNING),
    (re.compile(r"routekaart"), PRODUCT_ROUTEKAART),
)
_FORM_NAMES = {
    "per brief": PRODUCT_BRIEF,
    "per kamerbrief": PRODUCT_BRIEF,
    "schriftelijk": PRODUCT_SCHRIFTELIJK,
    "op papier": PRODUCT_OP_PAPIER,
}
_PAPER = (
    r"(?:(?:kamer|verzamel|voortgangs)?brie(?:f|fje)|overzicht(?:je)?"
    r"|(?:voortgangs)?rapportage|notitie)"
)
_MAYBE = r"(?:plan|actieplan|evaluatie|tijdpad|routekaart|planning)"
_ANY = rf"(?:{_PAPER}|{_MAYBE})"
_WHO = (
    r"(?:(?:de |het |deze |dit )?(?:minister|staatssecretaris|kabinet|regering"
    r"|bewindspersoon|bewindspersonen|premier)|hij|zij|u)"
)
_MODAL = (
    r"(?:kan|kunnen|kunt|wil|willen|wilt|zou|zouden|zal|zullen|zult|mag|mogen"
    r"|gaat|gaan)"
)
_I = r"(?:ik|wij|we)"
# The bewindspersoon is asked: the verb in front, as in a question, or the
# member saying that they ask.
_ADDRESS = (
    # Not behind "ik": "ik zal de minister een brief sturen" is the member's
    # own letter.
    rf"(?:(?<!\bik )(?<!\bwij )(?<!\bwe ){_MODAL} {_WHO}"
    rf"|(?:is|zijn|bent) {_WHO} (?:\w+ ){{0,3}}bereid"
    rf"|{_I} (?:vraag|vragen|verzoek|verzoeken) (?:aan )?{_WHO})"
)
# What a bewindspersoon does with paper. Not "geven" or "krijgen": see
# `_GIVE`.
_SEND = (
    r"(?:sturen|stuurt|toesturen|toestuurt|toe te sturen|toezenden|toe te zenden"
    r"|zenden|zendt|schrijven|schrijft|opstellen|op te stellen|opstelt"
    r"|toezeggen|toe te zeggen|toezegt|aanleveren|leveren|levert|delen|deelt"
    r"|maken|maakt|toekomen|nasturen)"
)
# "Een overzicht geven" can be done on the spot, in words. It asks for
# paper only by a moment: "vóór de begrotingsbehandeling een overzicht
# geven".
_GIVE = r"(?:geven|geeft)"
_RECEIVE = r"(?:ontvangen|krijgen|verwachten|zien|hebben)"
_KAMER = re.compile(r"\b(?:kamer|ons|commissie)\b")
# A few words between two parts of a wording.
_UP_TO_12 = r"(?:\w+ ){0,12}?"
_UP_TO_8 = r"(?:\w+ ){0,8}?"
_THEN_8 = r"(?: \w+){0,8}?"

# Each wording as (pattern, kind). The group `p` is the product or the form.
_SENT = "sent"
_GIVEN = "given"
_WANTED = "wanted"
_FORM = "form"
_INFORMED = "informed"
_INFORMATION = "information"
_WORDINGS: tuple[tuple[re.Pattern[str], str], ...] = (
    # A form of answering.
    (
        re.compile(
            rf"\b{_ADDRESS} {_UP_TO_12}(?P<p>per (?:kamer)?brief|schriftelijk"
            r"|op papier (?=zetten|krijgen|vastleggen|ontvangen|hebben))\b"
        ),
        _FORM,
    ),
    (
        re.compile(
            r"\bgraag (?:\w+ ){0,6}?(?P<p>per (?:kamer)?brief|schriftelijk)\b"
            r"|\b(?P<p2>per (?:kamer)?brief|schriftelijk) (?:\w+ ){0,3}graag\b"
        ),
        _FORM,
    ),
    # The bewindspersoon is asked to send it.
    (
        re.compile(rf"\b{_ADDRESS} {_UP_TO_12}(?P<p>{_ANY}){_THEN_8} (?P<v>{_SEND})\b"),
        _SENT,
    ),
    (
        re.compile(
            rf"\b{_ADDRESS} {_UP_TO_12}(?P<p>{_PAPER}){_THEN_8} (?P<v>{_GIVE})\b"
        ),
        _GIVEN,
    ),
    (
        re.compile(
            rf"\b(?:stuurt|zendt|levert) {_WHO} {_UP_TO_8}(?P<p>{_ANY})\b"
            rf"|\bkom(?:t|en) {_WHO} (?:\w+ ){{0,4}}?met (?:\w+ ){{0,2}}?"
            rf"(?P<p2>{_PAPER})\b"
        ),
        _SENT,
    ),
    # The member wants to get it.
    (
        re.compile(
            rf"\b{_I} (?:zou|zouden|wil|willen) {_UP_TO_12}(?P<p>{_ANY}){_THEN_8}"
            rf" (?P<v>{_RECEIVE})\b"
            rf"|\b(?:kan|kunnen|mag|mogen) (?:{_I}|de kamer) {_UP_TO_12}"
            rf"(?P<p2>{_ANY}){_THEN_8} (?P<v2>{_RECEIVE})\b"
            rf"|\b(?:krijg|krijgen|krijgt|ontvang|ontvangen|ontvangt)"
            rf" (?:{_I}|de kamer) {_UP_TO_12}(?P<p3>{_ANY})\b"
        ),
        _WANTED,
    ),
    (
        re.compile(
            rf"\bgraag {_UP_TO_8}(?P<p>{_PAPER})\b"
            rf"|\b(?P<p2>{_PAPER}) (?:\w+ ){{0,3}}graag\b"
            # Expecting a letter is asking for one; expecting the letter
            # that was promised is not.
            rf"|\b(?:{_I} verwacht(?:en)?|verwacht(?:en)? {_I}) (?:\w+ ){{0,3}}?een"
            rf" (?:\w+ ){{0,3}}?(?P<p3>{_PAPER})\b"
            rf"|\b{_WHO} (?:\w+ ){{0,3}}?om (?:\w+ ){{0,3}}?(?P<p4>{_PAPER})"
            r" (?:\w+ ){0,2}?(?:vragen|verzoeken|vraag|verzoek)\b"
            rf"|\b(?:vraag|vragen|verzoek|verzoeken) (?:\w+ ){{0,5}}?{_WHO}"
            rf" (?:\w+ ){{0,3}}?om (?:\w+ ){{0,3}}?(?P<p5>{_PAPER})\b"
        ),
        _WANTED,
    ),
    # Named as where an answer can come.
    (
        re.compile(
            rf"\b(?:kan|mag) (?:dat|dit|het|die) (?:\w+ ){{0,3}}?in een (?:\w+ )?"
            rf"(?P<p>{_PAPER})\b"
            rf"|\b(?:kan|kunnen|mag|mogen|misschien|graag) {_UP_TO_8}in"
            r" (?:een|de|zijn|haar)"
            r" (?:volgende|komende|aparte|nieuwe|eerstvolgende)"
            rf" (?P<p2>{_PAPER})(?: \w+){{0,10}}? terug\w*"
        ),
        _WANTED,
    ),
    # The Kamer informed. Counts with a moment only, see `paper_request`.
    (
        re.compile(rf"\b{_ADDRESS} (?:\w+ ){{0,14}}?(?P<p>informeren|informeert)\b"),
        _INFORMED,
    ),
    # Information to receive.
    (
        re.compile(
            rf"\b(?:graag ontvang(?:en)? {_I}|{_I} ontvang(?:en)? graag"
            rf"|ontvang(?:en)? {_I} graag|graag (?:\w+ ){{0,4}}?ontvangen)"
            r"(?: \w+){0,5}? (?P<p>informatie|cijfers|gegevens|stukken|documenten)\b"
        ),
        _INFORMATION,
    ),
)

# In front of a wording these ask when or why, not for the thing.
_NOT_FOR_IT = frozenset("wanneer waarom hoezo".split())
# In front of a wording these make it a condition and not a request.
_CONDITION = frozenset("tenzij mits".split())
# In front of a product: it is there already, and the question is about it.
_ABOUT = frozenset("uit volgens over op van".split())
_DEFINITE = frozenset("de die deze het dat dit zijn haar uw hun mijn onze jouw".split())
# "Het schriftelijk overleg" is a procedure of the Kamer, not a request.
_PROCEDURE = frozenset({"overleg"})
# On its way to the Kamer, for a product that is not paper by its name.
_TO_KAMER = re.compile(r"\b(?:kamer|ons|toesturen|toezenden|toekomen)\b|\btoe te\b")

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
# is shown as it was said. It is only looked for inside the wording of the
# request and right behind it, so "in maart" and "na de zomer" are the
# moment of the sending there, and not what the letter is to be about.
_MOMENT = re.compile(
    r"\b(?:(?:nog |ruim |kort |uiterlijk )?(?:voorafgaand aan|voor|na|bij|rond)"
    r" (?:de |het |dit |deze |die |dat )?(?:volgende |komende |aanstaande )?"
    rf"{_EVENT}"
    r"|(?:voor|uiterlijk|per|rond|begin|eind|medio|half|in) "
    rf"(?:\d{{1,2}} )?{_MONTH}(?: \d{{4}})?"
    r"|(?:voor|nog|begin|eind) (?:dit|volgend|komend|aankomend)"
    r" (?:jaar|najaar|voorjaar|kwartaal)"
    r"|(?:voor|in) het (?:eerste|tweede|derde|vierde|volgende|komende) kwartaal"
    r"|in het (?:voorjaar|najaar)"
    r"|binnen (?:\w+ ){0,2}(?:dagen|week|weken|maand|maanden)"
    r"|zo (?:snel|spoedig) mogelijk|op korte termijn|binnenkort)\b"
)
# How far behind the wording of a request its moment may begin: "een brief
# sturen, graag vóór de zomer".
_MOMENT_AFTER = 4
# Behind one of these comes what the letter is to say or what it is for,
# and a moment there is not when it is to come: "laten weten hoeveel er
# vóór het reces zijn bijgekomen", "zodat we die vóór de begroting kunnen
# bespreken".
_OPENS_SOMETHING_ELSE = frozenset(
    "over hoeveel waarin waarom hoe wat welke welk of dat wie waar zodat omdat"
    " want om als".split()
)
MAX_MOMENT = 80
_SENTENCE_END = re.compile(r"(?<!\.)[.?!;](?!\.)|…")


@dataclass(frozen=True)
class PaperRequest:
    """What a question asks for on paper.

    `product` is one of `PRODUCTS`: the word the member used, in a fixed
    spelling. `moment` is by when, in the member's words as the transcript
    has them, without capitals; ``None`` when none was named, or when two
    were and the rule cannot tell which is meant.
    """

    product: str
    moment: str | None = None


def paper_request(quote: str) -> PaperRequest | None:
    """What the quote of a question asks for on paper, or ``None``.

    The first sentence that asks for something decides, and in it the
    first wording in the order of the module text.
    """
    for sentence in _SENTENCE_END.split(quote):
        tokens = words(sentence)
        if not tokens:
            continue
        found = _in_sentence(tokens)
        if found is not None:
            return found
    return None


def _in_sentence(tokens: list[str]) -> PaperRequest | None:
    flat = " ".join(tokens)
    for pattern, kind in _WORDINGS:
        for match in pattern.finditer(flat):
            name = next(k for k, v in match.groupdict().items() if v and k[0] == "p")
            first = _index(flat, match.start())
            last = _index(flat, match.end() - 1)
            at = _index(flat, match.start(name))
            before = tokens[:first]
            if any(t in _NOT_FOR_IT or t in _CONDITION for t in before):
                continue
            product = _named(match.group(name), kind)
            if product is None:
                continue
            if kind == _FORM:
                if tokens[at + 1 : at + 2] and tokens[at + 1] in _PROCEDURE:
                    continue
            elif kind in (_SENT, _GIVEN, _WANTED):
                if _exists_already(tokens, at):
                    continue
                span = " ".join(tokens[first : last + 1])
                if product in _MAYBE_PRODUCTS and not (
                    _TO_KAMER.search(span) or " ontvangen" in span
                ):
                    continue
            moment = _moment(tokens, flat, first, last)
            if kind == _INFORMED and not (
                moment.said and _KAMER.search(" ".join(tokens[first : last + 3]))
            ):
                continue
            if kind == _GIVEN and not moment.said:
                continue
            return PaperRequest(product, moment.shown)
    return None


_MAYBE_PRODUCTS = frozenset(product for _, product in _MAYBE_NAMES)


def _named(word: str, kind: str) -> str | None:
    """Our spelling of what the member named."""
    if kind == _FORM:
        return _FORM_NAMES.get(word.strip())
    if kind == _INFORMED:
        return PRODUCT_BERICHT
    if kind == _INFORMATION:
        return PRODUCT_INFORMATIE
    for names in (_PAPER_NAMES, _MAYBE_NAMES):
        for pattern, product in names:
            if pattern.fullmatch(word):
                return product
    return None


def _index(flat: str, offset: int) -> int:
    """The number of the word that begins at `offset` in the joined words."""
    return flat.count(" ", 0, offset)


def _exists_already(tokens: list[str], at: int) -> bool:
    """Whether the product at `at` is one that is there, and spoken about:
    "op de brief", "uit het overzicht", "over zijn notitie"."""
    before = tokens[max(0, at - 2) : at]
    return len(before) == 2 and before[1] in _DEFINITE and before[0] in _ABOUT


@dataclass(frozen=True)
class _Moment:
    # Whether a moment was said with the request at all.
    said: bool = False
    # The one to show; ``None`` when there is none, or more than one.
    shown: str | None = None


def _moment(tokens: list[str], flat: str, first: int, last: int) -> _Moment:
    """The moment that belongs to the wording from word `first` to `last`.

    One that stands in the wording, or begins within `_MOMENT_AFTER` words
    behind it with nothing in between that opens something else. Two of
    them is one too many: "liefst vóór het reces en anders vóór de zomer"
    is not for a rule to choose from, and no moment is shown.
    """
    found: list[str] = []
    for match in _MOMENT.finditer(flat):
        begin = _index(flat, match.start())
        if begin < first or begin > last + _MOMENT_AFTER:
            continue
        if begin > last and any(
            t in _OPENS_SOMETHING_ELSE for t in tokens[last + 1 : begin]
        ):
            continue
        found.append(match.group().strip())
    if len(found) != 1:
        return _Moment(said=bool(found))
    # "Vóór" is what the member said; the words lost the accent.
    shown = re.sub(r"\bvoor\b", "vóór", found[0])[:MAX_MOMENT]
    return _Moment(said=True, shown=shown)
