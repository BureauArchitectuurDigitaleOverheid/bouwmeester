"""Security tests for is_agent mass assignment guard and security headers."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from bouwmeester.core.auth import get_optional_user
from bouwmeester.core.database import get_db

# ---------------------------------------------------------------------------
# Fixtures: build clients with a specific authenticated user injected
# ---------------------------------------------------------------------------


@pytest.fixture
def _test_app():
    """Create a fresh app instance for auth-override tests."""
    from bouwmeester.core.app import create_app

    return create_app()


@pytest.fixture
async def authed_client(db_session, _test_app, create_person, request):
    """HTTPX client with an authenticated user injected via dependency override.

    Use ``@pytest.mark.parametrize("authed_client", [True], indirect=True)``
    for admin, or ``[False]`` for non-admin.
    """
    is_admin = request.param
    user = await create_person(
        naam="Auth Override",
        prefix="auth",
        is_admin=is_admin,
    )

    app = _test_app

    async def _override_get_db():
        yield db_session

    def _override_get_user():
        return user

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_optional_user] = _override_get_user

    transport = ASGITransport(app=app)

    # A Bearer header exempts requests from CSRF checks (line 72 of csrf.py).
    # The token value doesn't matter because get_optional_user is overridden.
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer test-override"},
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Security headers tests
# ---------------------------------------------------------------------------


async def test_security_headers_present(client):
    """All responses include standard security headers."""
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


# ---------------------------------------------------------------------------
# is_agent guard tests — integration tests hitting the real route
# ---------------------------------------------------------------------------


async def test_update_person_is_agent_allowed_in_dev_mode(client, sample_person):
    """In dev mode (no OIDC, current_user=None), is_agent update goes through."""
    resp = await client.put(
        f"/api/people/{sample_person.id}",
        json={"is_agent": True},
    )
    assert resp.status_code == 200
    assert resp.json()["is_agent"] is True


@pytest.mark.parametrize("authed_client", [False], indirect=True)
async def test_update_person_is_agent_rejected_for_non_admin(
    authed_client, sample_person
):
    """Non-admin user gets 403 when trying to set is_agent."""
    resp = await authed_client.put(
        f"/api/people/{sample_person.id}",
        json={"is_agent": True},
    )
    assert resp.status_code == 403


@pytest.mark.parametrize("authed_client", [True], indirect=True)
async def test_update_person_is_agent_allowed_for_admin(authed_client, sample_person):
    """Admin user CAN set is_agent."""
    resp = await authed_client.put(
        f"/api/people/{sample_person.id}",
        json={"is_agent": True},
    )
    assert resp.status_code == 200
    assert resp.json()["is_agent"] is True


@pytest.mark.parametrize("authed_client", [False], indirect=True)
async def test_update_person_without_is_agent_allowed_for_non_admin(
    authed_client, sample_person
):
    """Non-admin can update other fields when is_agent is not in the payload."""
    resp = await authed_client.put(
        f"/api/people/{sample_person.id}",
        json={"naam": "Nieuwe Naam"},
    )
    assert resp.status_code == 200
    assert resp.json()["naam"] == "Nieuwe Naam"
