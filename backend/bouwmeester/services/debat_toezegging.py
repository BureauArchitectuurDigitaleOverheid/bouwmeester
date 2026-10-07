"""Whether a quote has the form of a toezegging, checked in code.

A toezegging is a bewindspersoon committing to something the Kamer can hold
them to. Whether a sentence is one is a judgement, and a model makes it. But
a model that is asked for commitments finds them: in work that is going on,
in what a colleague promised, in "daar kom ik zo op terug". So, as for a
question (`debat_vraag_vorm`), the quote is checked in code and a quote that
cannot be a commitment is dropped, whatever the model says about it.

The rule looks at form only: the speaker, in the first person or as "het
kabinet", with a verb of committing ("ik zeg toe", "ik zal", "ik ga", "ik
stuur de Kamer", "ik neem dat mee"), or the Kamer that gets something ("u
krijgt die brief voor de zomer"). Its job is to drop plain statements. In
doubt it says yes: whether "ik wil daar graag naar kijken" is a commitment
or a politeness is the model's call.

Five things are dropped although they have that form, because the codebook
names them and they can be told from the words:

* a refusal, wherever in the clause the "niet" or "geen" stands: "dat kan
  ik niet toezeggen", "ik stuur u daar op dit moment geen brief over". Not
  a contrast: "ik kom daar niet nu maar schriftelijk op terug" commits;
* coming back to it later in the same answer or debate: "daar kom ik zo op
  terug", "ik kom daar in de tweede termijn schriftelijk op terug". Also
  with a product named: the second term is this debate, and what is said
  there is heard there. "Schriftelijk vóór de tweede termijn" is a
  commitment, and is not this rule;
* coming back to it without saying when or in what: "ik kom daarop terug"
  counts only with a moment ("voor het kerstreces") or something to deliver
  ("schriftelijk", "in het halfjaarbericht");
* what was promised before, by anyone: "mijn voorganger heeft toegezegd dat
  de Kamer een brief krijgt", "ik heb dat vorige week al toegezegd". Said
  as the deed itself it counts: "bij dezen toegezegd", "dat is toegezegd";
* a question that is told back: "u vraagt of ik kan toezeggen dat".

The transcript comes from speech recognition: the punctuation is not to be
trusted and sentences are not finished. A clause therefore ends at a
punctuation mark if there is one, at "maar" or "want", at a word that
opens a condition ("als", "omdat", "tenzij"), and otherwise a dozen words
behind the wording: far enough for any refusal, and not the whole quote.

Pure functions, no I/O.
"""

from __future__ import annotations

import re

from bouwmeester.services.debat_vraag_vorm import words

# Who commits: the speaker, or the cabinet they speak for.
_I = r"(?:ik|wij|we)"
_CABINET = r"(?:het kabinet|dit kabinet|de regering)"
# The Kamer as who receives.
_KAMER = r"(?:u|de kamer|uw kamer|de commissie|uw commissie|de leden)"
# A few words in between: "ik zeg u dat graag toe".
_GAP = r"(?:\w+ ){0,5}"
_LONG_GAP = r"(?:\w+ ){0,8}"

