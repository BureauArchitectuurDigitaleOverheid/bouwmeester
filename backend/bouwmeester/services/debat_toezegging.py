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

Three things are dropped although they have that form, because the codebook
names them and they can be told from the words:

* a refusal: "dat kan ik niet toezeggen", "dat ga ik niet doen";
* coming back to it later in the same answer or debate: "daar kom ik zo op
  terug", "dat doe ik in de tweede termijn";
* coming back to it without saying when or in what: "ik kom daarop terug"
  counts only with a moment ("voor het kerstreces") or something to deliver
  ("schriftelijk", "in het halfjaarbericht").

The transcript comes from speech recognition: the punctuation is not to be
trusted and sentences are not finished. So nothing here depends on where a
sentence ends; everything is a distance in words.

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
# "Zo" only where it means "in a moment": "zo snel mogelijk" is a moment,
# and "zo'n" is flattened to one word before this is looked for.
_LATER_HERE = re.compile(
    r"\b(?:straks|dadelijk|zometeen|zo meteen|zo direct|zo dadelijk|verderop"
    r"|zo (?:nog |even |meteen )?(?:op|terug|over|bij|naar|aan|in|toe|doen|iets|wat)"
    r"|later in (?:dit|het|mijn) (?:debat|betoog|antwoord|blok|blokje)"
    r"|in (?:de |mijn )?tweede termijn"
    r"|in (?:het|mijn) (?:volgende|tweede|derde|laatste) blokj?e?"
    r"|bij het (?:volgende )?blokj?e?)\b"
)
_NEGATION = re.compile(r"\b(?:niet(?! alleen)|geen|nooit|niets|niks)\b")
_COMES_BACK = re.compile(r"\bterug\w*\b")

# Every way a commitment is worded. Each pattern is looked for by itself, so
# that a refusal at the start of a quote does not hide a commitment after it.
_CUES: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (
        # "dat zeg ik toe", "ik zeg u dat toe", "laat ik toezeggen dat"
        rf"\b{_I} zeg(?:gen)? {_GAP}toe\b",
        rf"\bzeg(?:gen)? {_I} {_GAP}toe\b",
        rf"\b{_I} {_GAP}toe(?:zeg|zeggen|gezegd)\b",
        rf"\b(?:kan|kunnen|wil|willen|zal|zullen) {_I} {_GAP}toezeggen\b",
        r"\b(?:mijn|onze|een|de|deze) toezegging\b",
        # "ik zal", "dat ga ik doen", "ik wil daar een proef mee starten"
        rf"\b{_I} (?:zal|zullen|ga|gaan|wil|willen)\b",
        rf"\b(?:zal|zullen|ga|gaan|wil|willen) {_I}\b",
        rf"\b{_CABINET} (?:zal|gaat|wil|komt|stuurt|informeert)\b",
        rf"\b(?:zal|gaat|wil|komt|stuurt|informeert) {_CABINET}\b",
        rf"\b(?:ben|zijn) {_I} {_GAP}bereid\b",
        rf"\b{_I} (?:ben|zijn) {_GAP}bereid\b",
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
        rf"\b{_I} (?:kom|komen) {_LONG_GAP}(?:terug|met)\b",
        rf"\b(?:kom|komen) {_I} {_LONG_GAP}(?:terug|met)\b",
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
        r"\bdat (?:doe|doen) (?:ik|wij|we)\b",
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
    )
)

# How far behind a cue its "niet" can stand: "dat ga ik nu echt niet doen".
_NEGATION_REACH = 3
# How far around a cue the words stand that say when: "daar kom ik zo
# meteen in het blokje handhaving nog op terug".
_BEFORE = 4
_AFTER = 9


def _flat(text: str) -> str:
    """A text as its words with one space between them."""
    # "zo'n proef" is not "zo": in a moment.
    text = re.sub(r"\bzo['’`]n\b", "zon", text.lower())
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
    flat = _flat(quote)
    tokens = flat.split()
    named = bool(_PRODUCT.search(flat) or _MOMENT.search(flat))
    for cue in _CUES:
        for found in cue.finditer(flat):
            first = flat.count(" ", 0, found.start())
            last = first + found.group().count(" ")
            said = found.group()
            behind = " ".join(tokens[last + 1 : last + 1 + _NEGATION_REACH])
            if _NEGATION.search(f"{said} {behind}"):
                continue
            around = " ".join(tokens[max(0, first - _BEFORE) : last + 1 + _AFTER])
            if not named and (_LATER_HERE.search(around) or _COMES_BACK.search(around)):
                continue
            return True
    return False


def deadline_is_said(deadline: str, quote: str) -> bool:
    """Whether the moment the model gave is one the quote names.

    The model is asked for the moment in the words of the speaker. One it
    worked out itself ("eind 2030" for "volgend jaar") is not shown as what
    was promised: at least one word of it that says something has to stand
    in the quote.
    """
    said = set(words(quote))
    return any(len(word) >= 4 and word in said for word in words(deadline))


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
    " informeren informeert stuurt sturen brief schriftelijk".split()
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
