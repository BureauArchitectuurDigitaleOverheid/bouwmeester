"""Access whitelist — restrict login to a set of allowed email addresses.

The whitelist is stored in the ``whitelist_email`` database table and managed
via the admin UI.

Admin emails are bootstrapped from ``admin_emails.json`` /
``admin_emails.json.age`` — those persons get ``is_admin = True``.

When the whitelist table is empty the whitelist is considered inactive and all
emails are allowed (backwards compatible for local development).

Expected JSON format for admin_emails::

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
# Startup: seed admin emails from file
# ---------------------------------------------------------------------------


async def seed_admins_from_file(session: AsyncSession) -> int:
    """Ensure admin persons exist and have ``is_admin = True``.

    For each email in the admin seed file:
    - If a Person with that email exists → set ``is_admin = True``
    - If not → create a stub Person with ``is_admin = True``

    Runs on every startup (idempotent).  Never revokes admin rights.

    Returns the number of newly created person stubs.
    """
    from bouwmeester.models.person import Person

    try:
        emails = _load_emails_from_file(_ADMIN_JSON_PATH, _ADMIN_AGE_PATH)
    except Exception:
        logger.exception("Failed to load admin emails file")
        return 0

    if emails is None:
        logger.info("No admin_emails file found — skipping admin seed")
        return 0

    if not emails:
        return 0

    # Update existing persons
    result = await session.execute(
        update(Person).where(func.lower(Person.email).in_(emails)).values(is_admin=True)
    )
    updated = result.rowcount

    # Find which admin emails don't have a person yet and create stubs
    existing_result = await session.execute(
        select(func.lower(Person.email)).where(func.lower(Person.email).in_(emails))
    )
    existing_emails = {row[0] for row in existing_result.all()}
    missing_emails = emails - existing_emails

    for email in missing_emails:
        session.add(Person(email=email, naam=email, is_admin=True))
    if missing_emails:
        await session.flush()

    logger.info(
        "Admin seed: updated %d existing, created %d new person stubs (from %d emails)",
        updated,
        len(missing_emails),
        len(emails),
    )
    return len(missing_emails)


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
    """Set whitelist to inactive (sync, legacy).

    Prefer :func:`refresh_whitelist_cache` for the async DB-backed flow.
    This function is kept for backwards compatibility with scripts/tests.
    """
    global _allowed_emails, _whitelist_active  # noqa: PLW0603

    _allowed_emails = None
    _whitelist_active = False
    logger.info(
        "Whitelist inactive — all emails allowed (use DB-backed cache in production)"
    )


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
