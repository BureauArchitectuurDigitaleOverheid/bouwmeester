"""OIDC authentication helpers.

When ``OIDC_ISSUER`` is configured the module validates Bearer tokens against
the Keycloak (or any OIDC-compatible) provider.  When it is *not* configured
(local development) the dependency simply returns ``None`` so the rest of the
application can run without authentication.
"""

from __future__ import annotations

import logging
from typing import Annotated

from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.config import Settings, get_settings
from bouwmeester.core.database import get_db
from bouwmeester.models.person import Person

logger = logging.getLogger(__name__)


def _get_discovery_url(settings: Settings) -> str:
    """Return the OIDC discovery URL from settings.

    Prefers ``OIDC_DISCOVERY_URL`` (set by ZAD platform), falls back to
    constructing it from ``OIDC_ISSUER``.
    """
    if settings.OIDC_DISCOVERY_URL:
        return settings.OIDC_DISCOVERY_URL
    return f"{settings.OIDC_ISSUER.rstrip('/')}/.well-known/openid-configuration"


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
        client_kwargs={"scope": "openid email profile"},
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
    """Return existing ``Person`` by ``oidc_subject``, or create a new one."""
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
    person = Person(
        naam=name or email,
        email=email,
        oidc_subject=sub,
    )
    db.add(person)
    await db.flush()
    await db.refresh(person)
    return person


# ---------------------------------------------------------------------------
# Token validation
# ---------------------------------------------------------------------------


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

    oauth = get_oauth(settings)
    if oauth is None:
        return None

    # Use the userinfo endpoint to validate the token.  This is the simplest
    # approach and works with opaque tokens as well as JWTs.
    import httpx

    metadata_url = _get_discovery_url(settings)
    async with httpx.AsyncClient() as client:
        try:
            meta_resp = await client.get(metadata_url)
            meta_resp.raise_for_status()
            metadata = meta_resp.json()
            userinfo_url = metadata["userinfo_endpoint"]

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
