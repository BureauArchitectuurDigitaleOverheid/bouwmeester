"""Comprehensive API tests for the health endpoints."""


async def test_liveness(client):
    """GET /api/health/live returns 200 with ok status."""
    resp = await client.get("/api/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_readiness(client):
    """GET /api/health/ready returns 200 with ok status."""
    resp = await client.get("/api/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
