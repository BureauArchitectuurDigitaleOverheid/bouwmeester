"""Application-level encryption for secret configuration values.

Uses Fernet (AES-128-CBC + HMAC) symmetric encryption.
The encryption key is derived from SESSION_SECRET_KEY via PBKDF2.
If no key is configured (local dev), values are stored in plaintext.
"""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None
_initialized = False


def _get_fernet() -> Fernet | None:
    """Lazily initialize Fernet from SESSION_SECRET_KEY."""
    global _fernet, _initialized  # noqa: PLW0603
    if _initialized:
        return _fernet

    _initialized = True
    try:
        from bouwmeester.core.config import get_settings

        settings = get_settings()
        secret = settings.SESSION_SECRET_KEY
        if not secret or secret in settings._INSECURE_SECRET_DEFAULTS:
            logger.debug(
                "No secure SESSION_SECRET_KEY set, storing config values in plaintext"
            )
            return None

        # Derive a 32-byte Fernet key from the session secret via PBKDF2
        key = hashlib.pbkdf2_hmac(
            "sha256",
            secret.encode(),
            b"bouwmeester-app-config",
            iterations=100_000,
        )
        _fernet = Fernet(base64.urlsafe_b64encode(key))
        return _fernet
    except Exception:
        logger.debug("Could not initialize encryption", exc_info=True)
        return None


def encrypt_value(plaintext: str) -> str:
    """Encrypt a value. Returns plaintext unchanged if no key configured."""
    if not plaintext:
        return plaintext
    f = _get_fernet()
    if f is None:
        return plaintext
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a value. Returns as-is if not encrypted or no key configured."""
    if not ciphertext:
        return ciphertext
    f = _get_fernet()
    if f is None:
        return ciphertext
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        # Value was stored before encryption was enabled, return as-is
        return ciphertext
