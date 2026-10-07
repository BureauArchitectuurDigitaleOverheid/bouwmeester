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
    " maar want ik dank verzoekt".split()
)
# A word that ends like a verb and is none, in front of "de" or "het".
_NOT_A_VERB_EITHER = frozenset(
    "niet het wat net echt eerst laat laten tot met tussen binnen buiten tegen"
    " boven beneden omtrent gezien gegeven even misschien bovendien sindsdien"
    " intussen ondertussen morgen gisteren mensen leden allen velen sommigen"
    " eigen recht slecht".split()
)
# What a clause that opens with its verb goes on with when the subject is
# not who is asked: "krijgen de gemeenten", "betekent dit dat".
_DETERMINERS = frozenset("de het dit dat deze die er een".split())
# A preposition in front of a question word: "op welke termijn", "per
# wanneer", "met welke partijen".
_PREPOSITIONS = frozenset(
    "op per met in voor tot van aan uit over naar bij binnen onder door tegen"
    " sinds vanaf om".split()
)
# A clause that opens with one of these comes first, and the question
# behind it without a comma in the transcript: "als dat zo is trekt de
# minister het voorstel dan in".
_CONDITIONS = frozenset("als indien nu stel".split())
# With one of these in front of who is asked it is a call, not a question:
# "dan moet de minister".
_OBLIGATION = frozenset("moet moeten hoort horen dient dienen behoort".split())
# Who is spoken to, in front of the question: "minister wanneer komt".
# The bewindspersoon as "he" or "she" behind the verb. Not "wij": "als
# dat zo is zijn wij tevreden" asks nothing.
_SPOKEN_OF = frozenset("hij zij u".split())
_VOCATIVES = frozenset("minister staatssecretaris".split())
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
    # "daar hoor ik de minister graag over"
    r"|\bhoor (?:ik|wij|we) (?:\w+ ){0,4}graag\b"
    # "ik wil weten of", "ik zou de minister willen vragen om"
    r"|\b(?:wil|wou|zou|willen|zouden) (?:\w+ ){0,6}"
    r"(?:vragen|weten|horen|verzoeken)\b"
    # "daar wil ik een reactie op", "een reactie van de minister graag"
    r"|\b(?:wil|graag|krijg|hoor|vraag)(?: \w+){0,6} reactie\b"
    r"|\breactie(?: \w+){0,5} graag\b"
    r"|\b(?:wil|graag|vraag|verwacht)(?: \w+){0,5} toezegging\b"
    # "ik roep de minister op om met een plan te komen". A call by the
    # codebook, and left to the model: it asks for something by name.
    rf"|\b(?:roep|roepen) (?:\w+ ){{0,2}}{_WHO} (?:\w+ ){{0,2}}op\b"
    # "misschien kan de minister daar iets over zeggen": the verb in front
    # of who is asked, wherever in the clause.
    r"|\b(?:kan|kunnen|wil|willen|zou|zouden|zal|zullen)"
    rf" (?:de|het|deze|dit) {_WHO}\b"
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
# Not the three dots: those are a subtitle line that runs on.
_SENTENCE_END = re.compile(r"(?<!\.)[.!?](?!\.)|…")
# Words a sentence starts with before it gets to the point.
_LEAD_IN = frozenset("en maar dus want of nou ja nee voorzitter kijk".split())


def words(text: str) -> list[str]:
    """The words of a text, without case, accents or punctuation."""
    flat = unicodedata.normalize("NFKD", text.lower())
    flat = "".join(c for c in flat if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", flat)


def _clauses(quote: str) -> list[tuple[str, bool]]:
    """The clauses of a quote, each with whether a sentence begins there."""
    found: list[tuple[str, bool]] = []
    for sentence in _SENTENCE_END.split(quote):
        for i, clause in enumerate(_CLAUSE_END.split(sentence)):
            found.append((clause, i == 0))
    return found


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
    for clause, first in _clauses(quote):
        tokens = words(clause)
        while tokens and tokens[0] in _LEAD_IN:
            tokens = tokens[1:]
        # "aan de minister: wil hij ..." names who is asked first.
        if tokens[:1] == ["aan"] and tuple(tokens[1:3]) in _ADDRESSED:
            tokens = tokens[3:]
        while tokens and tokens[0] in _VOCATIVES:
            tokens = tokens[1:]
        if not tokens:
            continue
        if tokens[0] in _QUESTION_WORDS and not _is_statement_opening(tokens):
            return True
        if (
            tokens[0] in _PREPOSITIONS
            and tokens[1:2]
            and (
                tokens[1] in _QUESTION_WORDS and tokens[1] not in ("wat", "waar", "hoe")
            )
        ):
            return True
        # Only where a sentence begins. Behind a comma the verb comes
        # first in a statement too: "omdat het kabinet niets deed, zitten
        # de gemeenten met de kosten".
        if first and (_opens_with_a_verb(tokens) or _asks_behind_a_condition(tokens)):
            return True
        if tokens[0] in _OPENING_VERBS:
            return True
        if (
            tokens[0] not in _NOT_A_VERB
            and tokens[0] not in _NOT_A_VERB_EITHER
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


def _opens_with_a_verb(tokens: list[str]) -> bool:
    """Whether a clause opens with a verb and then a subject nobody listed.

    "Krijgen de gemeenten daar geld voor", "betekent dit dat de regeling
    stopt". A Dutch statement does not open with its verb, so the order is
    the question. What a verb is, is guessed from how the word ends; a
    wrong guess lets a statement through, which the model had marked.
    """
    if len(tokens) < 3 or tokens[1] not in _DETERMINERS:
        return False
    first = tokens[0]
    if first in _NOT_A_VERB or first in _NOT_A_VERB_EITHER or first in _OBLIGATION:
        return False
    if first in _QUESTION_WORDS or first in _RELATIVE_WORDS:
        return False
    return len(first) > 3 and first.endswith(("t", "en"))


def _asks_behind_a_condition(tokens: list[str]) -> bool:
    """Whether a clause that opens with a condition goes on to ask.

    "Als dat zo is trekt de minister het voorstel dan in": the transcript
    has no comma where the question begins.
    """
    if tokens[0] not in _CONDITIONS:
        return False
    return any(
        (tuple(tokens[i + 1 : i + 3]) in _ADDRESSED or tokens[i + 1] in _SPOKEN_OF)
        and tokens[i] not in _NOT_A_VERB
        and tokens[i] not in _OBLIGATION
        for i in range(2, len(tokens) - 1)
    )
