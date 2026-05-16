"""Tests voor de unescape_html-helper."""

from __future__ import annotations

import pytest

from bouwmeester.core.text import unescape_html


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "Directie Ambtenaar &amp; Organisatie (A&amp;O)",
            "Directie Ambtenaar & Organisatie (A&O)",
        ),
        ("&quot;quoted&quot;", '"quoted"'),
        ("d&#39;Hondt", "d'Hondt"),
        ("Caf&eacute;", "Café"),
        # Idempotent: al-schone tekst blijft ongemoeid.
        (
            "Directie Ambtenaar & Organisatie (A&O)",
            "Directie Ambtenaar & Organisatie (A&O)",
        ),
        ("gewone naam zonder entities", "gewone naam zonder entities"),
        ("", ""),
    ],
)
def test_unescape_html(raw: str, expected: str) -> None:
    assert unescape_html(raw) == expected


def test_unescape_html_none_passthrough() -> None:
    assert unescape_html(None) is None
