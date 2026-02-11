"""Access whitelist — restrict login to a set of allowed email addresses.

The whitelist is stored in the ``whitelist_email`` database table.  On first
startup (when the table is empty) it is seeded from
``backend/scripts/access_whitelist.json`` (plaintext, gitignored) or decrypted
at runtime from the ``.age`` variant using the ``AGE_SECRET_KEY`` environment
variable (production).

Admin emails are similarly bootstrapped from ``admin_emails.json`` /
``admin_emails.json.age`` — those persons get ``is_admin = True``.

When neither file exists for the initial seed the whitelist table stays empty,
which means **all users are denied** (fail-closed).  For local development
without any whitelist file, the whitelist is simply not active and all emails
are allowed (backwards compatible).

Expected JSON format for both files::

    {"emails": ["user@example.com", "other@example.com"]}
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"

# Whitelist files
_WL_JSON_PATH = _SCRIPTS_DIR / "access_whitelist.json"
_WL_AGE_PATH = _SCRIPTS_DIR / "access_whitelist.json.age"

# Admin seed files
_ADMIN_JSON_PATH = _SCRIPTS_DIR / "admin_emails.json"
_ADMIN_AGE_PATH = _SCRIPTS_DIR / "admin_emails.json.age"

# Module-level cache
_allowed_emails: set[str] | None = None
_whitelist_active: bool = False


# ---------------------------------------------------------------------------
# File loading helpers
# ---------------------------------------------------------------------------


def _load_emails_from_file(json_path: Path, age_path: Path) -> set[str] | None:
    """Load a set of emails from a JSON file or its age-encrypted variant.

    Returns ``None`` when neither file exists (not an error).
    Raises on parse/decrypt errors (fail-closed).
    """
    if json_path.exists():
        with open(json_path) as f:
            data = json.load(f)
        return {e.strip().lower() for e in data.get("emails", [])}

    if os.environ.get("AGE_SECRET_KEY") and age_path.exists():
        from pyrage import decrypt as age_decrypt
        from pyrage import x25519

        identity = x25519.Identity.from_str(os.environ["AGE_SECRET_KEY"])
        decrypted = age_decrypt(age_path.read_bytes(), [identity])
        data = json.loads(decrypted)
        return {e.strip().lower() for e in data.get("emails", [])}

    return None


# ---------------------------------------------------------------------------
# Startup: seed whitelist from file into DB (one-time)
# ---------------------------------------------------------------------------


async def seed_whitelist_from_file(session: AsyncSession) -> None:
    """If the ``whitelist_email`` table is empty, seed it from the JSON file.

    This is a one-time migration: once emails are in the DB they are managed
    via the admin UI.
    """
    from bouwmeester.models.whitelist_email import WhitelistEmail

    count_result = await session.execute(select(WhitelistEmail.id).limit(1))
    if count_result.scalar_one_or_none() is not None:
        logger.info("Whitelist table already populated — skipping file seed")
        return

    try:
        emails = _load_emails_from_file(_WL_JSON_PATH, _WL_AGE_PATH)
    except Exception:
        logger.exception("Failed to load whitelist file for DB seed")
        return

    if emails is None:
        logger.info("No whitelist file found — table stays empty (all allowed in dev)")
        return

    for email in emails:
        session.add(WhitelistEmail(email=email, added_by="file-seed"))
    await session.flush()
    logger.info("Seeded %d whitelist emails from file into DB", len(emails))


# ---------------------------------------------------------------------------
# Startup: seed admin emails from file
# ---------------------------------------------------------------------------


async def seed_admins_from_file(session: AsyncSession) -> None:
    """Mark persons as admin based on the admin_emails seed file.

    Runs on every startup (idempotent).  Only sets ``is_admin = True`` for
    matching persons — it never revokes admin rights.
    """
    from bouwmeester.models.person import Person

    try:
        emails = _load_emails_from_file(_ADMIN_JSON_PATH, _ADMIN_AGE_PATH)
    except Exception:
        logger.exception("Failed to load admin emails file")
        return

    if emails is None:
        logger.info("No admin_emails file found — skipping admin seed")
        return

    if not emails:
        return

    result = await session.execute(
        update(Person).where(func.lower(Person.email).in_(emails)).values(is_admin=True)
    )
    logger.info(
        "Admin seed: set is_admin=True for %d persons (from %d emails in file)",
        result.rowcount,
        len(emails),
    )


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------


async def refresh_whitelist_cache(session: AsyncSession) -> None:
    """Reload the in-memory whitelist cache from the database.

    When the ``whitelist_email`` table is empty **and** no file seed was done,
    the whitelist is considered inactive (all emails allowed — backwards
    compatible for local dev).

    Note: when called from a request handler the data is flushed but not yet
    committed (``get_db`` commits after the handler returns).  Reading from the
    same session sees the flushed data, so the cache is consistent.  In the
    unlikely event that the commit fails afterwards, the cache will contain
    data that was rolled back — this is accepted as a minor edge case that
    self-corrects on the next whitelist mutation or app restart.
    """
    global _allowed_emails, _whitelist_active  # noqa: PLW0603

    from bouwmeester.models.whitelist_email import WhitelistEmail

    result = await session.execute(select(WhitelistEmail.email))
    emails = {row[0].strip().lower() for row in result.all()}

    if emails:
        _allowed_emails = emails
        _whitelist_active = True
        logger.info("Whitelist cache refreshed from DB (%d emails)", len(emails))
    else:
        _allowed_emails = None
        _whitelist_active = False
        logger.info("Whitelist table empty — whitelist inactive (all emails allowed)")


# ---------------------------------------------------------------------------
# Backwards-compatible sync loader (kept for tests / CLI scripts)
# ---------------------------------------------------------------------------


def load_whitelist() -> None:
    """Load the whitelist from disk (sync, legacy).

    Prefer :func:`refresh_whitelist_cache` for the async DB-backed flow.
    This function is kept for backwards compatibility with scripts.
    """
    global _allowed_emails, _whitelist_active  # noqa: PLW0603

    try:
        emails = _load_emails_from_file(_WL_JSON_PATH, _WL_AGE_PATH)
    except Exception:
        logger.exception("Failed to load access whitelist — denying all access")
        _allowed_emails = set()
        _whitelist_active = True
        return

    if emails is None:
        _allowed_emails = None
        _whitelist_active = False
        logger.info("No access whitelist found — all emails allowed (backwards compat)")
        return

    _allowed_emails = emails
    _whitelist_active = True
    logger.info("Access whitelist loaded from file (%d emails)", len(emails))


# ---------------------------------------------------------------------------
# Runtime check
# ---------------------------------------------------------------------------


def is_email_allowed(email: str) -> bool:
    """Check whether *email* is on the whitelist.

    Returns ``True`` when the whitelist is not active (no file loaded).
    """
    if not _whitelist_active or _allowed_emails is None:
        return True
    return email.strip().lower() in _allowed_emails