# What is promised when it is a thing: a letter, a report, a figure.
_PRODUCT = re.compile(
    r"\b(?:brief|brieven|kamerbrief|verzamelbrief|schriftelijk|op papier|rapportage"
    r"|rapport|overzicht|notitie|nota|\w*bericht|voortgangs\w+|planning|evaluatie"
    r"|onderzoek|uitkomst|uitkomsten|resultaten|stand van zaken|update|cijfers"
    r"|informeren|informeer|toekomen|toesturen|nasturen|terugkoppel\w*|verslag"
    r"|monitor|actieplan|plan van aanpak|routekaart|tijdpad|wetsvoorstel|amvb"
    r"|beantwoording|uitwerking)\b"
)
_MONTH = (
    r"(?:januari|februari|maart|april|mei|juni|juli|augustus|september|oktober"
    r"|november|december)"
)
# When, in the words a bewindspersoon uses for it. Not "in de tweede
# termijn" or "straks": that is this debate, see `_LATER_HERE`.
_MOMENT = re.compile(
    r"\b(?:(?:voor|na|rond|tot) (?:de |het )?(?:zomer|zomerreces|kerst|kerstreces"
    r"|reces|herfstreces|meireces|voorjaarsreces|begroting\w*|verkiezingen"
    r"|jaarwisseling|einde? van|volgende|tweede termijn|plenaire|stemmingen"
    r"|debat|commissiedebat|wetgevingsoverleg|notaoverleg|behandeling)"
    r"|(?:dit|volgend|komend|aankomend|begin|eind|medio|half)"
    r" (?:jaar|najaar|voorjaar|kwartaal|maand|week)"
    r"|(?:eerste|tweede|derde|vierde|volgende|komende)"
    r" (?:kwartaal|halfjaar|maanden|weken|week|maand|jaar|keer|moment)"
    r"|volgend (?:moment|debat|overleg)"
    r"|in (?:het|de) (?:voorjaar|najaar|zomer|herfst|winter|lente)"
    rf"|{_MONTH}"
    r"|binnen (?:\w+ ){0,2}(?:dagen|week|weken|maand|maanden)"
    r"|zo (?:snel|spoedig) mogelijk|op korte termijn|binnenkort|uiterlijk"
    r"|prinsjesdag|voorjaarsnota|najaarsnota)\b"
)

# Later in this answer or this debate: nothing the Kamer can hold anyone to.
# "Zo" only in front of a word it means "in a moment" with: "zo snel
# mogelijk" is a moment, and "zo'n proef" is no time at all.
_LATER_HERE = re.compile(
    r"\b(?:straks|dadelijk|zometeen|zo meteen|zo direct|zo dadelijk|verderop"
    r"|zo (?:nog |even |meteen )?(?:op|terug|over|bij|naar|aan|in|toe|doen|iets|wat)"
    r"|later in (?:dit|het|mijn) (?:debat|betoog|antwoord|blok|blokje)"
    r"|in (?:de |mijn )?tweede termijn"
    r"|in (?:het|mijn) (?:volgende|tweede|derde|laatste) blokj?e?"
    r"|bij het (?:volgende )?blokj?e?)\b"
)
_COMES_BACK = re.compile(r"\bterug\w*\b")

# What a bewindspersoon comes with, or what comes.
_BROUGHT = (
    r"(?:brief|kamerbrief|voorstel|wetsvoorstel|plan|reactie|kabinetsreactie"
    r"|overzicht|notitie|nota|uitwerking|rapportage|evaluatie|planning|update"
    r"|verslag|antwoord)"
)

