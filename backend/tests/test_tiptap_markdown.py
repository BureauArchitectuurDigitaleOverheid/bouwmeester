"""Tests for the TipTap -> markdown conversion.

This rewrites real descriptions, so the cases that matter are the ones where a
wrong conversion is invisible afterwards: a mention that loses its id, a name
that breaks out of its link, and a value that was never TipTap being mangled
anyway.
"""

import json
import re

from bouwmeester.core.tiptap_markdown import (
    extract_markdown_mentions,
    tiptap_to_markdown,
)
from bouwmeester.services.mention_service import MentionService


def doc(*content: dict) -> str:
    return json.dumps({"type": "doc", "content": list(content)})


def para(*content: dict) -> dict:
    return {"type": "paragraph", "content": list(content)}


def text(value: str, *marks: str) -> dict:
    node: dict = {"type": "text", "text": value}
    if marks:
        node["marks"] = [{"type": m} for m in marks]
    return node


class TestPassThrough:
    """Anything that is not a TipTap document comes back untouched."""

    def test_plain_text_is_unchanged(self):
        assert (
            tiptap_to_markdown("Gewoon een beschrijving.") == "Gewoon een beschrijving."
        )

    def test_markdown_is_unchanged(self):
        value = "# Kop\n\nMet **vet** erin."
        assert tiptap_to_markdown(value) == value

    def test_none_and_empty_are_unchanged(self):
        assert tiptap_to_markdown(None) is None
        assert tiptap_to_markdown("") == ""

    def test_json_that_is_not_a_doc_is_unchanged(self):
        value = '{"foo": "bar"}'
        assert tiptap_to_markdown(value) == value

    def test_broken_json_is_unchanged(self):
        value = '{"type": "doc", oops'
        assert tiptap_to_markdown(value) == value


class TestInline:
    def test_paragraphs_are_separated_by_a_blank_line(self):
        assert (
            tiptap_to_markdown(doc(para(text("Een")), para(text("Twee"))))
            == "Een\n\nTwee"
        )

    def test_marks(self):
        assert tiptap_to_markdown(doc(para(text("vet", "bold")))) == "**vet**"
        assert tiptap_to_markdown(doc(para(text("schuin", "italic")))) == "*schuin*"
        assert tiptap_to_markdown(doc(para(text("weg", "strike")))) == "~~weg~~"

    def test_code_wins_over_emphasis(self):
        # Inside code, `**` is literal, so applying both would render asterisks.
        assert tiptap_to_markdown(doc(para(text("x = 1", "code", "bold")))) == "`x = 1`"

    def test_code_containing_a_backtick_gets_a_longer_fence(self):
        assert tiptap_to_markdown(doc(para(text("a ` b", "code")))) == "``a ` b``"

    def test_link_mark(self):
        node = {
            "type": "text",
            "text": "Rijksoverheid",
            "marks": [{"type": "link", "attrs": {"href": "https://rijksoverheid.nl"}}],
        }
        assert (
            tiptap_to_markdown(doc(para(node)))
            == "[Rijksoverheid](https://rijksoverheid.nl)"
        )

    def test_markdown_characters_in_plain_text_are_escaped(self):
        # Otherwise a description mentioning *.py would come back italicised.
        assert tiptap_to_markdown(doc(para(text("kosten * 2")))) == "kosten \\* 2"

    def test_hard_break(self):
        result = tiptap_to_markdown(
            doc(para(text("een"), {"type": "hardBreak"}, text("twee")))
        )
        assert result == "een  \ntwee"


