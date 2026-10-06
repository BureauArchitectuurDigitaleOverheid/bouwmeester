"""Changes to try out without touching production code.

Two kinds, both applied from the outside:

* A *prompt variant* rewrites the prompt production built, on its way to
  the model. It hooks onto a heading that is in the production prompt and
  fails loudly when that heading is gone, so a variant never silently does
  nothing after the prompt changed.
* A *check* is a rule on a quote that the code could apply to what the
  model answered. Here it is applied when scoring a saved run, so its
  effect can be measured without asking the model again.

Nothing in here is used by the application. What proves its worth goes
into `prompts.py` and `debat_vraag_service.py` by hand.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from .scoring import words

ANCHOR = "## Wat verder niet telt\n"

IN_THE_QUOTE = (
    "## De vraag staat in het citaat\n"
    "Een vraag telt alleen als de spreker hem stelt. In het citaat moeten de"
    " woorden staan waarmee de spreker iets vraagt: een vraagzin"
    ' ("Kan de minister", "Hoe", "Waarom", "Is het kabinet bereid") of een'
    ' uitdrukkelijk verzoek ("ik vraag de minister", "graag een reactie",'
    ' "ik hoor graag"). Maak van een bewering geen vraag. "Niemand kan'
    ' zeggen waar dat bedrag op is gebaseerd" is een verwijt en geen vraag,'
    " ook al kun je er een goede vraag van maken. Hetzelfde geldt voor"
    ' "dat is ons nooit uitgelegd", "het is mij niet duidelijk'
    ' hoe" en "de grote vraag is of". Kun je in het citaat niet de woorden'
    " aanwijzen waarmee de spreker vraagt, markeer dan niets.\n\n"
)

ABOUT_IS_NOT_TO = (
    "## Over het kabinet is niet aan het kabinet\n"
    "Dat het kabinet, de minister of de staatssecretaris in een zin"
    " voorkomt, maakt het nog geen vraag aan hen. Niet markeren:\n"
    '- wat de spreker over het kabinet zegt of vindt ("het kabinet kiest'
    ' hier niet voor", "de minister was daar zuinig over");\n'
    "- wat de spreker tegen een ander Kamerlid over het kabinet zegt"
    ' ("laten we het kabinet daarvan proberen te overtuigen");\n'
    '- een oproep zonder vraag ("het kabinet moet hiermee stoppen", "ik'
    ' hoop dat de minister dat doet");\n'
    '- een vraag die de spreker eerder stelde en nu navertelt ("ik heb de'
    ' minister toen gevraagd of").\n\n'
)


class VariantError(RuntimeError):
    pass


def _before_anchor(prompt: str, addition: str) -> str:
    if prompt.count(ANCHOR) != 1:
        raise VariantError(
            "The production prompt no longer has the heading this variant"
            f" hooks onto: {ANCHOR.strip()!r}"
        )
    return prompt.replace(ANCHOR, addition + ANCHOR)


PROMPT_VARIANTS: dict[str, Callable[[str], str]] = {
    "productie": lambda prompt: prompt,
    "vraag-in-citaat": lambda prompt: _before_anchor(prompt, IN_THE_QUOTE),
    "over-is-niet-aan": lambda prompt: _before_anchor(prompt, ABOUT_IS_NOT_TO),
    "beide": lambda prompt: _before_anchor(prompt, IN_THE_QUOTE + ABOUT_IS_NOT_TO),
}


# --- checks on a quote -------------------------------------------------

# Words a Dutch question starts with.
_QUESTION_WORDS = frozenset(
    "hoe wat waarom wanneer welke welk wie waar hoeveel hoelang".split()
)
# These open a relative clause as often as a question ("een wet waardoor
# de minister ..."), so they only count with a verb and whoever is asked.
_RELATIVE_WORDS = frozenset("waarop waarmee waarvan waarvoor waardoor".split())
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
    }
)
# A word in front of a subject that is not a verb: these open a clause
# that asks nothing ("als we", "dat de minister", "volgens het kabinet").
_NOT_A_VERB = frozenset(
    "als dat omdat terwijl toen voordat nadat zodat of hoewel indien doordat"
    " sinds totdat zolang zodra nu aan van bij met voor door over naar tegen"
    " richting volgens namens tussen zonder ook juist zelfs alleen dan dus en"
    " maar want ik".split()
)
# An explicit request, wherever it stands in the quote.
_REQUEST = re.compile(
    r"\b(?:mijn|onze|de|een|deze|die) (?:eerste |tweede |laatste |volgende )?"
    r"(?:vervolg)?vra(?:ag|gen)\b"
    r"|\bvra(?:ag|gen|agt) (?:ik|wij|we|ook|nogmaals|dan|daarom|de|het|aan)\b"
    r"|\b(?:ik|wij|we) (?:vraag|vragen)\b"
    r"|\bvr(?:aag|oeg) (?:ik )?(?:me|mij) (?:dan |wel |ook )?af\b"
    r"|\bgraag (?:een |ook een )?(?:reactie|antwoord|toelichting|reflectie)\b"
    r"|\b(?:hoor|horen|ontvang|ontvangen|verneem|vernemen|weten) (?:ik|wij|we)?"
    r" ?(?:dan |daar |ook |wel )?graag\b"
    r"|\bgraag (?:\w+ ){0,3}(?:horen|weten|vernemen|ontvangen)\b"
    r"|\bbenieuwd\b"
    r"|\btoe ?(?:te )?zeggen\b|\btoezeggen\b"
    # "kan de minister dit nader toelichten", with the start of the clause
    # lost in the transcript. Without someone who is asked, "niemand kan
    # uitleggen waarom" is a reproach.
    r"|\b(?:minister|staatssecretaris|kabinet|regering|hij|zij|u)(?: \w+){0,6}"
    r" (?:aangeven|toelichten|uitleggen|bevestigen|garanderen|reflecteren"
    r"|ingaan|reageren|duiden)\b"
)
_CLAUSE_END = re.compile(r"\.\.\.|[.!?…:;,]")
# Words a sentence starts with before it gets to the point.
_LEAD_IN = frozenset("en maar dus want of nou ja nee voorzitter kijk".split())


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
    * the words of a request: "mijn vraag", "graag een reactie", "kan hij
      toezeggen", "ik ben benieuwd";
    * a clause that opens with a question word ("Hoe"), or a question word
      with a verb and then whoever is asked ("wat doet de minister");
    * a clause that opens with a verb and then whoever is asked ("kan de
      minister", "deelt het kabinet", "trekken we"), or with one of the
      verbs a yes/no question opens with ("Klopt het dat").

    When in doubt it says yes: a statement that slips through is no worse
    than today, a question that is stopped is lost.

    The transcript puts full stops where question marks belong, so the mark
    alone is not enough. "Hoe" in the middle of a clause without that
    inversion ("ik weet niet hoe de minister dat ziet") asks nothing.
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
        if tokens[0] in _QUESTION_WORDS or tokens[0] in _OPENING_VERBS:
            return True
        if tokens[0] not in _NOT_A_VERB and _is_asked(tokens, 1):
            return True
        if any(
            (token in _QUESTION_WORDS or token in _RELATIVE_WORDS)
            and _is_asked(tokens, index + 2)
            for index, token in enumerate(tokens)
        ):
            return True
    return False


_MOTION = re.compile(
    r"\bverzoekt de (?:regering|minister|staatssecretaris)\b"
    r"|\bgaat over tot de orde van de dag\b"
    r"|\bgehoord de beraadslaging\b"
    r"|\b(?:overwegende|constaterende) dat\b"
)


def is_motion_text(quote: str) -> bool:
    """Whether a quote is the text of a motion being read out.

    "Verzoekt de regering" is a request to the cabinet in form, and a motie
    in kind: it gets an oordeel, not an answer.
    """
    return bool(_MOTION.search(" ".join(words(quote))))


CHECKS: dict[str, Callable[[str], bool]] = {
    "vraagvorm": has_question_form,
    "geen-motietekst": lambda quote: not is_motion_text(quote),
    "vraagvorm+geen-motietekst": lambda quote: (
        has_question_form(quote) and not is_motion_text(quote)
    ),
}
