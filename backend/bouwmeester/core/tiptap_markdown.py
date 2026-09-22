"""Convert TipTap documents to the markdown `nldd-text-editor` reads and writes.

The editor keeps its document as plain markdown, so a mention has to survive as
markdown too. The design system solves that with a link carrying a scheme:

    [Anne Schuth](user:3fa9c1e2-...)

`user:` is the design system's own prefix for its built-in @-mention. Our second
mention kind (`#` for nodes and tasks) has no built-in equivalent, so it gets the
same shape with its own scheme: `node:`, `task:`. Both stay valid markdown and
both degrade to a plain link anywhere the scheme is not understood, which is the
property that makes this safe to write into a column that other code reads.

Everything that ends up inside a link is escaped, because all of it comes from
user data: the mention label, ordinary text, and the href. A stray `]` or `)`
closes a link early and turns the rest into markdown of its own, which is how a
second, attacker-controlled link gets into someone else's description. Plain
text is escaped for `[` and `]` too, so that typing the literal string
`[@Directeur BZK](user:0000...)` cannot forge a mention this converter never
wrote.

`extract_markdown_mentions` reads the same format back out, so the two sides of
it live in one module and cannot drift apart.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote, unquote

# Mention node type -> URL scheme. The `mentionType` attribute distinguishes
# person from organisatie within one TipTap node type, so the mapping is on the
# pair rather than on the node type alone.
_MENTION_SCHEMES = {
    ("mention", "person"): "user",
    ("mention", "organisatie"): "org",
    ("hashtagMention", "node"): "node",
    ("hashtagMention", "task"): "task",
}

# Defaults for documents written before `mentionType` existed.
_DEFAULT_MENTION_TYPE = {"mention": "person", "hashtagMention": "node"}

# URL scheme -> the `mention_type` the mention table stores, i.e. the inverse of
# the values in _MENTION_SCHEMES above. Used when reading the markdown back.
_SCHEME_MENTION_TYPES = {
    "user": "person",
    "org": "organisatie",
    "node": "node",
    "task": "task",
}

# The shape `_mention_to_markdown` writes, as a pattern. An escaped `\[` inside
# the label cannot end it, which keeps a label containing brackets from being
# read as a shorter mention followed by loose text.
_MENTION_PATTERN = re.compile(
    r"\[[@#]((?:\\.|[^\\\]])*)\]\((user|org|node|task):([^)\s]+)\)"
)


def _escape_label(label: str) -> str:
    """Backslash-escape what would end the link text early."""
    return label.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _escape_text(text: str) -> str:
    """Escape markdown that would otherwise be read as formatting.

    `[` and `]` are in the set because leaving them out was an injection hole,
    not because prose needs them escaped. Without it, a description containing
    the literal text `[@Directeur BZK](user:0000...)` came through verbatim and
    was indistinguishable from a mention this converter wrote, which is a way
    to forge one in someone else's text. The same gap let link text carrying
    `](...)` close its own link early and open a second one.

    Over-escaping turns readable prose into a thicket of backslashes, so the
    set stays as small as it can be while closing that off.
    """
    for char in ("\\", "*", "_", "`", "[", "]"):
        text = text.replace(char, "\\" + char)
    return text


def _escape_href(href: str) -> str:
    """Make a URL safe to sit inside `](...)`.

    An href arrives straight from pasted user content (TipTap's Link extension
    has `linkOnPaste` and `autolink` on), so a `)` in it closed the link early
    and let the rest be read as markdown: `x) [KLIK HIER](https://phish.nl`
    produced a second, attacker-controlled link. Angle brackets are the
    markdown-native way to wrap a URL with delimiters in it, so anything
    awkward goes inside them, with `<` and `>` themselves percent-encoded so
    the wrapper cannot be closed early either.
    """
    if not href:
        return ""
    cleaned = href.replace("<", "%3C").replace(">", "%3E")
    if any(char in cleaned for char in "() \t\n"):
        return f"<{cleaned}>"
    return cleaned


def _mention_to_markdown(node: dict[str, Any]) -> str:
    attrs = node.get("attrs") or {}
    label = str(attrs.get("label") or "")
    node_id = attrs.get("id")
    mention_type = attrs.get("mentionType") or _DEFAULT_MENTION_TYPE.get(node["type"])
    scheme = _MENTION_SCHEMES.get((node["type"], mention_type))

    sigil = "#" if node["type"] == "hashtagMention" else "@"

    # Without an id there is nothing to link to; keep the visible text so the
    # sentence still reads, rather than dropping it.
    if not node_id or not scheme:
        return f"{sigil}{label}"

    return f"[{sigil}{_escape_label(label)}]({scheme}:{quote(str(node_id), safe='')})"


def _marks_to_markdown(text: str, marks: list[dict[str, Any]] | None) -> str:
    """Wrap `text` in the markdown for its marks, innermost first.

    `code` wins over the others: its content is literal, so emphasis inside it
    is not emphasis. TipTap can still carry both, and writing `**`+backtick
    would render the asterisks rather than apply them.
    """
    if not marks:
        return _escape_text(text)

    kinds = {m.get("type") for m in marks}

    if "code" in kinds:
        # Inside code the escaping must not happen: a backslash is a backslash.
        fence = "`"
        while fence in text:
            fence += "`"
        pad = " " if text.startswith("`") or text.endswith("`") else ""
        return f"{fence}{pad}{text}{pad}{fence}"

    out = _escape_text(text)
    if "bold" in kinds:
        out = f"**{out}**"
    if "italic" in kinds:
        out = f"*{out}*"
    if "strike" in kinds:
        out = f"~~{out}~~"

    link = next((m for m in marks if m.get("type") == "link"), None)
    if link:
        href = (link.get("attrs") or {}).get("href")
        if href:
            out = f"[{out}]({_escape_href(href)})"

    return out


def _inline_to_markdown(nodes: list[dict[str, Any]] | None) -> str:
    if not nodes:
        return ""
    parts: list[str] = []
    for node in nodes:
        kind = node.get("type")
        if kind == "text":
            parts.append(_marks_to_markdown(node.get("text") or "", node.get("marks")))
        elif kind in ("mention", "hashtagMention"):
            parts.append(_mention_to_markdown(node))
        elif kind == "hardBreak":
            # Two trailing spaces is the markdown line break, and it survives a
            # round trip where a bare newline would be folded into the paragraph.
            parts.append("  \n")
        else:
            # An unknown inline node: keep whatever text hangs under it rather
            # than silently dropping a sentence.
            parts.append(_inline_to_markdown(node.get("content")))
    return "".join(parts)


def _block_to_markdown(node: dict[str, Any], depth: int = 0) -> list[str]:
    kind = node.get("type")
    content = node.get("content") or []
    attrs = node.get("attrs") or {}

    if kind == "paragraph":
        return [_inline_to_markdown(content)]

    if kind == "heading":
        level = int(attrs.get("level") or 2)
        return [f"{'#' * max(1, min(level, 6))} {_inline_to_markdown(content)}"]

    if kind == "blockquote":
        inner: list[str] = []
        for child in content:
            inner.extend(_block_to_markdown(child, depth))
        return ["\n".join(f"> {line}" if line else ">" for line in inner)]

    if kind == "codeBlock":
        language = attrs.get("language") or ""
        body = "".join(child.get("text") or "" for child in content)
        return [f"```{language}\n{body}\n```"]

    if kind == "horizontalRule":
        return ["---"]

    if kind in ("bulletList", "orderedList"):
        lines: list[str] = []
        for index, item in enumerate(content, start=1):
            marker = f"{index}." if kind == "orderedList" else "-"
            item_blocks: list[str] = []
            for child in item.get("content") or []:
                item_blocks.extend(_block_to_markdown(child, depth + 1))
            if not item_blocks:
                item_blocks = [""]
            indent = "  " * depth
            lines.append(f"{indent}{marker} {item_blocks[0]}")
            # Continuation lines of the same item line up under its text.
            for extra in item_blocks[1:]:
                pad = indent + " " * (len(marker) + 1)
                lines.extend(f"{pad}{line}" for line in extra.split("\n"))
        return ["\n".join(lines)]

    # Anything unrecognised: fall through to its children so no text is lost.
    blocks: list[str] = []
    for child in content:
        blocks.extend(_block_to_markdown(child, depth))
    return blocks


def tiptap_to_markdown(value: str | None) -> str | None:
    """Convert one stored value.

    Returns the value unchanged when it is not a TipTap document, so this is
    safe to run over a column holding a mix of JSON, markdown and plain text:
    only the JSON is rewritten.
    """
    if value is None or value == "":
        return value

    stripped = value.lstrip()
    if not stripped.startswith("{"):
        return value

    try:
        doc = json.loads(value)
    except (ValueError, TypeError):
        return value

    if not isinstance(doc, dict) or doc.get("type") != "doc":
        return value

    blocks: list[str] = []
    for node in doc.get("content") or []:
        blocks.extend(_block_to_markdown(node))

    # Drop trailing empties: TipTap keeps an empty paragraph where a user left
    # the caret, which would become stray blank lines.
    while blocks and not blocks[-1].strip():
        blocks.pop()

    return "\n\n".join(blocks)


def _code_spans(value: str) -> list[tuple[int, int]]:
    """Character ranges covered by a fenced block or an inline code span.

    Text carrying the `code` mark is written through verbatim, without the
    escaping every other run gets, because inside code a backslash has to stay
    a backslash. That leaves one hole: a user who types the literal text of a
    mention and marks it as code produces a run that `_MENTION_PATTERN` cannot
    tell from one this module wrote, and the mention lands on whichever id they
    typed. Code is quoted text, never a link, so these ranges are skipped.

    Fences are matched first: a lone backtick inside a fenced block opens no
    inline span.
    """
    spans: list[tuple[int, int]] = []
    for match in re.finditer(r"^(`{3,})[^\n]*\n.*?^\1[^\S\n]*$", value, re.S | re.M):
        spans.append(match.span())

    def in_fence(pos: int) -> bool:
        return any(start <= pos < end for start, end in spans)

    for match in re.finditer(r"(`+)(?!`).*?(?<!`)\1(?!`)", value, re.S):
        if not in_fence(match.start()):
            spans.append(match.span())
    return spans


def extract_markdown_mentions(value: str | None) -> list[dict[str, str]]:
    """Read the mentions back out of the markdown form.

    The inverse of `_mention_to_markdown`. Returns dicts of `mention_type` and
    `target_id` in document order, the same shape `MentionService` builds the
    mention table from.

    Anything inside code is quoted, not linked, so it yields no mentions: see
    `_code_spans`.
    """
    if not value:
        return []

    skip = _code_spans(value)

    mentions: list[dict[str, str]] = []
    for match in _MENTION_PATTERN.finditer(value):
        if any(start <= match.start() < end for start, end in skip):
            continue
        mention_type = _SCHEME_MENTION_TYPES.get(match.group(2))
        if mention_type:
            mentions.append(
                {"mention_type": mention_type, "target_id": unquote(match.group(3))}
            )
    return mentions
