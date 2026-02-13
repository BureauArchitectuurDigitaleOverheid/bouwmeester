"""Tests for API key authentication and lifecycle."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.api_key import generate_api_key, hash_api_key, verify_api_key
from bouwmeester.models.person import Person

# ---------------------------------------------------------------------------
# Unit tests for core/api_key.py
# ---------------------------------------------------------------------------


class TestApiKeyUtility:
    """Unit tests for generate, hash, verify functions."""

    def test_generate_api_key_prefix(self):
        key = generate_api_key()
        assert key.startswith("bm_")

    def test_generate_api_key_length(self):
        key = generate_api_key()
        # bm_ (3 chars) + 32 hex chars = 35
        assert len(key) == 35

    def test_generate_api_key_uniqueness(self):
        keys = {generate_api_key() for _ in range(100)}
        assert len(keys) == 100

    def test_hash_api_key_deterministic(self):
        key = "bm_abc123"
        assert hash_api_key(key) == hash_api_key(key)

    def test_hash_api_key_different_keys(self):
        assert hash_api_key("bm_key1") != hash_api_key("bm_key2")

    def test_verify_api_key_correct(self):
        key = generate_api_key()
        hashed = hash_api_key(key)
        assert verify_api_key(key, hashed) is True

    def test_verify_api_key_incorrect(self):
        key = generate_api_key()
        hashed = hash_api_key(key)
        assert verify_api_key("bm_wrong_key_value_here_aaa", hashed) is False

    def test_hash_is_hex_sha256(self):
        key = "bm_test"
        hashed = hash_api_key(key)
        # SHA-256 hex digest is 64 chars
        assert len(hashed) == 64
        assert all(c in "0123456789abcdef" for c in hashed)


# ---------------------------------------------------------------------------
# Integration tests for API key endpoints
# ---------------------------------------------------------------------------


async def test_create_agent_returns_api_key(client):
    """POST /api/people with is_agent=True returns a one-time API key."""
    resp = await client.post(
        "/api/people",
        json={"naam": "TestAgent", "is_agent": True},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["is_agent"] is True
    assert data["api_key"] is not None
    assert data["api_key"].startswith("bm_")
    assert data["has_api_key"] is True


async def test_create_non_agent_no_api_key(client):
    """POST /api/people without is_agent does not return an API key."""
    resp = await client.post(
        "/api/people",
        json={"naam": "NormalPerson", "email": "normal@test.com"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["is_agent"] is False
    assert data.get("api_key") is None
    assert "api_key" not in data or data["api_key"] is None


async def test_get_agent_hides_api_key(client):
    """GET /api/people/{id} never returns the plaintext API key."""
    create_resp = await client.post(
        "/api/people",
        json={"naam": "HiddenKeyAgent", "is_agent": True},
    )
    assert create_resp.status_code == 201
    agent_id = create_resp.json()["id"]

    get_resp = await client.get(f"/api/people/{agent_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    # api_key field should not be present on GET (only on create response)
    assert "api_key" not in data
    assert data["has_api_key"] is True


async def test_rotate_api_key(client):
    """POST /api/people/{id}/rotate-api-key generates a new key."""
    create_resp = await client.post(
        "/api/people",
        json={"naam": "RotateAgent", "is_agent": True},
    )
    assert create_resp.status_code == 201
    agent_id = create_resp.json()["id"]
    original_key = create_resp.json()["api_key"]

    rotate_resp = await client.post(f"/api/people/{agent_id}/rotate-api-key")
    assert rotate_resp.status_code == 200
    data = rotate_resp.json()
    assert data["api_key"].startswith("bm_")
    assert data["person_id"] == agent_id
    # The new key should be different from the original
    assert data["api_key"] != original_key


async def test_rotate_api_key_non_agent_400(client, sample_person):
    """POST /api/people/{id}/rotate-api-key for non-agent returns 400."""
    resp = await client.post(f"/api/people/{sample_person.id}/rotate-api-key")
    assert resp.status_code == 400


async def test_rotate_api_key_not_found(client):
    """POST /api/people/{id}/rotate-api-key for non-existent person returns 404."""
    fake_id = uuid.uuid4()
    resp = await client.post(f"/api/people/{fake_id}/rotate-api-key")
    assert resp.status_code == 404


async def test_api_key_hash_stored_in_db(client, db_session: AsyncSession):
    """Creating an agent stores a hash, not the plaintext key."""
    create_resp = await client.post(
        "/api/people",
        json={"naam": "DBCheckAgent", "is_agent": True},
    )
    assert create_resp.status_code == 201
    agent_id = create_resp.json()["id"]
    plaintext_key = create_resp.json()["api_key"]

    # Directly query the DB to verify hash storage
    person = await db_session.get(Person, uuid.UUID(agent_id))
    assert person is not None
    assert person.api_key_hash is not None
    # Verify the hash matches
    assert verify_api_key(plaintext_key, person.api_key_hash) is True


async def test_rotate_invalidates_old_key(client, db_session: AsyncSession):
    """After rotation, the old key's hash should no longer match."""
    create_resp = await client.post(
        "/api/people",
        json={"naam": "RotateInvalidateAgent", "is_agent": True},
    )
    agent_id = create_resp.json()["id"]
    old_key = create_resp.json()["api_key"]

    rotate_resp = await client.post(f"/api/people/{agent_id}/rotate-api-key")
    new_key = rotate_resp.json()["api_key"]

    person = await db_session.get(Person, uuid.UUID(agent_id))
    # Old key should no longer verify
    assert verify_api_key(old_key, person.api_key_hash) is False
    # New key should verify
    assert verify_api_key(new_key, person.api_key_hash) is True


