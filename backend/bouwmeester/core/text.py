"""Tekst-helpers voor externe-bron-import."""

from __future__ import annotations

import html


def unescape_html(value: str | None) -> str | None:
    """Decode HTML-entities (&amp; -> &) uit externe-bron-tekst.

    Idempotent voor normale tekst: html.unescape() laat strings zonder
    entities ongemoeid. Veilig om bij elke import-extractie aan te roepen.
    """
    if value is None:
        return None
    return html.unescape(value)
