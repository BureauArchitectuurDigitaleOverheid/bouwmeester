"""Pydantic schemas for WebAuthn biometric re-authentication."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class WebAuthnCredentialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    label: str
    created_at: datetime
    last_used_at: datetime | None = None


class RegisterOptionsRequest(BaseModel):
    """Empty request body — user comes from session."""


class RegisterOptionsResponse(BaseModel):
    """JSON-serialised PublicKeyCredentialCreationOptions."""

    options_json: str  # JSON string for the browser


class RegisterVerifyRequest(BaseModel):
    """Browser's attestation response after navigator.credentials.create()."""

    credential: str  # JSON string from the browser
    label: str = "Biometrie"


class AuthenticateOptionsRequest(BaseModel):
    """Request body for generating authentication options."""

    person_id: UUID


class AuthenticateOptionsResponse(BaseModel):
    """JSON-serialised PublicKeyCredentialRequestOptions."""

    options_json: str  # JSON string for the browser


class AuthenticateVerifyRequest(BaseModel):
    """Browser's assertion response after navigator.credentials.get()."""

    person_id: UUID
    credential: str  # JSON string from the browser
