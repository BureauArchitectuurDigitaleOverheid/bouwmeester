"""Shared query utilities."""


def escape_like(value: str) -> str:
    """Escape special characters for use in SQL LIKE / ILIKE patterns."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def normalize_email(email: str) -> str:
    """Normalize an email address for consistent comparison."""
    return email.strip().lower()
