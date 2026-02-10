"""Access whitelist — restrict login to a set of allowed email addresses.

The whitelist is loaded from ``backend/scripts/access_whitelist.json`` (plaintext,
gitignored) or decrypted at runtime from the ``.age`` variant using the
``AGE_SECRET_KEY`` environment variable (production).  When neither file exists
the whitelist is disabled and all emails are allowed (backwards compatible).

Expected JSON format::

    {"emails": ["user@example.com", "other@example.com"]}
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
_JSON_PATH = _SCRIPTS_DIR / "access_whitelist.json"
_AGE_PATH = _SCRIPTS_DIR / "access_whitelist.json.age"

# Module-level cache
_allowed_emails: set[str] | None = None
_whitelist_active: bool = False


def _set_whitelist(emails: set[str], source: str) -> None:
    """Set the module-level whitelist cache and log appropriately."""
    global _allowed_emails, _whitelist_active  # noqa: PLW0603
    _allowed_emails = emails
    _whitelist_active = True
    if emails:
        logger.info("Access whitelist loaded from %s (%d emails)", source, len(emails))
    else:
        logger.warning(
            "Access whitelist from %s contains 0 emails — all users will be denied",
            source,
        )


def load_whitelist() -> None:
    """Load the whitelist from disk (plaintext or age-encrypted).

    Fallback order:
    1. Plaintext ``access_whitelist.json`` (local dev)
    2. Age-decrypt via ``AGE_SECRET_KEY`` env var + ``pyrage`` (production)
    3. No file → whitelist disabled, all access allowed

    On parse/decrypt errors the whitelist is disabled and all access is denied
    (fail-closed) to avoid silently granting access to everyone.
    """
    global _allowed_emails, _whitelist_active  # noqa: PLW0603

    try:
        if _JSON_PATH.exists():
            with open(_JSON_PATH) as f:
                data = json.load(f)
            emails = {e.strip().lower() for e in data.get("emails", [])}
            _set_whitelist(emails, _JSON_PATH.name)
            return

        if os.environ.get("AGE_SECRET_KEY") and _AGE_PATH.exists():
            from pyrage import decrypt as age_decrypt
            from pyrage import x25519

            identity = x25519.Identity.from_str(os.environ["AGE_SECRET_KEY"])
            decrypted = age_decrypt(_AGE_PATH.read_bytes(), [identity])
            data = json.loads(decrypted)
            emails = {e.strip().lower() for e in data.get("emails", [])}
            _set_whitelist(emails, _AGE_PATH.name)
            return
    except Exception:
        logger.exception("Failed to load access whitelist — denying all access")
        _allowed_emails = set()
        _whitelist_active = True
        return

    _allowed_emails = None
    _whitelist_active = False
    logger.info("No access whitelist found — all emails allowed (backwards compatible)")


def is_email_allowed(email: str) -> bool:
    """Check whether *email* is on the whitelist.

    Returns ``True`` when the whitelist is not active (no file loaded).
    """
    if not _whitelist_active or _allowed_emails is None:
        return True
    return email.strip().lower() in _allowed_emails
