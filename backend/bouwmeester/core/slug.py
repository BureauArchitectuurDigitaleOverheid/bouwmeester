"""Slug generation and validation."""

import re
import unicodedata

# Reserved words that cannot be used as slugs (collide with routes / system).
RESERVED_SLUGS: frozenset[str] = frozenset(
    {
        "api",
        "auth",
        "admin",
        "c",
        "i",
        "public",
        "health",
        "static",
        "assets",
        "login",
        "logout",
        "callback",
        "webauthn",
        "mattermost",
        "new",
        "edit",
    }
)

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """Turn an arbitrary string into a slug.

    Lowercases, strips diacritics, replaces non-alphanumerics with hyphens,
    and collapses repeats. Returns an empty string if nothing remains.
    """
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower()
    hyphenated = _NON_ALNUM.sub("-", lowered)
    return hyphenated.strip("-")


def is_valid_slug(slug: str) -> bool:
    """A slug is valid if it matches the pattern and isn't reserved."""
    if not slug:
        return False
    if slug in RESERVED_SLUGS:
        return False
    return bool(_SLUG_PATTERN.match(slug))
