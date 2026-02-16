"""Mattermost integration endpoints.

User-facing endpoints (behind normal auth + CSRF):
  - POST /api/mattermost/link-code   -- generate a link code
  - GET  /api/mattermost/link-status  -- current mapping status
  - DELETE /api/mattermost/link       -- unlink

Webhook endpoints (token-verified, no user auth):
  - POST /api/mattermost/verify-link  -- bot verifies a link code
  - POST /api/mattermost/slash        -- slash command handler
  - POST /api/mattermost/action       -- button action handler
"""

import logging
import secrets
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.config import get_settings
from bouwmeester.core.database import get_db
from bouwmeester.repositories.mattermost_user import MattermostUserRepository
from bouwmeester.schema.mattermost_user import (
    MattermostLinkCodeResponse,
    MattermostLinkStatusResponse,
    MattermostVerifyLinkRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mattermost", tags=["mattermost"])

# Simple in-memory rate limiter for verify-link (keyed by client IP).
_verify_link_attempts: dict[str, list[float]] = defaultdict(list)
_VERIFY_LINK_MAX_ATTEMPTS = 10  # max attempts per window
_VERIFY_LINK_WINDOW_SECONDS = 60  # sliding window


def _check_verify_link_rate_limit(client_ip: str) -> None:
    """Raise 429 if the client has exceeded the verify-link rate limit."""
    now = time.monotonic()
    cutoff = now - _VERIFY_LINK_WINDOW_SECONDS
    # Prune old entries.
    attempts = _verify_link_attempts[client_ip]
    _verify_link_attempts[client_ip] = [t for t in attempts if t > cutoff]
    if len(_verify_link_attempts[client_ip]) >= _VERIFY_LINK_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail="Te veel verificatiepogingen. Probeer het later opnieuw.",
        )
    _verify_link_attempts[client_ip].append(now)


def _get_person_id(
    current_user: OptionalUser,
) -> UUID:
    """Resolve person ID from authenticated user."""
    if current_user is not None:
        return current_user.id
    raise HTTPException(status_code=401, detail="Niet ingelogd")


async def _verify_webhook_token(token: str, db: AsyncSession) -> None:
    """Verify the incoming Mattermost webhook token."""
    from bouwmeester.services.mattermost_service import _load_mattermost_config

    config = await _load_mattermost_config(db)
    settings = get_settings()
    expected = (
        config.get("MATTERMOST_WEBHOOK_TOKEN") or settings.MATTERMOST_WEBHOOK_TOKEN
    )
    if not expected:
        raise HTTPException(
            status_code=503, detail="Mattermost integration not configured"
        )
    if not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=403, detail="Invalid webhook token")


# ---------------------------------------------------------------------------
# User-facing endpoints (authenticated via session)
# ---------------------------------------------------------------------------


@router.post("/link-code", response_model=MattermostLinkCodeResponse)
async def generate_link_code(
    person_id: UUID = Depends(_get_person_id),
    db: AsyncSession = Depends(get_db),
) -> MattermostLinkCodeResponse:
    """Generate a short-lived code for linking to Mattermost."""
    repo = MattermostUserRepository(db)

    # Check if already linked.
    existing = await repo.get_by_person_id(person_id)
    if existing:
        raise HTTPException(
            status_code=409, detail="Account is al gekoppeld aan Mattermost"
        )

    # Rate limit: reject if a code was created less than 60 seconds ago.
    active = await repo.get_active_code(person_id)
    if active and active.created_at > datetime.now(UTC) - timedelta(seconds=60):
        raise HTTPException(
            status_code=429,
            detail="Wacht even voordat je een nieuwe code genereert.",
        )

    link_code = await repo.create_link_code(person_id)
    return MattermostLinkCodeResponse(
        code=link_code.code,
        expires_at=link_code.expires_at,
    )


@router.get("/link-status", response_model=MattermostLinkStatusResponse)
async def get_link_status(
    person_id: UUID = Depends(_get_person_id),
    db: AsyncSession = Depends(get_db),
) -> MattermostLinkStatusResponse:
    """Check whether the current user is linked to Mattermost."""
    repo = MattermostUserRepository(db)
    mapping = await repo.get_by_person_id(person_id)
    if mapping:
        return MattermostLinkStatusResponse(
            linked=True,
            mattermost_username=mapping.mattermost_username,
        )
    return MattermostLinkStatusResponse(linked=False)


@router.delete("/link")
async def unlink_mattermost(
    person_id: UUID = Depends(_get_person_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Remove the Mattermost link for the current user."""
    repo = MattermostUserRepository(db)
    deleted = await repo.delete_by_person_id(person_id)
    if not deleted:
        raise HTTPException(
            status_code=404, detail="Geen Mattermost-koppeling gevonden"
        )
    return {"ok": True}


# ---------------------------------------------------------------------------
# Webhook endpoints (token-verified, no user auth)
# ---------------------------------------------------------------------------


@router.post("/verify-link")
async def verify_link(
    payload: MattermostVerifyLinkRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Verify a link code from the Mattermost bot and create the mapping."""
    # Rate limit by client IP to prevent brute-forcing link codes.
    client_ip = request.client.host if request.client else "unknown"
    _check_verify_link_rate_limit(client_ip)

    # Token verification via header.
    token = request.headers.get("x-mattermost-token", "")
    await _verify_webhook_token(token, db)

    repo = MattermostUserRepository(db)
    link_code = await repo.verify_code(payload.code)
    if not link_code:
        raise HTTPException(status_code=400, detail="Ongeldige of verlopen koppelcode")

    # Check if this Mattermost user is already linked to someone else.
    existing = await repo.get_by_mattermost_user_id(payload.mattermost_user_id)
    if existing:
        raise HTTPException(
            status_code=409, detail="Dit Mattermost-account is al gekoppeld"
        )

    # Create the mapping — handle race condition where another request
    # already linked this user or person concurrently.
    try:
        await repo.create_mapping(
            person_id=link_code.person_id,
            mattermost_user_id=payload.mattermost_user_id,
            mattermost_username=payload.mattermost_username,
        )
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail="Account is al gekoppeld"
        )
    # Clean up the used code.
    await repo.delete_code(payload.code)

    return {"ok": True, "message": "Je account is gekoppeld met Bouwmeester!"}


@router.post("/slash")
async def handle_slash_command(
    request: Request,
    db: AsyncSession = Depends(get_db),
    token: str = Form(""),
    user_id: str = Form(""),
    text: str = Form(""),
    command: str = Form(""),
) -> dict:
    """Handle /bouwmeester slash commands from Mattermost."""
    await _verify_webhook_token(token, db)

    from bouwmeester.services.mattermost_slash_service import MattermostSlashService

    service = MattermostSlashService(db)
    return await service.handle_command(
        mattermost_user_id=user_id,
        command_text=text.strip(),
    )


@router.post("/action")
async def handle_action(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Handle interactive button actions from Mattermost."""
    body = await request.json()

    # Mattermost sends the integration token at the top level for interactive
    # messages.  Never read from "context" — that is user/attacker-controllable.
    token = body.get("token", "")

    # Always verify — reject if no token is provided.
    await _verify_webhook_token(token, db)

    from bouwmeester.services.mattermost_slash_service import MattermostSlashService

    service = MattermostSlashService(db)
    context = body.get("context", {})
    user_id = body.get("user_id", "")

    return await service.handle_action(
        mattermost_user_id=user_id,
        action=context.get("action", ""),
        context=context,
    )
