"""WebAuthn routes -- biometric credential registration and authentication."""

from __future__ import annotations

import json as json_mod
import logging
import time
from collections import OrderedDict
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from bouwmeester.core.auth import CurrentUser
from bouwmeester.core.config import Settings, get_settings
from bouwmeester.core.database import get_db
from bouwmeester.core.whitelist import is_email_allowed
from bouwmeester.models.person import Person
from bouwmeester.models.webauthn_credential import WebAuthnCredential
from bouwmeester.schema.webauthn import (
    AuthenticateOptionsRequest,
    AuthenticateVerifyRequest,
    RegisterVerifyRequest,
    WebAuthnCredentialResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webauthn", tags=["webauthn"])


def _init_webauthn_session(session: dict, person: Person) -> None:
    """Populate a cleared session dict for a WebAuthn-only login."""
    session["webauthn_session"] = True
    session["person_db_id"] = str(person.id)
    session["person_email"] = person.email or ""
    session["person_name"] = person.naam
    session["person_sub"] = person.oidc_subject or ""
    session["is_admin"] = person.is_admin
    session["_rotate"] = True


# ---------------------------------------------------------------------------
# Rate limiter for authentication endpoints (unauthenticated).
# NOTE: In-process store — with multiple workers each has its own state,
# so effective limit is N × _RATE_LIMIT_MAX per window. Acceptable for
# this use case; switch to Redis if stricter limits are needed.
# ---------------------------------------------------------------------------
_RATE_LIMIT_WINDOW = 60
_RATE_LIMIT_MAX = 20
_RATE_LIMIT_MAX_KEYS = 10_000
_rate_limit_store: OrderedDict[str, list[float]] = OrderedDict()


def _check_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window_start = now - _RATE_LIMIT_WINDOW

    timestamps = _rate_limit_store.get(client_ip, [])
    pruned = [t for t in timestamps if t > window_start]

    if len(pruned) >= _RATE_LIMIT_MAX:
        _rate_limit_store[client_ip] = pruned
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests, try again later",
        )

    pruned.append(now)
    _rate_limit_store[client_ip] = pruned
    _rate_limit_store.move_to_end(client_ip)

    while len(_rate_limit_store) > _RATE_LIMIT_MAX_KEYS:
        _rate_limit_store.popitem(last=False)


# ---------------------------------------------------------------------------
# GET /credentials -- list user's registered credentials
# ---------------------------------------------------------------------------


