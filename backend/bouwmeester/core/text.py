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


# Prefixes that different sources add or drop for the same organisational
# unit. organogram.overheid.nl lists "Digitalisering en Overheidsorganisatie"
# where the seed has "DG Digitalisering en Overheidsorganisatie"; TOOI uses
# "Ministerie van ..." where a scrape may not. Stripping these before
# comparison lets cross-source matching find the same unit.
_ORG_NAME_PREFIXES = (
    "ministerie van ",
    "directoraat-generaal ",
    "directoraat generaal ",
    "dg ",
    "directie ",
    "afdeling ",
    "agentschap ",
    "zbo ",
    "stichting ",
)


def normalize_org_name(naam: str) -> str:
    """Normalize an organisational-unit name for cross-source matching.

    Lowercases, collapses whitespace, and strips one leading source-specific
    prefix (see _ORG_NAME_PREFIXES). Used both by the organogram scrape (to
    avoid creating a duplicate of an existing manual/seed row) and by the
    orphan-handmatig reconciliation scan, so the two stay in lockstep.
    """
    n = " ".join(naam.lower().split())
    for prefix in _ORG_NAME_PREFIXES:
        if n.startswith(prefix):
            n = n[len(prefix) :]
            break
    return n.strip()
