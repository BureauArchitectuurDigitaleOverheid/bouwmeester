"""Shared file-storage utilities for bijlagen (attachments)."""

from __future__ import annotations

import logging
import os
import shutil
import uuid as _uuid
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import HTTPException

if TYPE_CHECKING:
    from fastapi import UploadFile

logger = logging.getLogger(__name__)


def data_root() -> Path:
    """Return the writable runtime data directory.

    Resolution order:
    1. ``DATA_PATH`` env var (explicit override)
    2. ``/data`` (container default — made group-writable for arbitrary
       UIDs in the Dockerfile, unlike the read-only ``/app`` code tree)

    Used for generated runtime state that must survive process restarts
    but cannot be written into the immutable image layer.
    """
    data_path = os.environ.get("DATA_PATH")
    if data_path:
        return Path(data_path)
    return Path("/data")


def kabinet_yaml_path() -> Path:
    """Return the writable path for the scraped ``kabinet.yaml``.

    The worker scrapes rijksoverheid.nl and overwrites this file daily, so
    it cannot live in the read-only ``/app`` code tree (the deployed
    container runs as an arbitrary, non-owning UID and gets ``EACCES`` on
    write — see ``backend/bouwmeester/data/kabinet.yaml`` shipped only as a
    seed). On first run we copy the in-image seed into the writable data
    dir so ``write_kabinet_yaml``'s "0 entries → keep existing YAML"
    data-loss guard still has a baseline to fall back to.
    """
    target = data_root() / "kabinet.yaml"
    if not target.exists():
        seed = Path(__file__).resolve().parent.parent / "data" / "kabinet.yaml"
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if seed.exists():
                shutil.copyfile(seed, target)
        except OSError:
            logger.warning(
                "Kon kabinet.yaml-seed niet naar %s kopiëren; scrape begint "
                "zonder baseline",
                target,
            )
    return target


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


def file_exists_on_disk(root: Path, relative: str) -> bool:
    """Check whether the file at *relative* under *root* exists.

    Returns ``False`` when the path escapes *root* (traversal) or cannot
    be resolved for any reason, so callers never need their own try/except.
    """
    try:
        return safe_resolve(root, relative).exists()
    except (ValueError, OSError):
        return False


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
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.spreadsheet",
    "text/plain",
    "text/csv",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "application/zip",
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


def sanitize_download_filename(name: str) -> str:
    """Strip characters that could cause header injection in Content-Disposition."""
    return name.replace('"', "").replace("\r", "").replace("\n", "")


def ensure_bijlagen_dir(subdir: str | None = None) -> Path:
    """Return a bijlagen subdirectory, creating it if possible.

    Returns ``bijlagen_root() / subdir`` (or just ``bijlagen_root()``
    when *subdir* is ``None``) after a best-effort ``mkdir``.
    """
    path = bijlagen_root() / subdir if subdir else bijlagen_root()
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass  # May fail in CI/test; directories are also created per-upload
    return path


def write_upload_to_disk(
    content: bytes,
    filename: str,
    storage_dir: Path,
    item_id: _uuid.UUID | str | None = None,
) -> tuple[str, str, Path]:
    """Sanitize *filename*, write *content* to disk, return metadata.

    Creates ``storage_dir / item_id / <uuid>_<safe_name>`` (or
    ``storage_dir / <uuid>_<safe_name>`` when *item_id* is ``None``).

    Returns:
        ``(sanitized_filename, relative_path, absolute_path)``

    Raises:
        ``HTTPException(500)`` on write failure.
    """
    safe_basename = Path(filename).name or "bijlage"
    safe_name = f"{_uuid.uuid4().hex}_{safe_basename}"

    if item_id is not None:
        dir_path = storage_dir / str(item_id)
    else:
        dir_path = storage_dir

    try:
        dir_path.mkdir(parents=True, exist_ok=True)
        abs_path = dir_path / safe_name
        abs_path.write_bytes(content)
    except OSError:
        logger.exception("Failed to write upload to %s", dir_path)
        raise HTTPException(
            status_code=500,
            detail="Kan bestand niet opslaan.",
        )

    # Build a relative path from storage_dir for DB storage.
    rel_path = str(abs_path.relative_to(storage_dir))
    return safe_basename, rel_path, abs_path


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