async def test_update_agent_preserves_has_api_key(client):
    """PUT /api/people/{id} returns has_api_key=True for agents with keys."""
    create_resp = await client.post(
        "/api/people",
        json={"naam": "UpdateAgent", "is_agent": True},
    )
    assert create_resp.status_code == 201
    agent_id = create_resp.json()["id"]

    update_resp = await client.put(
        f"/api/people/{agent_id}",
        json={"description": "Updated description"},
    )
    assert update_resp.status_code == 200
    data = update_resp.json()
    assert data["has_api_key"] is True
    # api_key field should not be present on update response
    assert "api_key" not in data


# ---------------------------------------------------------------------------
# Middleware-level auth tests
#
# The middleware opens its own DB session (separate from the test transaction),
# so it can only see committed data.  Tests that verify middleware rejection
# (invalid key, wrong prefix) work fine.  Tests that require a valid key to
# be recognised use a committed fixture instead.
# ---------------------------------------------------------------------------


async def test_invalid_bm_key_returns_401(client):
    """An invalid bm_ Bearer token is rejected immediately with 401."""
    resp = await client.get(
        "/api/people",
        headers={"Authorization": "Bearer bm_this_key_does_not_exist_aa"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid API key"


async def test_malformed_bm_key_short(client):
    """A bm_ key that is too short is rejected."""
    resp = await client.get(
        "/api/people",
        headers={"Authorization": "Bearer bm_short"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid API key"


async def test_malformed_bm_key_non_hex(client):
    """A bm_ key with non-hex characters is rejected."""
    resp = await client.get(
        "/api/people",
        headers={"Authorization": "Bearer bm_zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid API key"


async def test_malformed_bm_key_empty_after_prefix(client):
    """A bare bm_ prefix with no key body is rejected."""
    resp = await client.get(
        "/api/people",
        headers={"Authorization": "Bearer bm_"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid API key"


async def test_invalid_bm_key_does_not_fall_through(client):
    """Even in dev mode (no OIDC), an invalid bm_ key must not pass through."""
    # This specifically tests the fix: previously invalid bm_ keys would
    # fall through to the dev-mode passthrough and succeed.
    resp = await client.post(
        "/api/people",
        json={"naam": "ShouldNotBeCreated"},
        headers={"Authorization": "Bearer bm_bogus_key_value_1234567890"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Auth dependency tests (via _person_from_api_key)
#
# These test that the auth dependency correctly resolves a Person from the
# scope set by the middleware.  We simulate the middleware's scope injection
# directly to avoid the separate-session issue.
# ---------------------------------------------------------------------------


async def test_person_from_api_key_resolves(db_session: AsyncSession):
    """_person_from_api_key returns the correct Person when scope is set."""
    from unittest.mock import MagicMock

    from bouwmeester.core.auth import _person_from_api_key

    # Create an agent with a key hash in the test session
    person = Person(
        id=uuid.uuid4(),
        naam="AuthTestAgent",
        is_agent=True,
        is_active=True,
    )
    db_session.add(person)
    await db_session.flush()

    # Simulate what the middleware does: set _api_key_person_id in scope
    request = MagicMock()
    request.scope = {"_api_key_person_id": person.id}

    result = await _person_from_api_key(request, db_session)
    assert result is not None
    assert result.id == person.id
    assert result.naam == "AuthTestAgent"


async def test_person_from_api_key_inactive_rejected(db_session: AsyncSession):
    """_person_from_api_key returns None for inactive persons."""
    from unittest.mock import MagicMock

    from bouwmeester.core.auth import _person_from_api_key

    person = Person(
        id=uuid.uuid4(),
        naam="InactiveAgent",
        is_agent=True,
        is_active=False,
    )
    db_session.add(person)
    await db_session.flush()

    request = MagicMock()
    request.scope = {"_api_key_person_id": person.id}

    result = await _person_from_api_key(request, db_session)
    assert result is None


async def test_person_from_api_key_non_agent_rejected(db_session: AsyncSession):
    """_person_from_api_key returns None for non-agent persons."""
    from unittest.mock import MagicMock

    from bouwmeester.core.auth import _person_from_api_key

    person = Person(
        id=uuid.uuid4(),
        naam="RegularPerson",
        is_agent=False,
        is_active=True,
    )
    db_session.add(person)
    await db_session.flush()

    request = MagicMock()
    request.scope = {"_api_key_person_id": person.id}

    result = await _person_from_api_key(request, db_session)
    assert result is None


async def test_duplicate_agent_name_rejected(client):
    """Creating two agents with the same name returns 409."""
    resp1 = await client.post(
        "/api/people",
        json={"naam": "DuplicateAgent", "is_agent": True},
    )
    assert resp1.status_code == 201

    resp2 = await client.post(
        "/api/people",
        json={"naam": "DuplicateAgent", "is_agent": True},
    )
    assert resp2.status_code == 409


async def test_person_from_api_key_no_scope():
    """_person_from_api_key returns None when no API key scope is set."""
    from unittest.mock import MagicMock

    from bouwmeester.core.auth import _person_from_api_key

    request = MagicMock()
    request.scope = {}

    result = await _person_from_api_key(request, MagicMock())
    assert result is None