# The wordings that say little by themselves: "ik zal", "dat ga ik doen",
# "ik wil daar een proef mee starten". A bewindspersoon says "ik wil" and
# "ik ga" in every other sentence of an answer, mostly about what comes
# next in it.
_WEAK_CUES: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (
        # With room for one word between who and the verb: "wat ik wel
        # wil doen", "ik ook ga".
        rf"\b{_I} (?:\w+ )?(?:zal|zullen|ga|gaan|wil|willen)\b",
        rf"\b(?:zal|zullen|ga|gaan|wil|willen) {_I}\b",
        rf"\b{_CABINET} (?:zal|gaat|wil|komt|stuurt|informeert|bereidt)\b",
        rf"\b(?:zal|gaat|wil|komt|stuurt|informeert|bereidt) {_CABINET}\b",
        rf"\b(?:ben|zijn) {_I} {_GAP}bereid\b",
        rf"\b{_I} (?:ben|zijn) {_GAP}bereid\b",
        # "dat doe ik", "prima, doen we"
        rf"\b(?:doe|doen) {_I}\b",
    )
)
# The wordings that name the promise or the deed. Each pattern is looked
# for by itself, so that a refusal at the start of a quote does not hide a
# commitment after it.
_STRONG_CUES: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (
        # "dat zeg ik toe", "ik zeg u dat toe", "laat ik toezeggen dat"
        rf"\b{_I} zeg(?:gen)? {_GAP}toe\b",
        rf"\bzeg(?:gen)? {_I} {_GAP}toe\b",
        rf"\b{_I} {_GAP}toe(?:zeg|zeggen)\b",
        rf"\b(?:kan|kunnen|wil|willen|zal|zullen) {_I} {_GAP}toezeggen\b",
        r"\b(?:mijn|onze|een|de|deze|die) toezegging\b",
        # The participle only where saying it is doing it: "bij dezen
        # toegezegd", "dat is toegezegd". With "heb" or "heeft" it tells
        # what was promised before, and is no wording at all.
        r"\b(?:bij deze|bij dezen|hierbij) (?:\w+ ){0,3}toegezegd\b",
        r"\b(?:dat|dit) is (?:dan |dus |hierbij |bij deze |bij dezen )?toegezegd\b",
        # "ik stuur de Kamer", "ik informeer u", "ik beloof"
        rf"\b{_I} (?:stuur|sturen|informeer|informeren|beloof|beloven|bespreek"
        r"|bespreken|betrek|betrekken|lever|leveren|rapporteer|rapporteren)\b",
        r"\b(?:stuur|sturen|informeer|informeren|beloof|beloven|bespreek|bespreken"
        rf"|betrek|betrekken|lever|leveren|rapporteer|rapporteren) {_I}\b",
        # A verb with the word that makes it a deed: "ik neem dat mee", "ik
        # zoek dat uit", "ik kom daar schriftelijk op terug", "ik laat het u
        # weten", "ik maak daar geld voor vrij". Without that word "ik neem
        # aan dat" and "ik kom uit het zuiden" would count.
        rf"\b{_I} (?:neem|nemen) {_LONG_GAP}(?:mee|op)\b",
        rf"\b(?:neem|nemen) {_I} {_LONG_GAP}(?:mee|op)\b",
        rf"\b{_I} (?:zoek|zoeken) {_LONG_GAP}uit\b",
        rf"\b(?:zoek|zoeken) {_I} {_LONG_GAP}uit\b",
        rf"\b{_I} (?:pak|pakken) {_LONG_GAP}op\b",
        rf"\b(?:pak|pakken) {_I} {_LONG_GAP}op\b",
        # "Terug" can stand far behind: "ik kom daar niet nu maar
        # schriftelijk voor de zomer op terug".
        rf"\b{_I} (?:kom|komen) (?:\w+ ){{0,12}}terug\b",
        rf"\b(?:kom|komen) {_I} (?:\w+ ){{0,12}}terug\b",
        # "Ik kom met" only with what is brought: "ik kom uit een gezin met
        # drie kinderen" comes with nothing.
        rf"\b{_I} (?:kom|komen) (?:\w+ ){{0,4}}met (?:een |de |het ){_BROUGHT}\b",
        rf"\b(?:kom|komen) {_I} (?:\w+ ){{0,4}}met (?:een |de |het ){_BROUGHT}\b",
        rf"\b{_I} (?:laat|laten) {_LONG_GAP}"
        r"(?:weten|uitzoeken|onderzoeken|nagaan|uitwerken|toekomen)\b",
        rf"\b(?:laat|laten) {_I} {_LONG_GAP}"
        r"(?:weten|uitzoeken|onderzoeken|nagaan|uitwerken|toekomen)\b",
        rf"\b{_I} (?:zorg|zorgen) (?:\w+ ){{0,2}}(?:dat|voor|ervoor)\b",
        rf"\b(?:zorg|zorgen) {_I} (?:\w+ ){{0,2}}(?:dat|voor|ervoor)\b",
        rf"\b{_I} (?:geef|geven) {_LONG_GAP}door\b",
        rf"\b{_I} (?:breng|brengen) {_LONG_GAP}(?:over|in kaart)\b",
        # With room for a sum in between: "ik maak daar in de begroting
        # van volgend jaar twee miljoen euro voor vrij".
        rf"\b{_I} (?:maak|maken) (?:\w+ ){{0,12}}vrij\b",
        rf"\b{_I} (?:doe|doen) {_LONG_GAP}(?:toekomen|graag)\b",
        # The verb at the end, as in a clause: "dat ik dat meeneem".
        rf"\b{_I} {_LONG_GAP}(?:meeneem|meenemen|uitzoek|uitzoeken|oppak|oppakken"
        r"|terugkom|terugkomen|doorgeef|toestuur|toesturen|nastuur|nasturen)\b",
        # The Kamer receives: "u krijgt die brief voor de zomer", "die komt
        # in het voorjaar naar de Kamer".
        rf"\b{_KAMER} (?:\w+ ){{0,2}}"
        r"(?:krijgt|krijgen|ontvangt|ontvangen|hoort|horen)\b",
        rf"\b(?:krijgt|ontvangt|hoort) {_KAMER}\b",
        rf"\b(?:komt|komen|gaat|gaan|stuur|sturen) {_LONG_GAP}naar (?:de|uw) kamer\b",
        rf"\b(?:kunt u|kan de kamer|kan uw kamer|mag u|mag de kamer) {_LONG_GAP}"
        r"(?:verwachten|tegemoet|rekenen)\b",
        r"\bdoen toekomen\b",
        # Nobody named as who does it: "de Kamer wordt daarover voor de
        # zomer geïnformeerd", "er komt een brief voor de begroting".
        rf"\b{_KAMER} (?:wordt|worden) {_LONG_GAP}(?:geinformeerd|bericht|ingelicht)\b",
        rf"\b(?:wordt|worden) {_KAMER} {_LONG_GAP}(?:geinformeerd|bericht|ingelicht)\b",
        rf"\b(?:er (?:komt|volgt)|(?:komt|volgt) er) (?:\w+ ){{0,3}}{_BROUGHT}\b",
    )
)
# Every way a commitment is worded.
_CUES = (*_STRONG_CUES, *_WEAK_CUES)

