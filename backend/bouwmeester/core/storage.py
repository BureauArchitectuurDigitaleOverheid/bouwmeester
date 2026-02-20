"""Shared file-storage utilities for bijlagen (attachments)."""

import os
from pathlib import Path

from fastapi import HTTPException


def bijlagen_root() -> Path:
    """Return the root directory for bijlagen storage.

    Resolution order:
    1. ``BIJLAGEN_ROOT`` env var (explicit override)
    2. ``DATA_PATH`` env var + ``/bijlagen``
    3. ``/data/bijlagen`` (container default)
    """
    explicit = os.environ.get("BIJLAGEN_ROOT")
    if explicit:
        return Path(explicit)
    data_path = os.environ.get("DATA_PATH")
    if data_path:
        return Path(data_path) / "bijlagen"
    return Path("/data/bijlagen")


def safe_resolve(root: Path, relative: str) -> Path:
    """Resolve *relative* under *root*, guarding against path traversal.

    Raises ``ValueError`` if the resolved path escapes *root*.
    """
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("Path traversal attempt detected")
    return resolved


def safe_resolve_or_400(root: Path, relative: str) -> Path:
    """Like :func:`safe_resolve` but raises HTTP 400 on traversal."""
    try:
        return safe_resolve(root, relative)
    except ValueError:
        raise HTTPException(status_code=400, detail="Ongeldig pad")


# Magic-byte signatures for content-type verification.
_MAGIC_SIGNATURES: dict[bytes, set[str]] = {
    b"%PDF": {"application/pdf"},
    b"PK": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.oasis.opendocument.text",
    },
    b"\xd0\xcf\x11\xe0": {"application/msword"},
    b"\x89PNG": {"image/png"},
    b"\xff\xd8\xff": {"image/jpeg"},
    b"GIF87a": {"image/gif"},
    b"GIF89a": {"image/gif"},
    b"RIFF": {"image/webp"},  # WebP starts with RIFF....WEBP
}


def verify_content_type(content: bytes, claimed: str) -> bool:
    """Check that *content* magic bytes are consistent with *claimed* MIME type.

    Returns ``True`` when the content matches (or for ``text/plain`` where
    magic-byte detection is unreliable).  Returns ``False`` when a magic
    signature is found that contradicts the claimed type.
    """
    if claimed == "text/plain":
        return True

    for sig, allowed_types in _MAGIC_SIGNATURES.items():
        if content[: len(sig)] == sig:
            return claimed in allowed_types
    # No matching signature found — allow (defensive; unknown formats pass)
    return True
