"""Shared file-storage utilities for bijlagen (attachments)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import HTTPException

if TYPE_CHECKING:
    from fastapi import UploadFile


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


# Broad allowlist for chat and lead attachments.
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.oasis.opendocument.text",
    "text/plain",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
}

# Stricter allowlist for bron (document) attachments - no animated images.
BRON_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.oasis.opendocument.text",
    "text/plain",
    "image/png",
    "image/jpeg",
}

MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20 MB


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


def validate_upload(
    content: bytes,
    content_type: str,
    allowed: set[str] | None = None,
) -> None:
    """Validate content type against allowlist and magic bytes.

    Raises ``HTTPException`` with 400 status on validation failure.
    Uses *allowed* if given, otherwise falls back to ``ALLOWED_CONTENT_TYPES``.
    """
    if content_type not in (allowed or ALLOWED_CONTENT_TYPES):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Ongeldig bestandstype: {content_type}. "
                "Toegestaan: PDF, Word, ODT, TXT, PNG, JPEG, GIF, WebP."
            ),
        )
    if not verify_content_type(content, content_type):
        raise HTTPException(
            status_code=400,
            detail="Bestandsinhoud komt niet overeen met het opgegeven bestandstype.",
        )


async def read_upload_content(file: UploadFile, max_size: int | None = None) -> bytes:
    """Read an upload file in chunks, enforcing a size limit.

    Raises ``HTTPException`` with 400 status if the file exceeds *max_size*.
    Defaults to ``MAX_UPLOAD_SIZE`` when *max_size* is ``None``.
    """
    if max_size is None:
        max_size = MAX_UPLOAD_SIZE
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(8192):
        total += len(chunk)
        if total > max_size:
            max_mb = max_size // (1024 * 1024)
            raise HTTPException(
                status_code=400,
                detail=f"Bestand te groot. Maximum is {max_mb} MB.",
            )
        chunks.append(chunk)
    return b"".join(chunks)