# How far a clause reaches behind a wording when nothing ends it: speech
# recognition leaves whole answers without a comma. The two refusals this
# was widened for have their "niet" and "geen" five and seven words behind
# the wording; it was three words before, and both got through.
_CLAUSE_REACH = 12
# How far in front of a wording the word can stand that says when:
# "straks zal ik daar meer over zeggen".
_BEFORE = 4
# How far behind it "terug" still belongs to it.
_AFTER = 9
# Where a clause ends when the transcript has no punctuation there.
_CONJUNCTIONS = frozenset("maar want doch".split())
_CONDITIONS = frozenset(
    "als omdat zodat tenzij mits zodra wanneer indien terwijl hoewel".split()
)
_NEGATIONS = frozenset("niet geen nooit niets niks".split())
# "Niet nu maar schriftelijk": within this many words a "maar" makes a
# "niet" a contrast, and what stands behind "maar" is what is promised.
_CONTRAST_REACH = 4
# What was promised before, told: "heeft toegezegd dat", "heb ik al
# toegezegd". Looked for in the words in front of a wording.
_TOLD = re.compile(
    r"\b(?:heb|heeft|hebben|had|hadden) (?:\w+ ){0,6}toegezegd(?: dat)?(?: \w+){0,4}$"
)
# A question told back: "u vraagt of ik kan toezeggen".
_ASKED = re.compile(
    r"\b(?:vraag|vraagt|vragen|vroeg|vroegen|gevraagd) (?:\w+ ){0,3}of$"
)
# Only in front of a space or at the end: the dot in "500.000" ends nothing.
_MARK = re.compile(r"\.\.\.|…|[.?!;:,](?=\s|$)")


def _split(text: str) -> tuple[list[str], set[int]]:
    """The words of a text, and which of them come first after a mark.

    The three dots of a subtitle line that runs on are no mark: the
    sentence goes on behind them.
    """
    tokens: list[str] = []
    breaks: set[int] = set()
    at = 0
    for mark in _MARK.finditer(text):
        tokens.extend(words(text[at : mark.start()]))
        if mark.group() not in ("...", "…"):
            breaks.add(len(tokens))
        at = mark.end()
    tokens.extend(words(text[at:]))
    return tokens, breaks


def _flat(text: str) -> str:
    """A text as its words with one space between them."""
    return " ".join(words(text))


def may_hold_commitment(text: str) -> bool:
    """Whether the words of a commitment stand anywhere in a text.

    For a whole turn, before a model is asked about it: a turn in which
    none of the wordings occurs holds no quote that `has_commitment_form`
    would let through, so asking would cost a call and mark nothing.
    Nothing is weighed here; a refusal counts too.
    """
    flat = _flat(text)
    return any(cue.search(flat) for cue in _CUES)


