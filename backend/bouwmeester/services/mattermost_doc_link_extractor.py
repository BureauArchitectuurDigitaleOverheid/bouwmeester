"""Doc-link extractie uit Mattermost-berichten.

Pikt URLs op die naar bekende documentbronnen wijzen (Drive, Confluence,
SharePoint, Dropbox, Notion) plus expliciete bestandstypen (.pdf/.docx).
Bewust conservatief: een willekeurige nieuwsartikel-URL telt niet als
document.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# https?:// gevolgd door tekens die in een URL passen, geen aanhalingstekens.
# Stript veelvoorkomende trailing punctuation (komma's, haakjes, punten).
_URL_PATTERN = re.compile(
    r"https?://[^\s<>\"\\]+",
    re.IGNORECASE,
)
_TRAILING_STRIP = ".,;:!?)]}>"

# Hostnamen (suffix-match) waarvan we URLs altijd als doc-link beschouwen.
_DOC_HOST_SUFFIXES: tuple[str, ...] = (
    "drive.google.com",
    "docs.google.com",
    "sheets.google.com",
    "slides.google.com",
    "atlassian.net",  # Confluence cloud
    "sharepoint.com",
    "onedrive.live.com",
    "dropbox.com",
    "notion.so",
    "notion.site",
    "miro.com",
    "figma.com",
)

# Padsuffixen die ook zonder bekende host gelden als doc-link.
_DOC_PATH_SUFFIXES: tuple[str, ...] = (
    ".pdf",
    ".docx",
    ".doc",
    ".pptx",
    ".ppt",
    ".xlsx",
    ".xls",
    ".odt",
    ".ods",
)


def _normalize(url: str) -> str:
    """Strip trailing punctuation die vaak per ongeluk in de match zit."""
    while url and url[-1] in _TRAILING_STRIP:
        url = url[:-1]
    return url


def _matches_doc_host(host: str) -> bool:
    host = host.lower()
    return any(
        host == suffix or host.endswith("." + suffix) for suffix in _DOC_HOST_SUFFIXES
    )


def _matches_doc_path(path: str) -> bool:
    p = path.lower()
    return any(p.endswith(suffix) for suffix in _DOC_PATH_SUFFIXES)


def extract_doc_links(message: str) -> list[dict]:
    """Vind alle URLs die kwalificeren als doc-link.

    Returneert een lijst dicts: ``{"url": str, "host": str}``. De caller
    bepaalt zelf hoe deze als attachment worden opgeslagen. Dubbele URLs
    worden gededupliceerd in volgorde van eerste voorkomen.
    """
    if not message:
        return []

    seen: set[str] = set()
    out: list[dict] = []
    for raw in _URL_PATTERN.findall(message):
        url = _normalize(raw)
        if not url or url in seen:
            continue
        try:
            parsed = urlparse(url)
        except ValueError:
            continue
        host = (parsed.hostname or "").lower()
        if not host:
            continue
        if not (_matches_doc_host(host) or _matches_doc_path(parsed.path or "")):
            continue
        seen.add(url)
        out.append({"url": url, "host": host})
    return out


def derive_attachment_label(url: str) -> str:
    """Verzin een leesbaar label voor een URL-attachment.

    We willen geen full-URL als label tonen — voor Google Drive nemen we
    'Drive', voor Confluence 'Confluence', anders de host zonder www.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return url
    host = (parsed.hostname or "").lower()
    if "drive.google.com" in host or "docs.google.com" in host:
        return "Google Drive"
    if "atlassian.net" in host:
        return "Confluence"
    if "sharepoint.com" in host or "onedrive.live.com" in host:
        return "SharePoint/OneDrive"
    if "dropbox.com" in host:
        return "Dropbox"
    if "notion." in host:
        return "Notion"
    if "figma.com" in host:
        return "Figma"
    if "miro.com" in host:
        return "Miro"
    if host.startswith("www."):
        host = host[4:]
    return host or url
