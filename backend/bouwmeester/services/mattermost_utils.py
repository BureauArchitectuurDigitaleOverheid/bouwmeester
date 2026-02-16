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


def escape_mattermost_md(text: str) -> str:
    """Escape Mattermost markdown special characters in user-controlled text."""
    return text.translate(_MM_ESCAPE_CHARS)
