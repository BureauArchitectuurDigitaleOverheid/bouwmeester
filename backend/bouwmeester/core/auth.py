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
from uuid import UUID

import httpx
from authlib.integrations.starlette_client import OAuth
from authlib.jose import JsonWebKey
from authlib.jose import jwt as authlib_jwt
from authlib.jose.errors import JoseError
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.config import Settings, get_settings
from bouwmeester.core.database import get_db
from bouwmeester.models.person import Person
from bouwmeester.models.person_email import PersonEmail

logger = logging.getLogger(__name__)

# Revalidate the access token against Keycloak at most every 5 minutes.
_TOKEN_REVALIDATION_INTERVAL = 300

# Grace period: if Keycloak is unreachable, allow recently-validated sessions
# for up to this many seconds beyond the last successful validation.
_NETWORK_ERROR_GRACE_SECONDS = 120

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


def _require_https(url: str, label: str) -> bool:
    """Return True if the URL uses HTTPS.  Log a warning and return False otherwise."""
    if url.startswith("https://"):
        return True
    logger.warning("%s is not HTTPS, refusing to send credentials: %s", label, url)
    return False


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
        if not _require_https(url, "OIDC discovery URL"):
            return None
        client = _get_http_client()
        resp = await client.get(url)
        resp.raise_for_status()
        _oidc_metadata = resp.json()
        _oidc_metadata_fetched_at = now
        return _oidc_metadata


# ---------------------------------------------------------------------------
# Cached JWKS keys for local JWT validation
# ---------------------------------------------------------------------------

_jwks_keys: Any | None = None
_jwks_fetched_at: float = 0
_jwks_lock = asyncio.Lock()
_JWKS_TTL = 3600  # Re-fetch JWKS every hour


async def _get_jwks(settings: Settings) -> Any | None:
    """Return cached JWKS key set, fetching if stale."""
    global _jwks_keys, _jwks_fetched_at  # noqa: PLW0603

    now = time.monotonic()
    if _jwks_keys and (now - _jwks_fetched_at) < _JWKS_TTL:
        return _jwks_keys

    async with _jwks_lock:
        now = time.monotonic()
        if _jwks_keys and (now - _jwks_fetched_at) < _JWKS_TTL:
            return _jwks_keys

        metadata = await get_oidc_metadata(settings)
        if not metadata:
            return None

        jwks_uri = metadata.get("jwks_uri")
        if not jwks_uri:
            return None

        if not _require_https(jwks_uri, "JWKS URI"):
            return None

        client = _get_http_client()
        try:
            resp = await client.get(jwks_uri)
            resp.raise_for_status()
            _jwks_keys = JsonWebKey.import_key_set(resp.json())
            _jwks_fetched_at = now
            return _jwks_keys
        except (httpx.HTTPError, Exception) as exc:
            logger.warning("Failed to fetch JWKS: %s", exc)
            return _jwks_keys  # Return stale keys if available


def _validate_jwt_locally(
    token: str,
    jwks: Any,
    settings: Settings,
) -> dict[str, Any] | None:
    """Validate a JWT access token locally using cached JWKS keys.

    Returns the decoded claims on success, or ``None`` if validation fails.
    """
    try:
        claims = authlib_jwt.decode(token, jwks)
        claims.validate()

        # Verify issuer matches our configured OIDC_ISSUER.
        if claims.get("iss") != settings.OIDC_ISSUER:
            logger.debug(
                "JWT issuer mismatch: %s != %s",
                claims.get("iss"),
                settings.OIDC_ISSUER,
            )
            return None

        # Verify audience — the token must be intended for this client.
        # Keycloak puts the client_id in ``azp`` (authorized party) for
        # access tokens and in ``aud`` for ID tokens.
        aud = claims.get("aud")
        azp = claims.get("azp")
        client_id = settings.OIDC_CLIENT_ID

        # ``aud`` can be a string or a list.
        aud_list = [aud] if isinstance(aud, str) else (aud or [])
        if client_id not in aud_list and azp != client_id:
            logger.debug(
                "JWT audience mismatch: aud=%s, azp=%s, expected=%s",
                aud,
                azp,
                client_id,
            )
            return None

        return dict(claims)
    except JoseError as exc:
        logger.debug("Local JWT validation failed: %s", exc)
        return None


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


async def _ensure_email_linked(db: AsyncSession, person_id: UUID, email: str) -> None:
    """Add email to person_email if not already present (is_default=False)."""

    existing = await db.execute(select(PersonEmail).where(PersonEmail.email == email))
    if existing.scalar_one_or_none() is not None:
        return  # Already linked (possibly to this or another person)
    try:
        async with db.begin_nested():
            db.add(PersonEmail(person_id=person_id, email=email, is_default=False))
            await db.flush()
    except IntegrityError:
        pass  # Concurrent insert — ignore (savepoint already rolled back)


