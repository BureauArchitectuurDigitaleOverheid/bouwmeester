"""Tests for access request endpoints (submit, status check, admin review)."""

import uuid

import pytest
from sqlalchemy import select

from bouwmeester.core import whitelist
from bouwmeester.models.access_request import AccessRequest
from bouwmeester.models.notification import Notification
from bouwmeester.models.person import Person
from bouwmeester.models.whitelist_email import WhitelistEmail


@pytest.fixture(autouse=True)
def _whitelist_active():
    """Enable the whitelist so access-denied logic triggers."""
    old_active = whitelist._whitelist_active
    old_emails = whitelist._allowed_emails
    whitelist._whitelist_active = True
    whitelist._allowed_emails = {"existing@example.com"}
    yield
    whitelist._whitelist_active = old_active
    whitelist._allowed_emails = old_emails


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Clear the access-request rate limiter between tests."""
    from bouwmeester.api.routes.auth import _access_request_rate_store

    _access_request_rate_store.clear()
    yield
    _access_request_rate_store.clear()


# ---------------------------------------------------------------------------
# POST /api/auth/request-access
# ---------------------------------------------------------------------------


async def test_request_access_creates_pending(client, db_session):
    """Submitting an access request creates a pending record."""
    resp = await client.post(
        "/api/auth/request-access",
        json={"email": "new@example.com", "naam": "New User"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert data["has_pending"] is True

    # Verify in DB
    result = await db_session.execute(
        select(AccessRequest).where(AccessRequest.email == "new@example.com")
    )
    req = result.scalar_one()
    assert req.status == "pending"
    assert req.naam == "New User"


async def test_request_access_duplicate_returns_already_pending(client, db_session):
    """Submitting a second request for the same email returns already_pending."""
    # First request
    resp1 = await client.post(
        "/api/auth/request-access",
        json={"email": "dup@example.com", "naam": "Dup User"},
    )
    assert resp1.json()["status"] == "pending"

    # Second request — same email
    resp2 = await client.post(
        "/api/auth/request-access",
        json={"email": "dup@example.com", "naam": "Dup User Again"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "already_pending"


async def test_request_access_already_allowed(client):
    """If email is already on whitelist, returns already_allowed."""
    resp = await client.post(
        "/api/auth/request-access",
        json={"email": "existing@example.com", "naam": "Existing"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "already_allowed"
    assert resp.json()["has_pending"] is False


async def test_request_access_notifies_admins(client, db_session):
    """Submitting an access request sends notifications to admin users."""
    admin = Person(
        id=uuid.uuid4(),
        naam="Admin User",
        email="admin@example.com",
        is_admin=True,
    )
    db_session.add(admin)
    await db_session.flush()

    resp = await client.post(
        "/api/auth/request-access",
        json={"email": "notifier@example.com", "naam": "Notifier"},
    )
    assert resp.status_code == 200

    # Check notification was created for admin
    result = await db_session.execute(
        select(Notification).where(
            Notification.person_id == admin.id,
            Notification.type == "access_request",
        )
    )
    notif = result.scalar_one()
    assert "Notifier" in notif.title


async def test_request_access_email_normalized(client, db_session):
    """Email should be lowercased and stripped."""
    resp = await client.post(
        "/api/auth/request-access",
        json={"email": "  Upper@Example.COM  ", "naam": "Upper"},
    )
    assert resp.status_code == 200

    result = await db_session.execute(
        select(AccessRequest).where(AccessRequest.email == "upper@example.com")
    )
    assert result.scalar_one() is not None


async def test_request_access_rate_limit(client):
    """After exceeding the rate limit, returns 429."""
    for i in range(5):
        resp = await client.post(
            "/api/auth/request-access",
            json={"email": f"rate{i}@example.com", "naam": f"Rate {i}"},
        )
        assert resp.status_code == 200

    # 6th request should be rate limited
    resp = await client.post(
        "/api/auth/request-access",
        json={"email": "rate5@example.com", "naam": "Rate 5"},
    )
    assert resp.status_code == 429


# ---------------------------------------------------------------------------
# GET /api/auth/access-request-status
# ---------------------------------------------------------------------------


async def test_access_request_status_no_request(client):
    """Status check for unknown email returns no pending, null status."""
    resp = await client.get(
        "/api/auth/access-request-status",
        params={"email": "nobody@example.com"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_pending"] is False
    assert data["status"] is None


async def test_access_request_status_pending(client, db_session):
    """Status check for a pending request returns pending."""
    req = AccessRequest(email="pending@example.com", naam="Pending User")
    db_session.add(req)
    await db_session.flush()

    resp = await client.get(
        "/api/auth/access-request-status",
        params={"email": "pending@example.com"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_pending"] is True
    assert data["status"] == "pending"


async def test_access_request_status_already_allowed(client):
    """Status check for a whitelisted email returns approved."""
    resp = await client.get(
        "/api/auth/access-request-status",
        params={"email": "existing@example.com"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"
    assert data["has_pending"] is False


async def test_access_request_status_denied(client, db_session):
    """Status check for a denied request returns denied with reason."""
    req = AccessRequest(
        email="denied@example.com",
        naam="Denied User",
        status="denied",
        deny_reason="Not eligible",
    )
    db_session.add(req)
    await db_session.flush()

    resp = await client.get(
        "/api/auth/access-request-status",
        params={"email": "denied@example.com"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_pending"] is False
    assert data["status"] == "denied"
    assert data["deny_reason"] == "Not eligible"


# ---------------------------------------------------------------------------
# GET /api/admin/access-requests
# ---------------------------------------------------------------------------


async def test_admin_list_access_requests(client, db_session):
    """Admin can list all access requests."""
    for i in range(3):
        db_session.add(
            AccessRequest(email=f"list{i}@example.com", naam=f"List {i}")
        )
    await db_session.flush()

    resp = await client.get("/api/admin/access-requests")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 3


async def test_admin_list_access_requests_filter_pending(client, db_session):
    """Admin can filter by status=pending."""
    db_session.add(
        AccessRequest(email="pend@example.com", naam="Pend", status="pending")
    )
    db_session.add(
        AccessRequest(email="done@example.com", naam="Done", status="approved")
    )
    await db_session.flush()

    resp = await client.get(
        "/api/admin/access-requests", params={"status": "pending"}
    )
    assert resp.status_code == 200
    data = resp.json()
    emails = [r["email"] for r in data]
    assert "pend@example.com" in emails
    assert "done@example.com" not in emails


# ---------------------------------------------------------------------------
# PATCH /api/admin/access-requests/{id} — approve
# ---------------------------------------------------------------------------


async def test_admin_approve_access_request(client, db_session):
    """Approving adds the email to the whitelist."""
    req = AccessRequest(email="approve@example.com", naam="Approve Me")
    db_session.add(req)
    await db_session.flush()
    req_id = str(req.id)

    resp = await client.patch(
        f"/api/admin/access-requests/{req_id}",
        json={"action": "approve"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"

    # Verify whitelist entry was created
    result = await db_session.execute(
        select(WhitelistEmail).where(
            WhitelistEmail.email == "approve@example.com"
        )
    )
    assert result.scalar_one_or_none() is not None


async def test_admin_approve_already_reviewed(client, db_session):
    """Approving an already-reviewed request returns 409."""
    req = AccessRequest(
        email="already@example.com", naam="Already", status="approved"
    )
    db_session.add(req)
    await db_session.flush()

    resp = await client.patch(
        f"/api/admin/access-requests/{req.id}",
        json={"action": "approve"},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# PATCH /api/admin/access-requests/{id} — deny
# ---------------------------------------------------------------------------


async def test_admin_deny_access_request(client, db_session):
    """Denying records the reason and sets status to denied."""
    req = AccessRequest(email="deny@example.com", naam="Deny Me")
    db_session.add(req)
    await db_session.flush()

    resp = await client.patch(
        f"/api/admin/access-requests/{req.id}",
        json={"action": "deny", "deny_reason": "Not eligible"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "denied"
    assert data["deny_reason"] == "Not eligible"


async def test_admin_deny_without_reason(client, db_session):
    """Denying without a reason is allowed."""
    req = AccessRequest(email="denynr@example.com", naam="Deny No Reason")
    db_session.add(req)
    await db_session.flush()

    resp = await client.patch(
        f"/api/admin/access-requests/{req.id}",
        json={"action": "deny"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "denied"
    assert data["deny_reason"] is None


# ---------------------------------------------------------------------------
# PATCH /api/admin/access-requests/{id} — not found
# ---------------------------------------------------------------------------


async def test_admin_review_not_found(client):
    """Reviewing a non-existent request returns 404."""
    resp = await client.patch(
        f"/api/admin/access-requests/{uuid.uuid4()}",
        json={"action": "approve"},
    )
    assert resp.status_code == 404
