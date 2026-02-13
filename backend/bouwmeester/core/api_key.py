"""API key generation, hashing, and verification.

Uses SHA-256 hashing (high-entropy keys don't need bcrypt) matching the
pattern used by Stripe, GitHub, etc.
"""

import hashlib
import secrets

_API_KEY_PREFIX = "bm_"
_API_KEY_BYTES = 16  # 128-bit entropy → 32 hex chars


def generate_api_key() -> str:
    """Generate a new API key with ``bm_`` prefix and 32 random hex chars."""
    return _API_KEY_PREFIX + secrets.token_hex(_API_KEY_BYTES)


def hash_api_key(plaintext: str) -> str:
    """Return the SHA-256 hex digest of a plaintext API key."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def verify_api_key(plaintext: str, stored_hash: str) -> bool:
    """Constant-time comparison of a plaintext key against a stored hash."""
    candidate = hash_api_key(plaintext)
    return secrets.compare_digest(candidate, stored_hash)