async def get_or_create_person(
    db: AsyncSession,
    sub: str,
    email: str,
    name: str,
    email_verified: bool = False,
) -> Person:
    """Return existing ``Person`` by ``oidc_subject``, or create a new one.

    Handles race conditions where two concurrent requests might try to
    create the same person simultaneously.

    Only links an existing Person by email if ``email_verified`` is True,
    to prevent account takeover via unverified email claims.
    """
    stmt = select(Person).where(Person.oidc_subject == sub)
    result = await db.execute(stmt)
    person = result.scalar_one_or_none()

    if person is not None:
        # Auto-accumulate emails across logins
        await _ensure_email_linked(db, person.id, email)
        return person

    # Only link by email if the OIDC provider has verified the email address.
    if email_verified:
        # Look up in person_email table
        stmt_email = select(Person).join(PersonEmail).where(PersonEmail.email == email)
        result_email = await db.execute(stmt_email)
        person = result_email.scalar_one_or_none()

        if person is None:
            # Fallback: check legacy Person.email column
            stmt_legacy = select(Person).where(Person.email == email)
            result_legacy = await db.execute(stmt_legacy)
            person = result_legacy.scalar_one_or_none()

        if person is not None:
            person.oidc_subject = sub
            if name and not person.naam:
                person.naam = name
            await _ensure_email_linked(db, person.id, email)
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
        # Create PersonEmail row for the new person
        email_obj = PersonEmail(person_id=person.id, email=email, is_default=True)
        db.add(email_obj)
        await db.flush()
        await db.refresh(person)
        return person
    except IntegrityError:
        # Concurrent insert — roll back and re-fetch.
        await db.rollback()
        stmt = select(Person).where(Person.oidc_subject == sub)
        result = await db.execute(stmt)
        person = result.scalar_one_or_none()
        if person is None:
            # Fall back to email match in person_email table.
            stmt = select(Person).join(PersonEmail).where(PersonEmail.email == email)
            result = await db.execute(stmt)
            person = result.scalar_one_or_none()
        if person is None:
            # Legacy fallback
            stmt = select(Person).where(Person.email == email)
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

    if not _require_https(token_url, "Token endpoint"):
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

    # Try local JWT validation first (no network call).
    jwks = await _get_jwks(settings)
    if jwks:
        claims = _validate_jwt_locally(access_token, jwks, settings)
        if claims:
            session["token_validated_at"] = time.time()
            return True
        # Local validation failed — token might be expired or keys rotated.
        # Fall through to userinfo check / refresh.

    metadata = await get_oidc_metadata(settings)
    if not metadata:
        return False

    userinfo_url = metadata.get("userinfo_endpoint")
    if not userinfo_url:
        return False

    if not _require_https(userinfo_url, "Userinfo endpoint"):
        return False

    client = _get_http_client()
    try:
        resp = await client.get(
            userinfo_url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    except httpx.HTTPError as exc:
        logger.warning("Token validation HTTP error: %s", exc)
        # Network error — only allow if validated within the grace period.
        if validated_at and (time.time() - validated_at) < _NETWORK_ERROR_GRACE_SECONDS:
            logger.info("Keycloak unreachable, allowing session within grace period")
            return True
        logger.warning(
            "Keycloak unreachable and grace period expired, rejecting session"
        )
        return False

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

    For session-based tokens, if the token is expired this function attempts
    a refresh before giving up — mirroring the behaviour of
    :func:`validate_session_token`.

    Returns the userinfo claims dict on success, or ``None`` when no token is
    present.  Raises ``HTTPException(401)`` when the token is invalid.
    """
    # 1. Check Authorization header
    auth_header = request.headers.get("Authorization")
    token: str | None = None
    is_bearer = False
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip() or None
        is_bearer = token is not None

    # 2. Fall back to session token
    session: dict | None = None
    if token is None:
        session = getattr(request, "session", None) or request.scope.get("session", {})
        token = session.get("access_token") if session else None

    if not token:
        return None

    # Try local JWT validation first (avoids network call).
    jwks = await _get_jwks(settings)
    if jwks:
        claims = _validate_jwt_locally(token, jwks, settings)
        if claims:
            return claims

    # Fall back to userinfo endpoint.
    metadata = await get_oidc_metadata(settings)
    if not metadata:
        return None

    userinfo_url = metadata.get("userinfo_endpoint")
    if not userinfo_url:
        return None

    if not _require_https(userinfo_url, "Userinfo endpoint"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC userinfo endpoint is not HTTPS",
        )

    client = _get_http_client()
    try:
        resp = await client.get(
            userinfo_url,
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 200:
            return resp.json()

        # Token invalid/expired — try refresh for session-based tokens.
        if not is_bearer and session and session.get("refresh_token"):
            if await _try_refresh_token(session, settings):
                # Re-validate with the refreshed token.
                new_token = session.get("access_token")
                if new_token:
                    resp2 = await client.get(
                        userinfo_url,
                        headers={"Authorization": f"Bearer {new_token}"},
                    )
                    if resp2.status_code == 200:
                        return resp2.json()

        # All attempts failed — clear session if present.
        if session and "access_token" in session:
            session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    except httpx.HTTPError as exc:
        logger.warning("OIDC token validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token validation failed",
        ) from exc


# ---------------------------------------------------------------------------
# Token revocation (best-effort, for logout)
# ---------------------------------------------------------------------------


async def revoke_tokens(
    settings: Settings,
    access_token: str | None = None,
    refresh_token: str | None = None,
) -> None:
    """Revoke access and/or refresh tokens at Keycloak (best-effort).

    Failures are logged but never raised — logout should always succeed locally.
    """
    if not access_token and not refresh_token:
        return

    metadata = await get_oidc_metadata(settings)
    if not metadata:
        return

    # Use the revocation_endpoint from discovery, or fall back to the
    # standard Keycloak revocation path.
    revocation_url = metadata.get(
        "revocation_endpoint",
        f"{settings.OIDC_ISSUER.rstrip('/')}/protocol/openid-connect/revoke",
    )

    if not _require_https(revocation_url, "Revocation endpoint"):
        return

    client = _get_http_client()
    for token_value, token_type in [
        (refresh_token, "refresh_token"),
        (access_token, "access_token"),
    ]:
        if not token_value:
            continue
        try:
            resp = await client.post(
                revocation_url,
                data={
                    "token": token_value,
                    "token_type_hint": token_type,
                    "client_id": settings.OIDC_CLIENT_ID,
                    "client_secret": settings.OIDC_CLIENT_SECRET,
                },
            )
            if resp.status_code != 200:
                logger.info(
                    "Token revocation returned %d for %s", resp.status_code, token_type
                )
        except httpx.HTTPError as exc:
            logger.warning("Token revocation failed for %s: %s", token_type, exc)


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def _person_from_claims(
    db: AsyncSession,
    claims: dict[str, Any],
) -> Person | None:
    """Extract OIDC claims and resolve to a :class:`Person`.

    Returns ``None`` if required claims (``sub``, ``email``) are missing.
    """
    sub: str = claims.get("sub", "")
    email: str = claims.get("email", "")
    name: str = claims.get("name", claims.get("preferred_username", ""))
    email_verified: bool = claims.get("email_verified", False)

    if not sub or not email:
        return None

    return await get_or_create_person(
        db, sub=sub, email=email, name=name, email_verified=email_verified
    )


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

    person = await _person_from_claims(db, claims)
    if person is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC claims missing 'sub' or 'email'",
        )
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

    return await _person_from_claims(db, claims)


async def get_admin_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Person | None:
    """Dependency that requires the current user to be an admin.

    In development mode (no OIDC) returns ``None`` (all access open).
    In OIDC mode: resolves the authenticated user and checks ``is_admin``.
    Raises 403 if the user is not an admin.
    """
    if not settings.OIDC_ISSUER:
        return None

    claims = await _validate_token(request, settings)
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    person = await _person_from_claims(db, claims)
    if person is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC claims missing 'sub' or 'email'",
        )

    if not person.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return person


# Type aliases for convenient use in route signatures.
#
# NOTE ON AUTHORIZATION:
# - CurrentUser: raises 401 when OIDC is not configured.  Use this to
#   **enforce** authentication (blocks unauthenticated access).
# - OptionalUser: returns None when OIDC is not configured (dev mode).
#   It does NOT enforce authentication — it only provides identity context
#   so handlers can apply authorization logic (e.g. prevent sender spoofing)
#   when a user *is* authenticated.  All endpoints currently use OptionalUser
#   so the app keeps working in dev without an OIDC provider.  When deployed
#   behind the Keycloak gateway, every request carries a valid token and
#   OptionalUser returns the authenticated Person.
# - AdminUser: requires admin role.  Returns None in dev mode (no OIDC).
CurrentUser = Annotated[Person, Depends(get_current_user)]
OptionalUser = Annotated[Person | None, Depends(get_optional_user)]
AdminUser = Annotated[Person | None, Depends(get_admin_user)]