class TestMentions:
    """The part with no second chance: an id lost here cannot be recovered."""

    def test_person_mention_keeps_its_id(self):
        node = {
            "type": "mention",
            "attrs": {
                "id": "3fa9c1e2",
                "label": "Anne Schuth",
                "mentionType": "person",
            },
        }
        assert tiptap_to_markdown(doc(para(node))) == "[@Anne Schuth](user:3fa9c1e2)"

    def test_organisatie_mention_gets_its_own_scheme(self):
        node = {
            "type": "mention",
            "attrs": {"id": "abc", "label": "BZK", "mentionType": "organisatie"},
        }
        assert tiptap_to_markdown(doc(para(node))) == "[@BZK](org:abc)"

    def test_node_and_task_hashtags(self):
        node = {
            "type": "hashtagMention",
            "attrs": {"id": "n1", "label": "Dossier", "mentionType": "node"},
        }
        task = {
            "type": "hashtagMention",
            "attrs": {"id": "t1", "label": "Taak", "mentionType": "task"},
        }
        assert tiptap_to_markdown(doc(para(node))) == "[#Dossier](node:n1)"
        assert tiptap_to_markdown(doc(para(task))) == "[#Taak](task:t1)"

    def test_mention_without_mention_type_falls_back(self):
        # Documents written before the attribute existed.
        node = {"type": "mention", "attrs": {"id": "x", "label": "Wie"}}
        assert tiptap_to_markdown(doc(para(node))) == "[@Wie](user:x)"

    def test_mention_without_id_keeps_its_text(self):
        node = {"type": "mention", "attrs": {"label": "Naamloos"}}
        assert tiptap_to_markdown(doc(para(node))) == "@Naamloos"

    def test_brackets_in_a_name_cannot_break_out_of_the_link(self):
        # A display name comes from user data; an unescaped `]` would end the
        # link text early and let the rest be read as markdown of its own.
        node = {
            "type": "mention",
            "attrs": {"id": "x", "label": "Jan] (evil) [", "mentionType": "person"},
        }
        result = tiptap_to_markdown(doc(para(node)))
        assert result == "[@Jan\\] (evil) \\[](user:x)"

    def test_id_is_percent_encoded(self):
        node = {
            "type": "mention",
            "attrs": {"id": "a b/c", "label": "X", "mentionType": "person"},
        }
        assert tiptap_to_markdown(doc(para(node))) == "[@X](user:a%20b%2Fc)"

    def test_mention_inside_a_sentence(self):
        node = {
            "type": "mention",
            "attrs": {"id": "p1", "label": "Anne", "mentionType": "person"},
        }
        result = tiptap_to_markdown(
            doc(para(text("Vraag aan "), node, text(" hierover.")))
        )
        assert result == "Vraag aan [@Anne](user:p1) hierover."


class TestBlocks:
    def test_heading(self):
        node = {"type": "heading", "attrs": {"level": 3}, "content": [text("Kop")]}
        assert tiptap_to_markdown(doc(node)) == "### Kop"

    def test_bullet_list(self):
        item = {"type": "listItem", "content": [para(text("Een"))]}
        other = {"type": "listItem", "content": [para(text("Twee"))]}
        result = tiptap_to_markdown(
            doc({"type": "bulletList", "content": [item, other]})
        )
        assert result == "- Een\n- Twee"

    def test_ordered_list_numbers_from_one(self):
        item = {"type": "listItem", "content": [para(text("Eerst"))]}
        other = {"type": "listItem", "content": [para(text("Dan"))]}
        result = tiptap_to_markdown(
            doc({"type": "orderedList", "content": [item, other]})
        )
        assert result == "1. Eerst\n2. Dan"

    def test_blockquote(self):
        node = {"type": "blockquote", "content": [para(text("Geciteerd"))]}
        assert tiptap_to_markdown(doc(node)) == "> Geciteerd"

    def test_code_block_keeps_its_language(self):
        node = {
            "type": "codeBlock",
            "attrs": {"language": "python"},
            "content": [{"type": "text", "text": "x = 1"}],
        }
        assert tiptap_to_markdown(doc(node)) == "```python\nx = 1\n```"

    def test_horizontal_rule(self):
        assert tiptap_to_markdown(doc({"type": "horizontalRule"})) == "---"

    def test_trailing_empty_paragraph_is_dropped(self):
        # TipTap keeps one where the caret was left.
        assert tiptap_to_markdown(doc(para(text("Tekst")), para())) == "Tekst"

    def test_empty_document_becomes_empty_string(self):
        assert tiptap_to_markdown(doc()) == ""

    def test_unknown_block_keeps_its_text(self):
        node = {"type": "somethingNew", "content": [para(text("Niet verliezen"))]}
        assert tiptap_to_markdown(doc(node)) == "Niet verliezen"


ANNE = "3fa9c1e2-0000-0000-0000-000000000001"
DOSSIER = "aaaa1111-0000-0000-0000-000000000002"


