"""Whether a quote has the form of a question, checked in code.

The model that marks questions copies a sentence from the turn and writes a
tidy question next to it as the summary. The quote is literally in the
turn, so the check on the quote lets it through, and what reaches the
channel is a statement with a question made of it. On four real debates
that was the largest group of wrong markings: 21 to 32 of about 52 per run.
A sentence in the prompt did not stop it; the model went on marking the
very example the prompt gave. So it is not left to the model: a quote that
holds no question and no request is dropped, whatever the model says.

The rule looks at form only. Whether a question is put to the
bewindspersoon, is rhetorical, or is answered by the speaker is still the
model's call: those have the form of a question.

The transcript comes from speech recognition. It writes full stops where
question marks belong and loses the first word of a sentence now and then,
so a missing question mark never drops a quote by itself: the order of the
words and the words of a request count as much.

Pure functions, no I/O.
"""

from __future__ import annotations

import re
import unicodedata

# Words a Dutch question opens with.
_QUESTION_WORDS = frozenset(
    "hoe wat waarom wanneer welke welk wie waar hoeveel hoelang".split()
)
# These open a relative clause as often as a question ("een wet waardoor
# de minister ..."), so they only count with a verb and whoever is asked.
_RELATIVE_WORDS = frozenset("waarop waarmee waarvan waarvoor waardoor".split())
# In a question the verb comes second: "Hoe gaat de minister". With one of
# these right behind the question word it comes last, and the clause is
# part of a statement: "hoe de minister dat ziet", "wat wij willen".
_SUBJECT_STARTS = frozenset(
    "de het een die dat deze dit we wij ik je jij u hij zij ze men er mijn"
    " onze ons zo zon dus nou bijvoorbeeld".split()
)
_AFTER_VOOR = frozenset(
    "ons mij me hem haar hen jou u de het deze die dit dat onze mijn".split()
)
# The verbs a yes/no question opens with when nobody is named behind them:
# "Klopt het dat", "Is het lot van", "Worden er ook". A Dutch statement
# does not open with its verb.
_OPENING_VERBS = frozenset(
    "klopt is zijn was wordt worden heeft hebben kan kunnen gaat gaan zal"
    " zullen wil willen mag mogen moet moeten blijft komt zou zouden".split()
)
# Who a question is put to, as the subject right behind the verb.
_SUBJECTS = frozenset("we wij hij zij ze u je jullie".split())
_ADDRESSED = frozenset(
    {
        ("de", "minister"),
        ("deze", "minister"),
        ("de", "staatssecretaris"),
        ("deze", "staatssecretaris"),
        ("de", "bewindspersoon"),
        ("de", "bewindspersonen"),
        ("het", "kabinet"),
        ("dit", "kabinet"),
        ("de", "regering"),
        ("de", "premier"),
    }
)
# A word in front of a subject that is not a verb: these open a clause
# that asks nothing ("als we", "dat de minister", "volgens het kabinet").
_NOT_A_VERB = frozenset(
    "als dat omdat terwijl toen voordat nadat zodat of hoewel indien doordat"
    " sinds totdat zolang zodra nu aan van bij met voor door over naar tegen"
    " richting volgens namens tussen zonder ook juist zelfs alleen dan dus en"
    " maar want ik dank".split()
)
# "Hoe meer stallingen, hoe minder fietsen op straat" compares and asks
# nothing.
_COMPARATIVES = frozenset(
    "meer minder langer korter groter kleiner sneller eerder later verder"
    " beter slechter hoger lager vaker dieper".split()
)
_WHO = r"(?:minister|staatssecretaris|kabinet|regering|bewindspersoon|premier)"
# An explicit request, wherever it stands in the quote.
_REQUEST = re.compile(
    r"\b(?:mijn|onze|de|een|deze|die) (?:eerste |tweede |laatste |volgende )?"
    r"(?:vervolg)?vra(?:ag|gen)\b"
    r"|\bvra(?:ag|gen|agt) (?:ik|wij|we|ook|nogmaals|dan|daarom|de|het|aan)\b"
    r"|\b(?:ik|wij|we) (?:vraag|vragen|verzoek|verzoeken)\b"
    r"|\bverzoek (?:ik|aan)\b"
    r"|\bvr(?:aag|oeg) (?:ik )?(?:me|mij) (?:dan |wel |ook )?af\b"
    r"|\bgraag (?:een |ook een )?(?:reactie|antwoord|toelichting|reflectie)\b"
    r"|\b(?:hoor|horen|ontvang|ontvangen|verneem|vernemen|weten) (?:ik|wij|we)?"
    r" ?(?:dan |daar |ook |wel )?graag\b"
    r"|\bgraag (?:\w+ ){0,3}(?:horen|weten|vernemen|ontvangen)\b"
    r"|\bgraag (?:hoor|verneem|ontvang|weet) (?:ik|wij|we)\b"
    r"|\bbenieuwd\b"
    r"|\btoe ?(?:te )?zeggen\b|\btoezeggen\b"
    # "kan de minister dit nader toelichten", with the start of the clause
    # lost in the transcript. Without someone who is asked, "niemand kan
    # uitleggen waarom" is a reproach.
    rf"|\b(?:{_WHO}|hij|zij|u)(?: \w+){{0,6}}"
    r" (?:aangeven|toelichten|uitleggen|bevestigen|garanderen|reflecteren"
    r"|ingaan|reageren|duiden)\b"
    # "[Is de] minister het met me eens dat": the verb in front is what the
    # transcript or the model drops first.
    rf"|\b{_WHO} het (?:\w+ ){{0,3}}eens\b"
)
_CLAUSE_END = re.compile(r"\.\.\.|[.!?…:;,]")
# Words a sentence starts with before it gets to the point.
_LEAD_IN = frozenset("en maar dus want of nou ja nee voorzitter kijk".split())


