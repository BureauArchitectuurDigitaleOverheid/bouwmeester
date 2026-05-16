"""Text helpers for external-source import."""

from __future__ import annotations

import html


def unescape_html(value: str | None) -> str | None:
    """Decode HTML entities (&amp; -> &) from external-source text.

    Idempotent for clean text: html.unescape() leaves entity-free strings
    untouched. Safe to call at every import extraction point. Note it only
    strips one layer, which is exactly what we want for single-encoded input.
    """
    if value is None:
        return None
    return html.unescape(value)
