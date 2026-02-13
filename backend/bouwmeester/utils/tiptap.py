"""Extract plain text from TipTap/ProseMirror JSON."""

from __future__ import annotations

import json
from typing import Any


def tiptap_to_plain(value: str | None) -> str | None:
    """Convert a TipTap JSON string to plain text.

    Returns the original string unchanged if it is not TipTap JSON.
    Returns None if value is None.
    """
    if value is None:
        return None
    try:
        doc = json.loads(value)
        if isinstance(doc, dict) and doc.get("type") == "doc":
            return _extract_text(doc).strip() or None
    except (json.JSONDecodeError, TypeError):
        pass
    return value


def _extract_text(node: dict[str, Any]) -> str:
    """Recursively extract text content from a TipTap node tree."""
    if "text" in node:
        return node["text"]
    if node.get("type") in ("mention", "hashtagMention"):
        label = (node.get("attrs") or {}).get("label", "")
        return str(label)
    content = node.get("content")
    if not content:
        return ""
    sep = " " if node.get("type") == "paragraph" else ""
    return sep.join(_extract_text(child) for child in content)