def mention(node_type: str, mention_type: str, id_: str, label: str) -> dict:
    return {
        "type": node_type,
        "attrs": {"id": id_, "label": label, "mentionType": mention_type},
    }


class TestMentionsSurviveTheRoundTrip:
    """What this writes, the app has to be able to read back.

    `MentionService` populates the mention table and fires the notifications.
    It clears a row's mentions before re-extracting, so a format it cannot
    parse costs that row every notification, silently.
    """

    def test_person_and_node_mentions_round_trip(self):
        source = doc(
            para(
                text("Vraag aan "),
                mention("mention", "person", ANNE, "Anne Schuth"),
                text(" over "),
                mention("hashtagMention", "node", DOSSIER, "Dossier X"),
            )
        )
        assert extract_markdown_mentions(tiptap_to_markdown(source)) == [
            {"mention_type": "person", "target_id": ANNE},
            {"mention_type": "node", "target_id": DOSSIER},
        ]

    def test_service_reads_both_storage_formats(self):
        # A row migrated to markdown and a row not yet edited since must give
        # the same answer, or notifications depend on when a row was written.
        source = doc(para(mention("mention", "person", ANNE, "Anne Schuth")))
        assert MentionService.extract_mentions(
            tiptap_to_markdown(source)
        ) == MentionService.extract_mentions(source)

    def test_label_cannot_smuggle_a_second_mention(self):
        # The label is user data. Unescaped, this ends its own link early and
        # opens one pointing at an id the author never chose.
        smuggled = "9999aaaa-0000-0000-0000-000000000009"
        source = doc(
            para(
                mention(
                    "mention",
                    "person",
                    ANNE,
                    f"A] fake](user:{smuggled}) B",
                )
            )
        )
        assert extract_markdown_mentions(tiptap_to_markdown(source)) == [
            {"mention_type": "person", "target_id": ANNE}
        ]


def _link_targets(markdown: str) -> set[str]:
    """The hrefs a markdown renderer would actually link to.

    An unescaped `]` inside link text is still a literal `](` in the output,
    so counting those says nothing. What matters is whether a second, working
    link appeared: a `]` that ends the text early, or a `)` in an href that
    closes the link. Both show up here as an extra target.

    The `<...>` form is matched first and greedily to its closing `>`, the way
    CommonMark reads it, so a `)` inside an angle-bracketed destination stays
    part of that one destination instead of looking like a new link.
    """
    pattern = r"(?<!\\)\]\((?:<([^>]*)>|([^)\s]+))\)"
    return {
        m.group(1) if m.group(1) is not None else m.group(2)
        for m in re.finditer(pattern, markdown)
    }


class TestLinksCannotBeInjected:
    """Everything inside a link is user data, so all of it is escaped."""

    def test_href_with_a_closing_paren_cannot_open_a_second_link(self):
        value = tiptap_to_markdown(
            doc(
                para(
                    {
                        "type": "text",
                        "text": "klik",
                        "marks": [
                            {
                                "type": "link",
                                "attrs": {
                                    "href": "x) [KLIK HIER](https://phish.example"
                                },
                            }
                        ],
                    }
                )
            )
        )
        # The whole href sits inside <...>, so the `)` in it no longer closes
        # the link and the attacker's URL never becomes a target of its own.
        assert value == "[klik](<x) [KLIK HIER](https://phish.example>)"
        assert not _link_targets(value) & {"https://phish.example"}

    def test_link_text_with_a_bracket_cannot_open_a_second_link(self):
        value = tiptap_to_markdown(
            doc(
                para(
                    {
                        "type": "text",
                        "text": "a](https://phish.example) [b",
                        "marks": [
                            {"type": "link", "attrs": {"href": "https://ok.example"}}
                        ],
                    }
                )
            )
        )
        # The `]` is escaped, so it cannot end the link text early; only the
        # author's own href is a target.
        assert _link_targets(value) == {"https://ok.example"}

    def test_typing_a_mention_does_not_forge_one(self):
        typed = f"[@Directeur BZK](user:{ANNE})"
        assert (
            extract_markdown_mentions(tiptap_to_markdown(doc(para(text(typed))))) == []
        )
