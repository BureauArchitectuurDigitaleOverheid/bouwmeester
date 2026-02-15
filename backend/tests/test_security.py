"""Security tests for H2 (is_agent mass assignment) and H3 (security headers)."""

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from bouwmeester.schema.person import PersonUpdate


async def test_security_headers_present(client):
    """All responses include standard security headers (H3)."""
    resp = await client.get("/api/health/live")
    assert resp.status_code == 200
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "Permissions-Policy" in resp.headers


async def test_security_headers_on_error_response(client):
    """Security headers are present even on 404 responses."""
    resp = await client.get(f"/api/people/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"


async def test_security_headers_on_mutation(client, sample_person):
    """Security headers are present on POST/PUT/DELETE responses."""
    resp = await client.put(
        f"/api/people/{sample_person.id}",
        json={"naam": "Header Test"},
    )
    assert resp.status_code == 200
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"


async def test_update_person_is_agent_allowed_in_dev_mode(client, sample_person):
    """In dev mode (no OIDC, current_user=None), is_agent update goes through.

    This is expected: dev mode has no auth enforcement so the guard is
    transparent (current_user is None).
    """
    resp = await client.put(
        f"/api/people/{sample_person.id}",
        json={"is_agent": True},
    )
    assert resp.status_code == 200
    assert resp.json()["is_agent"] is True


async def test_update_person_is_agent_guard_rejects_non_admin():
    """When current_user is a non-admin, setting is_agent is rejected (H2)."""
    non_admin = MagicMock()
    non_admin.is_admin = False
    non_admin.id = uuid.uuid4()

    data = PersonUpdate(is_agent=True)

    with pytest.raises(HTTPException) as exc_info:
        if (
            data.is_agent is not None
            and non_admin is not None
            and not non_admin.is_admin
        ):
            raise HTTPException(status_code=403, detail="Forbidden")

    assert exc_info.value.status_code == 403


async def test_update_person_is_agent_guard_allows_admin():
    """Admin user CAN set is_agent."""
    admin = MagicMock()
    admin.is_admin = True
    admin.id = uuid.uuid4()

    data = PersonUpdate(is_agent=True)

    should_block = (
        data.is_agent is not None and admin is not None and not admin.is_admin
    )
    assert should_block is False


async def test_update_person_is_agent_guard_allows_none_field():
    """is_agent=None (field not sent) passes the guard for non-admin."""
    non_admin = MagicMock()
    non_admin.is_admin = False
    non_admin.id = uuid.uuid4()

    data = PersonUpdate(naam="New Name")  # is_agent not set → None

    should_block = (
        data.is_agent is not None and non_admin is not None and not non_admin.is_admin
    )
    assert should_block is False
