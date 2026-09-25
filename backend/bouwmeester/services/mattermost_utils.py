"""Shared utilities for the Mattermost integration."""

# Characters that have special meaning in Mattermost markdown.
_MM_ESCAPE_CHARS = str.maketrans(
    {
        "[": "\\[",
        "]": "\\]",
        "(": "\\(",
        ")": "\\)",
        "@": "\\@",
        "~": "\\~",
        "*": "\\*",
        "_": "\\_",
        "`": "\\`",
        "#": "\\#",
        "|": "\\|",
    }
)


# Dezelfde tekens, zonder de haakjes. Haakjes hebben in Mattermost alleen
# betekenis direct ná een `]` — dus in linktekst. In gewone prozatekst
# leveren ze niets op behalve zichtbare backslashes, en die stonden in
# productie in een samenvatting: "Meerdere fracties \(D66, VVD\) stellen".
#
# Een aparte tabel en niet de bestaande aanpassen, omdat de strikte vorm
# nog nodig is voor tekst die tússen `[` en `]` belandt.
_MM_ESCAPE_PROZA = str.maketrans(
    {
        "[": "\\[",
        "]": "\\]",
        "@": "\\@",
        "~": "\\~",
        "*": "\\*",
        "_": "\\_",
        "`": "\\`",
        "#": "\\#",
        "|": "\\|",
    }
)


def escape_mattermost_prose(text: str) -> str:
    """Escape voor lopende tekst, waar haakjes gewoon haakjes zijn.

    Voor linktekst (alles wat tussen `[` en `]` komt) hoort
    `escape_mattermost_md`, want daar maakt een haakje wél verschil.
    """
    return text.translate(_MM_ESCAPE_PROZA)


def escape_mattermost_md(text: str) -> str:
    """Escape Mattermost markdown special characters in user-controlled text."""
    return text.translate(_MM_ESCAPE_CHARS)