def has_commitment_form(quote: str) -> bool:
    """Whether a quote itself holds a commitment of the speaker.

    One wording of a commitment is enough (see `_CUES`), unless that
    wording is refused, or puts it off to later in the same debate, or
    promises to come back to it without a moment or anything to deliver.

    When in doubt it says yes: a statement that slips through was the
    model's choice, a commitment that is stopped is lost.
    """
    return _commits(quote, _CUES)


def _commits(text: str, cues: tuple[re.Pattern[str], ...]) -> bool:
    """Whether one of `cues` stands in a text as a commitment."""
    tokens, breaks = _split(text)
    flat = " ".join(tokens)
    named = bool(_PRODUCT.search(flat) or _MOMENT.search(flat))
    for cue in cues:
        for found in cue.finditer(flat):
            first = flat.count(" ", 0, found.start())
            last = first + found.group().count(" ")
            if any(first < mark <= last for mark in breaks):
                # Two halves of a wording on either side of a full stop
                # are two sentences, not a wording.
                continue
            end = _clause_end(tokens, breaks, last)
            if _is_refused(tokens, first, last, end):
                continue
            before = " ".join(tokens[max(0, first - 12) : first])
            if _TOLD.search(before) or _ASKED.search(before):
                continue
            around = " ".join(tokens[max(0, first - _BEFORE) : end + 1])
            if _LATER_HERE.search(around):
                continue
            behind = " ".join(tokens[first : min(end, last + _AFTER) + 1])
            if not named and _COMES_BACK.search(behind):
                continue
            return True
    return False


def _clause_end(tokens: list[str], breaks: set[int], last: int) -> int:
    """The last word of the clause a wording stands in."""
    end = last
    while (
        end + 1 < len(tokens)
        and end - last < _CLAUSE_REACH
        and end + 1 not in breaks
        and tokens[end + 1] not in _CONJUNCTIONS
        and tokens[end + 1] not in _CONDITIONS
    ):
        end += 1
    return end


def _is_refused(tokens: list[str], first: int, last: int, end: int) -> bool:
    """Whether a wording is refused: a negation in its clause, from the
    wording on. The wording itself is `first` to `last`.

    Not "niet alleen", and not a contrast: "ik stuur die brief niet morgen
    maar volgende week", "ik kom daar niet nu maar schriftelijk op terug".
    A contrast is a "niet" with "maar" close behind it, where what stands
    behind "maar" still belongs to the wording. In "dat kan ik niet
    toezeggen maar het is een goed idee" the wording ends before "maar",
    with the "niet" in it: that is a refusal and then something else.
    """
    for at in range(first, end + 1):
        if tokens[at] not in _NEGATIONS:
            continue
        if tokens[at] == "niet" and tokens[at + 1 : at + 2] == ["alleen"]:
            continue
        reach = tokens[at + 1 : at + 1 + _CONTRAST_REACH]
        if "maar" in reach and (at > last or at + 1 + reach.index("maar") <= last):
            continue
        return True
    return False


# Where a sentence ends in a transcript: a full stop and then a capital.
# The three dots of a line that runs on go on in lower case.
_SENTENCE = re.compile(r"(?<=[.?!])\s+(?=[A-ZÀ-Ý])")
MAX_PASSAGES = 15
MAX_PASSAGE = 300


