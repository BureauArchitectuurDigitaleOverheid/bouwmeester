"""OIDC authentication helpers.

When ``OIDC_ISSUER`` is configured the module validates Bearer tokens against
the Keycloak (or any OIDC-compatible) provider.  When it is *not* configured
(local development) the dependency simply returns ``None`` so the rest of the
application can run without authentication.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Annotated, Any

import httpx
from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.config import Settings, get_settings
from bouwmeester.core.database import get_db
from bouwmeester.models.person import Person

logger = logging.getLogger(__name__)

# Revalidate the access token against Keycloak at most every 5 minutes.
_TOKEN_REVALIDATION_INTERVAL = 300

# Shared httpx client for outbound OIDC requests (connection pooling).
_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    """Return a shared httpx.AsyncClient, creating it on first call."""
    global _http_client  # noqa: PLW0603
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=10)
    return _http_client


async def close_http_client() -> None:
    """Close the shared httpx client (called during app shutdown)."""
    global _http_client  # noqa: PLW0603
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None


def _get_discovery_url(settings: Settings) -> str:
    """Return the OIDC discovery URL from settings.

    Prefers ``OIDC_DISCOVERY_URL`` (set by ZAD platform), falls back to
    constructing it from ``OIDC_ISSUER``.
    """
    if settings.OIDC_DISCOVERY_URL:
        return settings.OIDC_DISCOVERY_URL
    return f"{settings.OIDC_ISSUER.rstrip('/')}/.well-known/openid-configuration"


# ---------------------------------------------------------------------------
# Cached OIDC discovery metadata
# ---------------------------------------------------------------------------

_oidc_metadata: dict[str, Any] | None = None
_oidc_metadata_fetched_at: float = 0
_oidc_metadata_lock = asyncio.Lock()
_OIDC_METADATA_TTL = 3600  # Re-fetch discovery doc every hour


async def get_oidc_metadata(settings: Settings) -> dict[str, Any] | None:
    """Return cached OIDC discovery metadata, fetching if stale."""
    global _oidc_metadata, _oidc_metadata_fetched_at  # noqa: PLW0603

    if not settings.OIDC_ISSUER:
        return None

    now = time.monotonic()
    if _oidc_metadata and (now - _oidc_metadata_fetched_at) < _OIDC_METADATA_TTL:
        return _oidc_metadata

    async with _oidc_metadata_lock:
        # Re-check after acquiring lock (another coroutine may have fetched).
        now = time.monotonic()
        if _oidc_metadata and (now - _oidc_metadata_fetched_at) < _OIDC_METADATA_TTL:
            return _oidc_metadata

        url = _get_discovery_url(settings)
        client = _get_http_client()
        resp = await client.get(url)
        resp.raise_for_status()
        _oidc_metadata = resp.json()
        _oidc_metadata_fetched_at = now
        return _oidc_metadata


# ---------------------------------------------------------------------------
# OAuth / OIDC client singleton
# ---------------------------------------------------------------------------

_oauth: OAuth | None = None


def get_oauth(settings: Settings | None = None) -> OAuth | None:
    """Return the global :class:`OAuth` instance, creating it on first call.

    Returns ``None`` when OIDC is not configured.
    """
    global _oauth  # noqa: PLW0603
    if _oauth is not None:
        return _oauth

    if settings is None:
        settings = get_settings()

    if not settings.OIDC_ISSUER:
        return None

    _oauth = OAuth()

    _oauth.register(
        name="keycloak",
        client_id=settings.OIDC_CLIENT_ID,
        client_secret=settings.OIDC_CLIENT_SECRET,
        server_metadata_url=_get_discovery_url(settings),
        client_kwargs={
            "scope": "openid email profile",
            "code_challenge_method": "S256",
        },
    )

    return _oauth


# ---------------------------------------------------------------------------
# Helper: find or create Person from OIDC claims
# ---------------------------------------------------------------------------


async def _get_or_create_person(
    db: AsyncSession,
    sub: str,
    email: str,
    name: str,
) -> Person:
    """Return existing ``Person`` by ``oidc_subject``, or create a new one.

    Handles race conditions where two concurrent requests might try to
    create the same person simultaneously.
    """
    stmt = select(Person).where(Person.oidc_subject == sub)
    result = await db.execute(stmt)
    person = result.scalar_one_or_none()

    if person is not None:
        return person

    # Also check by email -- the record may already exist from a manual
    # import without OIDC subject.
    stmt_email = select(Person).where(Person.email == email)
    result_email = await db.execute(stmt_email)
    person = result_email.scalar_one_or_none()

    if person is not None:
        person.oidc_subject = sub
        if name and not person.naam:
            person.naam = name
        await db.flush()
        await db.refresh(person)
        return person

    # Create brand-new person from OIDC claims.
    try:
        person = Person(
            naam=name or email,
            email=email,
            oidc_subject=sub,
        )
        db.add(person)
        await db.flush()
        await db.refresh(person)
        return person
    except IntegrityError:
        # Concurrent insert — roll back and re-fetch.
        await db.rollback()
        stmt = select(Person).where(
            (Person.oidc_subject == sub) | (Person.email == email)
        )
        result = await db.execute(stmt)
        person = result.scalar_one_or_none()
        if person is None:
            raise  # Unexpected — re-raise the original error.
        return person


# ---------------------------------------------------------------------------
# Token validation + refresh
# ---------------------------------------------------------------------------


async def _try_refresh_token(
    session: dict[str, Any],
    settings: Settings,
) -> bool:
    """Attempt to refresh the access token using the stored refresh_token.

    Updates the session in-place on success.  Returns ``True`` if successful.
    """
    refresh_token = session.get("refresh_token")
    if not refresh_token:
        return False

    metadata = await get_oidc_metadata(settings)
    if not metadata:
        return False

    token_url = metadata.get("token_endpoint")
    if not token_url:
        return False

    # Refuse to send client_secret over plain HTTP.
    if not token_url.startswith("https://"):
        logger.warning("Token endpoint is not HTTPS, refusing refresh: %s", token_url)
        return False

    client = _get_http_client()
    try:
        resp = await client.post(
            token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": settings.OIDC_CLIENT_ID,
                "client_secret": settings.OIDC_CLIENT_SECRET,
            },
        )
        if resp.status_code != 200:
            logger.info("Token refresh failed with status %d", resp.status_code)
            return False

        tokens = resp.json()
        session["access_token"] = tokens["access_token"]
        if "refresh_token" in tokens:
            session["refresh_token"] = tokens["refresh_token"]
        if "id_token" in tokens:
            session["id_token"] = tokens["id_token"]
        session["token_validated_at"] = time.time()
        logger.debug("Token refreshed successfully")
        return True
    except httpx.HTTPError as exc:
        logger.warning("Token refresh HTTP error: %s", exc)
        return False


async def validate_session_token(
    session: dict[str, Any],
    settings: Settings,
) -> bool:
    """Validate the session's access token against Keycloak.

    Uses a cached validation timestamp to avoid hitting Keycloak on every
    request.  If the token is expired, attempts a refresh first.

    Returns ``True`` if the session is valid, ``False`` if it should be
    rejected (session will be cleared).
    """
    access_token = session.get("access_token")
    if not access_token:
        return False

    # Skip revalidation if recently validated.
    validated_at = session.get("token_validated_at")
    recently_validated = (
        validated_at and (time.time() - validated_at) < _TOKEN_REVALIDATION_INTERVAL
    )
    if recently_validated:
        return True

    metadata = await get_oidc_metadata(settings)
    if not metadata:
        return False

    userinfo_url = metadata.get("userinfo_endpoint")
    if not userinfo_url:
        return False

    client = _get_http_client()
    try:
        resp = await client.get(
            userinfo_url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    except httpx.HTTPError as exc:
        logger.warning("Token validation HTTP error: %s", exc)
        # Network error — don't clear session, allow stale validation.
        return True

    if resp.status_code == 200:
        session["token_validated_at"] = time.time()
        return True

    # Token is invalid/expired at Keycloak — try refresh.
    if await _try_refresh_token(session, settings):
        return True

    # Refresh also failed — session is dead.
    logger.info("Token invalid and refresh failed, clearing session")
    session.clear()
    return False


async def _validate_token(request: Request, settings: Settings) -> dict | None:
    """Validate the Bearer token or session access token.

    Checks in order:
    1. ``Authorization: Bearer`` header (for API clients)
    2. ``request.session["access_token"]`` (for browser sessions)

    Returns the userinfo claims dict on success, or ``None`` when no token is
    present.  Raises ``HTTPException(401)`` when the token is invalid.
    """
    # 1. Check Authorization header
    auth_header = request.headers.get("Authorization")
    token: str | None = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip() or None

    # 2. Fall back to session token
    if token is None:
        session = getattr(request, "session", None) or request.scope.get("session", {})
        token = session.get("access_token") if session else None

    if not token:
        return None

    metadata = await get_oidc_metadata(settings)
    if not metadata:
        return None

    userinfo_url = metadata.get("userinfo_endpoint")
    if not userinfo_url:
        return None

    client = _get_http_client()
    try:
        resp = await client.get(
            userinfo_url,
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code != 200:
            # Token expired or invalid — clear session if present
            session = request.scope.get("session")
            if session and "access_token" in session:
                session.clear()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
        return resp.json()
    except httpx.HTTPError as exc:
        logger.warning("OIDC token validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token validation failed",
        ) from exc


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Person:
    """Dependency that requires a valid OIDC token.

    In development mode (``OIDC_ISSUER`` is empty) this raises 401 to signal
    that authentication is not available -- prefer :func:`get_optional_user`
    for endpoints that should also work without OIDC.
    """
    if not settings.OIDC_ISSUER:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC is not configured",
        )

    claims = await _validate_token(request, settings)
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    sub: str = claims.get("sub", "")
    email: str = claims.get("email", "")
    name: str = claims.get("name", claims.get("preferred_username", ""))

    if not sub or not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC claims missing 'sub' or 'email'",
        )

    person = await _get_or_create_person(db, sub=sub, email=email, name=name)
    return person


async def get_optional_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Person | None:
    """Dependency that returns the current user when authenticated, or ``None``.

    If OIDC is not configured, always returns ``None`` (dev mode).
    """
    if not settings.OIDC_ISSUER:
        return None

    claims = await _validate_token(request, settings)
    if claims is None:
        return None

    sub: str = claims.get("sub", "")
    email: str = claims.get("email", "")
    name: str = claims.get("name", claims.get("preferred_username", ""))

    if not sub or not email:
        return None

    person = await _get_or_create_person(db, sub=sub, email=email, name=name)
    return person


# Type aliases for convenient use in route signatures.
CurrentUser = Annotated[Person, Depends(get_current_user)]
OptionalUser = Annotated[Person | None, Depends(get_optional_user)]