@router.get("/credentials", response_model=list[WebAuthnCredentialResponse])
async def list_credentials(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> list[WebAuthnCredentialResponse]:
    result = await db.execute(
        select(WebAuthnCredential)
        .where(WebAuthnCredential.person_id == current_user.id)
        .order_by(WebAuthnCredential.created_at.desc())
    )
    return [
        WebAuthnCredentialResponse.model_validate(c) for c in result.scalars().all()
    ]


# ---------------------------------------------------------------------------
# DELETE /credentials/{id} -- delete a credential
# ---------------------------------------------------------------------------


@router.delete("/credentials/{credential_id}", status_code=204)
async def delete_credential(
    credential_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        delete(WebAuthnCredential).where(
            WebAuthnCredential.id == credential_id,
            WebAuthnCredential.person_id == current_user.id,
        )
    )
    if result.rowcount == 0:  # type: ignore[union-attr]
        raise HTTPException(status_code=404, detail="Credential niet gevonden")


# ---------------------------------------------------------------------------
# POST /register/options -- generate registration challenge
# ---------------------------------------------------------------------------


@router.post("/register/options")
async def register_options(
    request: Request,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    # Get existing credentials to exclude them.
    result = await db.execute(
        select(WebAuthnCredential.credential_id).where(
            WebAuthnCredential.person_id == current_user.id
        )
    )
    existing = [PublicKeyCredentialDescriptor(id=row[0]) for row in result.all()]

    options = generate_registration_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_name=current_user.email or current_user.naam,
        user_id=current_user.id.bytes,
        user_display_name=current_user.naam,
        exclude_credentials=existing,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        timeout=60000,
    )

    options_json = options_to_json(options)

    # Store the challenge in the session for verification.
    request.session["webauthn_reg_challenge"] = options.challenge.hex()

    return {"options_json": options_json}


# ---------------------------------------------------------------------------
# POST /register/verify -- verify attestation and store credential
# ---------------------------------------------------------------------------


@router.post("/register/verify", response_model=WebAuthnCredentialResponse)
async def register_verify(
    request: Request,
    body: RegisterVerifyRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> WebAuthnCredentialResponse:
    challenge_hex = request.session.pop("webauthn_reg_challenge", None)
    if not challenge_hex:
        raise HTTPException(
            status_code=400,
            detail="Geen registratie-uitdaging gevonden",
        )

    expected_challenge = bytes.fromhex(challenge_hex)

    try:
        verification = verify_registration_response(
            credential=body.credential,
            expected_challenge=expected_challenge,
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=settings.WEBAUTHN_ORIGIN,
            require_user_verification=True,
        )
    except Exception as e:
        logger.warning("WebAuthn registration verification failed: %s", e)
        raise HTTPException(
            status_code=400,
            detail="Registratie-verificatie mislukt",
        ) from e

    credential = WebAuthnCredential(
        person_id=current_user.id,
        credential_id=verification.credential_id,
        public_key=verification.credential_public_key,
        sign_count=verification.sign_count,
        label=body.label[:100],
    )
    db.add(credential)
    await db.flush()

    return WebAuthnCredentialResponse.model_validate(credential)


# ---------------------------------------------------------------------------
# POST /authenticate/options -- generate authentication challenge
# ---------------------------------------------------------------------------


@router.post("/authenticate/options")
async def authenticate_options(
    request: Request,
    body: AuthenticateOptionsRequest,
    settings: Settings = Depends(get_settings),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _check_rate_limit(request)

    # Look up credentials for the given person.
    result = await db.execute(
        select(WebAuthnCredential.credential_id).where(
            WebAuthnCredential.person_id == body.person_id
        )
    )
    allow_credentials = [
        PublicKeyCredentialDescriptor(id=row[0]) for row in result.all()
    ]

    if not allow_credentials:
        # Return a generic error to prevent enumerating which users have
        # registered biometric credentials.
        raise HTTPException(
            status_code=400,
            detail="Authenticatie niet beschikbaar",
        )

    options = generate_authentication_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        allow_credentials=allow_credentials,
        user_verification=UserVerificationRequirement.REQUIRED,
        timeout=60000,
    )

    options_json = options_to_json(options)

    # Store challenge and person_id in session for verification.
    request.session["webauthn_auth_challenge"] = options.challenge.hex()
    request.session["webauthn_auth_person_id"] = str(body.person_id)

    return {"options_json": options_json}


# ---------------------------------------------------------------------------
# POST /authenticate/verify -- verify assertion and issue session
# ---------------------------------------------------------------------------


@router.post("/authenticate/verify")
async def authenticate_verify(
    request: Request,
    body: AuthenticateVerifyRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    _check_rate_limit(request)

    challenge_hex = request.session.pop("webauthn_auth_challenge", None)
    expected_person_id = request.session.pop("webauthn_auth_person_id", None)

    if not challenge_hex or not expected_person_id:
        raise HTTPException(
            status_code=400,
            detail="Geen authenticatie-uitdaging gevonden",
        )

    if str(body.person_id) != expected_person_id:
        raise HTTPException(status_code=400, detail="person_id komt niet overeen")

    expected_challenge = bytes.fromhex(challenge_hex)

    # Extract the credential ID from the browser's assertion response so we
    # can look up the exact credential rather than iterating all of them.
    try:
        cred_data = json_mod.loads(body.credential)
        raw_id_b64 = cred_data.get("rawId") or cred_data.get("id")
        if not raw_id_b64:
            raise ValueError("missing rawId/id")
        credential_id_bytes = base64url_to_bytes(raw_id_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="Ongeldig credential formaat")

    result = await db.execute(
        select(WebAuthnCredential).where(
            WebAuthnCredential.credential_id == credential_id_bytes,
            WebAuthnCredential.person_id == body.person_id,
        )
    )
    matched_credential = result.scalar_one_or_none()

    if not matched_credential:
        raise HTTPException(status_code=400, detail="Authenticatie-verificatie mislukt")

    try:
        verified = verify_authentication_response(
            credential=body.credential,
            expected_challenge=expected_challenge,
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=settings.WEBAUTHN_ORIGIN,
            credential_public_key=matched_credential.public_key,
            credential_current_sign_count=matched_credential.sign_count,
            require_user_verification=True,
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Authenticatie-verificatie mislukt")

    # Update sign count and last_used_at.
    matched_credential.sign_count = verified.new_sign_count
    matched_credential.last_used_at = datetime.now(UTC)

    # Load the person to check whitelist and set up session.
    person = await db.get(Person, body.person_id)
    if person is None or not person.is_active:
        raise HTTPException(
            status_code=403,
            detail="Gebruiker niet gevonden of inactief",
        )

    email = person.email or ""
    if not is_email_allowed(email):
        raise HTTPException(
            status_code=403,
            detail="Toegang geweigerd — niet op de whitelist",
        )

    # Create a WebAuthn-only session (no OIDC tokens).
    session = request.session
    session.clear()
    _init_webauthn_session(session, person)

    logger.info("WebAuthn authentication successful for %s", email)

    return {"authenticated": True}