def commitment_passages(text: str, limit: int = MAX_PASSAGES) -> list[str]:
    """The sentences of an answer that most look like a toezegging.

    For the model, as places to look. A model that reads an answer of ten
    minutes for toezeggingen finds some and passes over others, and which
    ones differs from run to run: on the debate the rules were made on it
    found 3 to 5 of the 6 it could find over five runs, and among the ones
    it passed over was a sentence with "dat zeg ik toe" in it. Finding such
    a sentence is what code is good at; judging it is still the model's.
    With these sentences in the prompt it found the same 4 of the 6 in
    three runs out of three. Nothing it marked on that debate was wrong, in
    any of eleven runs.
    The two it still misses are not among these sentences: a promise to do
    "something" and one worded as a wish, each without a moment or
    anything to deliver.

    A sentence is one when it has the form of a commitment
    (`has_commitment_form`) by a wording that names the promise or the
    deed, or by any wording together with a moment or something to
    deliver. "Ik wil daar iets over zeggen" alone is none: an answer has
    dozens of those.

    As they stand in the text, in order, each cut to `MAX_PASSAGE`.
    """
    found: list[str] = []
    for sentence in _SENTENCE.split(text):
        flat = _flat(sentence)
        if not flat:
            continue
        named = bool(_PRODUCT.search(flat) or _MOMENT.search(flat))
        if _commits(sentence, _STRONG_CUES) or (
            named and _commits(sentence, _WEAK_CUES)
        ):
            found.append(" ".join(sentence.split())[:MAX_PASSAGE])
            if len(found) >= limit:
                break
    return found


def deadline_is_said(deadline: str, quote: str) -> bool:
    """Whether the moment the model gave is one the quote names.

    The model is asked for the moment in the words of the speaker. One it
    worked out itself ("eind 2030" for "volgend jaar") is not shown as what
    was promised, and neither is one it got the wrong way round: "voor de
    zomer" where "na de zomer" was said. So the words of the moment have to
    stand in the quote as they are, one after the other. Short words count:
    "in mei" is a moment.
    """
    said = _flat(deadline)
    return bool(said) and f" {said} " in f" {_flat(quote)} "


# Words that say nothing about what a question or a toezegging is about:
# every one of them is in half of what is said in a debate.
_GENERIC = frozenset(
    "minister ministers staatssecretaris kabinet regering kamer kamerlid leden"
    " voorzitter vraag vragen toezegging toezeggen toegezegd zeggen graag"
    " willen zullen kunnen moeten worden hebben maken komen gaan doen"
    " daarover daarvan daarbij daarmee hierover waarom wanneer welke hoeveel"
    " andere anders eerder verder zoals omdat tussen binnen zonder onder"
    " alleen altijd nooit precies eigenlijk natuurlijk misschien volgende"
    " mensen manier moment punt zaken stand goede groot grote nieuwe"
    " informeren informeert stuurt sturen brief schriftelijk"
    # Who and what every debate is about, whatever its subject: two
    # sentences that both name the gemeenten and the provincies are not
    # about the same thing yet.
    " gemeente gemeenten provincie provincies rijksoverheid overheid overheden"
    " nederland nederlandse europa europese burgers bedrijven beleid"
    " miljoen miljard euros bedrag gesprek gesprekken overleg".split()
)
# A word counts from this many letters, and two words are the same word when
# they start alike: "bezuinigd" and "bezuinigingen", "onderzoek" and
# "onderzoeken".
_STEM = 6
_MIN_WORD = 5
# How many of those a toezegging and a question have to share before the
# model's "this answers question 12" is believed. See `shares_a_subject`.
MIN_SHARED = 2


def _subject_words(text: str, without: frozenset[str] | set[str]) -> set[str]:
    return {
        word[:_STEM]
        for word in words(text)
        if len(word) >= _MIN_WORD
        and word not in _GENERIC
        and word[:_STEM] not in without
    }


def shares_a_subject(toezegging: str, question: str, onderwerp: str = "") -> bool:
    """Whether a toezegging and a question are about the same thing, by their words.

    The model names the open question a toezegging answers. On the debate
    the rules were made on it named one for six of seven toezeggingen, and
    three of the six were the question that was answered; the others were a
    question about something near it. So the link is checked: the two have
    to share at least `MIN_SHARED` words that say what they are about. Not
    the words of the subject of the debate, which every question shares,
    and not the words of asking and promising.

    Both texts are the summary and the quote together: the summaries are
    the model's and spell the terms right, the quotes are what was said.
    A link that is dropped costs a line in the reply; a wrong one tells
    whoever asked that they got an answer.
    """
    subject = {word[:_STEM] for word in words(onderwerp)}
    shared = _subject_words(toezegging, subject) & _subject_words(question, subject)
    return len(shared) >= MIN_SHARED
