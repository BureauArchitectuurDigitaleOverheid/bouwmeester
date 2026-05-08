"""Minimal Markdown to HTML converter for the lead-update mail body.

We intentionally do NOT pull in a full Markdown parser. The LLM only emits
paragraphs, ``-`` bullet lists and ``**bold**`` per the prompt; anything more
ornate would also raise the visual surface for issues in Outlook anyway.
"""

import html
import re


def markdown_to_html(text: str) -> str:
    if not text:
        return ""

    # Split into paragraph blocks separated by blank lines.
    blocks = re.split(r"\n\s*\n", text.strip())
    out: list[str] = []
    for block in blocks:
        lines = [ln.rstrip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        if all(_is_bullet(ln) for ln in lines):
            items = "".join(
                f"<li>{_inline(ln.lstrip('-* ').strip())}</li>" for ln in lines
            )
            out.append(f"<ul>{items}</ul>")
        else:
            joined = "<br>".join(_inline(ln) for ln in lines)
            out.append(f"<p>{joined}</p>")

    return "\n".join(out)


def _is_bullet(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("- ") or stripped.startswith("* ")


def _inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    return escaped
