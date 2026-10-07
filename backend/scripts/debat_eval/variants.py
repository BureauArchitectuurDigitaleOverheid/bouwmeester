"""Changes to try out without touching production code.

Two kinds, both applied from the outside:

* A *prompt variant* rewrites the prompt production built, on its way to
  the model. It hooks onto a heading that is in the production prompt and
  fails loudly when that heading is gone, so a variant never silently does
  nothing after the prompt changed.
* A *check* is a rule on a quote that the code could apply to what the
  model answered. Here it is applied when scoring a saved run, so its
  effect can be measured without asking the model again.

What proved its worth has moved. The two paragraphs that were tried here
first are in `prompts.py`, and the two checks are in `lees_antwoord`
(`debat_vraag_vorm.has_question_form`, `debat_motie.is_motion_text`). The
checks are still listed here, taken from production, to score a run that
was saved before they were: that is what "before" and "after" on the same
answers of the model are compared with.
"""

from __future__ import annotations

from collections.abc import Callable

from bouwmeester.services.debat_motie import is_motion_text
from bouwmeester.services.debat_vraag_vorm import has_question_form

__all__ = [
    "ANCHOR",
    "CHECKS",
    "PROMPT_VARIANTS",
    "VariantError",
    "before_anchor",
    "has_question_form",
    "is_motion_text",
]

ANCHOR = "## Wat verder niet telt\n"


class VariantError(RuntimeError):
    pass


def before_anchor(prompt: str, addition: str) -> str:
    """The prompt with a paragraph put in front of the heading `ANCHOR`."""
    if prompt.count(ANCHOR) != 1:
        raise VariantError(
            "The production prompt no longer has the heading this variant"
            f" hooks onto: {ANCHOR.strip()!r}"
        )
    return prompt.replace(ANCHOR, addition + ANCHOR)


# A new wording to try goes in here, as
# `"naam": lambda prompt: before_anchor(prompt, TEXT)`.
PROMPT_VARIANTS: dict[str, Callable[[str], str]] = {
    "productie": lambda prompt: prompt,
}


CHECKS: dict[str, Callable[[str], bool]] = {
    "vraagvorm": has_question_form,
    "geen-motietekst": lambda quote: not is_motion_text(quote),
    "vraagvorm+geen-motietekst": lambda quote: (
        has_question_form(quote) and not is_motion_text(quote)
    ),
}