def words(text: str) -> list[str]:
    """The words of a text, without case, accents or punctuation."""
    flat = unicodedata.normalize("NFKD", text.lower())
    flat = "".join(c for c in flat if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", flat)


def _is_asked(tokens: list[str], at: int) -> bool:
    """Whether whoever is asked stands at `at`: "hij", or "de minister"."""
    return (
        at < len(tokens)
        and tokens[at] in _SUBJECTS
        or tuple(tokens[at : at + 2]) in _ADDRESSED
    )


def has_question_form(quote: str) -> bool:
    """Whether a quote itself holds a question or an explicit request.

    One of four things makes it so:

    * a question mark;
    * the words of a request: "mijn vraag", "ik verzoek", "graag een
      reactie", "kan hij toezeggen", "ik ben benieuwd", "ik hoor graag";
    * a clause that opens with a question word and then its verb ("Hoe
      gaat", "Welke stappen"), or a question word with a verb and then
      whoever is asked, anywhere ("en wat doet de minister");
    * a clause that opens with a verb and then whoever is asked ("kan de
      minister", "deelt het kabinet", "trekken we"), or with one of the
      verbs a yes/no question opens with ("Klopt het dat").

    When in doubt it says yes: a statement that slips through is no worse
    than before this check, a question that is stopped is lost.

    "Hoe" without that order of words asks nothing: "ik weet niet hoe de
    minister dat ziet", "Wat ons betreft", "Hoe de werkgevers daarmee
    omgaan verschilt". Those are how a statement comes to look like a
    question to a model.
    """
    if "?" in quote:
        return True
    if _REQUEST.search(" ".join(words(quote))):
        return True
    for clause in _CLAUSE_END.split(quote):
        tokens = words(clause)
        while tokens and tokens[0] in _LEAD_IN:
            tokens = tokens[1:]
        # "aan de minister: wil hij ..." names who is asked first.
        if tokens[:1] == ["aan"] and tuple(tokens[1:3]) in _ADDRESSED:
            tokens = tokens[3:]
        if not tokens:
            continue
        if tokens[0] in _QUESTION_WORDS and not _is_statement_opening(tokens):
            return True
        if tokens[0] in _OPENING_VERBS:
            return True
        if (
            tokens[0] not in _NOT_A_VERB
            and tokens[0] not in _QUESTION_WORDS
            and tokens[0] not in _RELATIVE_WORDS
            and _is_asked(tokens, 1)
        ):
            return True
        if any(
            (token in _QUESTION_WORDS or token in _RELATIVE_WORDS)
            and _is_asked(tokens, index + 2)
            for index, token in enumerate(tokens)
        ):
            return True
    return False


def _is_statement_opening(tokens: list[str]) -> bool:
    """Whether a clause that opens with a question word is no question.

    The verb of a question comes right behind the question word, or behind
    the noun it asks about ("Welke stappen zet"). A subject there means the
    verb comes last: "Wat de fractie betreft", "Hoe wij daarnaar kijken".
    A clause of one or two words is too little to tell, and counts as a
    question.
    """
    if len(tokens) < 3:
        return False
    if tokens[0] == "hoe" and tokens[1] in _COMPARATIVES:
        return True
    if tokens[1] == "voor":
        # "Wat voor ons de inzet is", against "Wat voor maatregelen neemt".
        return tokens[2] in _AFTER_VOOR
    return tokens[1] in _SUBJECT_STARTS
