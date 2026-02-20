"""Shared file-storage utilities for bijlagen (attachments)."""

import os
from pathlib import Path


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
