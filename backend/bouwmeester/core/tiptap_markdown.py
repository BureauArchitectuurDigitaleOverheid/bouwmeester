"""Convert TipTap documents to the markdown `nldd-text-editor` reads and writes.

The editor keeps its document as plain markdown, so a mention has to survive as
markdown too. The design system solves that with a link carrying a scheme:

    [Anne Schuth](user:3fa9c1e2-...)

`user:` is the design system's own prefix for its built-in @-mention. Our second
mention kind (`#` for nodes and tasks) has no built-in equivalent, so it gets the
same shape with its own scheme: `node:`, `task:`. Both stay valid markdown and
both degrade to a plain link anywhere the scheme is not understood, which is the
property that makes this safe to write into a column that other code reads.

The label is escaped and the id percent-encoded for the same reason the design
system does it: a display name comes from user data, and a stray `]` or `)`
would otherwise close the link early and let the rest of the name be read as
markdown of its own.

Only used by the one-off migration; the app writes this format directly after
that. Kept in the package rather than in scripts/ so the migration and the tests
import the same code.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

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


def _escape_label(label: str) -> str:
    """Backslash-escape what would end the link text early."""
    return label.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _escape_text(text: str) -> str:
    """Escape markdown that would otherwise be read as formatting.

    Only the characters that start inline formatting, and only where they could
    plausibly do so. Over-escaping turns readable prose into a thicket of
    backslashes, which is worse than the rare false positive it prevents.
    """
    for char in ("\\", "*", "_", "`"):
        text = text.replace(char, "\\" + char)
    return text


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
            out = f"[{out}]({href})"

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
