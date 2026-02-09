"""Tests for temporal corpus node features.

Covers: create with temporal records, update (title rename / status change),
dissolution, active-only filtering, history endpoints, and wijzig_datum override.
"""

import uuid
from datetime import date

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def sample_corpus_node(client: AsyncClient) -> dict:
    """Create a corpus node (dossier) via the API."""
    resp = await client.post(
        "/api/nodes",
        json={
            "title": "Test Dossier",
            "node_type": "dossier",
            "description": "Een test dossier",
            "status": "actief",
        },
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class TestCreate:
    async def test_create_sets_geldig_van(self, client, sample_corpus_node):
        """Created node gets geldig_van = today, geldig_tot = null."""
        assert sample_corpus_node["geldig_van"] == str(date.today())
        assert sample_corpus_node["geldig_tot"] is None

    async def test_create_produces_title_record(self, client, sample_corpus_node):
        """Creating a node also creates a temporal title record."""
        nid = sample_corpus_node["id"]
        resp = await client.get(f"/api/nodes/{nid}/history/titles")
        assert resp.status_code == 200
        records = resp.json()
        assert len(records) == 1
        assert records[0]["title"] == "Test Dossier"
        assert records[0]["geldig_tot"] is None

    async def test_create_produces_status_record(self, client, sample_corpus_node):
        """Creating a node also creates a temporal status record."""
        nid = sample_corpus_node["id"]
        resp = await client.get(f"/api/nodes/{nid}/history/statuses")
        assert resp.status_code == 200
        records = resp.json()
        assert len(records) == 1
        assert records[0]["status"] == "actief"
        assert records[0]["geldig_tot"] is None


# ---------------------------------------------------------------------------
# Update — title rename
# ---------------------------------------------------------------------------


class TestTitleRename:
    async def test_rename_closes_old_title(self, client, sample_corpus_node):
        """Renaming closes the old title record and opens a new one."""
        nid = sample_corpus_node["id"]
        resp = await client.put(
            f"/api/nodes/{nid}",
            json={"title": "Nieuw Dossier"},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Nieuw Dossier"

        hist = await client.get(f"/api/nodes/{nid}/history/titles")
        records = hist.json()
        assert len(records) == 2
        # Most recent first (desc order)
        assert records[0]["title"] == "Nieuw Dossier"
        assert records[0]["geldig_tot"] is None
        assert records[1]["title"] == "Test Dossier"
        assert records[1]["geldig_tot"] is not None


# ---------------------------------------------------------------------------
# Update — status change
# ---------------------------------------------------------------------------


class TestStatusChange:
    async def test_status_change_closes_old_status(self, client, sample_corpus_node):
        """Changing status closes the old status record and opens a new one."""
        nid = sample_corpus_node["id"]
        resp = await client.put(
            f"/api/nodes/{nid}",
            json={"status": "gepauzeerd"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "gepauzeerd"

        hist = await client.get(f"/api/nodes/{nid}/history/statuses")
        records = hist.json()
        assert len(records) == 2
        assert records[0]["status"] == "gepauzeerd"
        assert records[0]["geldig_tot"] is None
        assert records[1]["status"] == "actief"
        assert records[1]["geldig_tot"] is not None


# ---------------------------------------------------------------------------
# Dissolution
# ---------------------------------------------------------------------------


class TestDissolution:
    async def test_dissolve_sets_geldig_tot(self, client, sample_corpus_node):
        """Setting geldig_tot dissolves the node."""
        nid = sample_corpus_node["id"]
        resp = await client.put(
            f"/api/nodes/{nid}",
            json={"geldig_tot": "2025-11-01"},
        )
        assert resp.status_code == 200
        assert resp.json()["geldig_tot"] == "2025-11-01"

    async def test_dissolved_excluded_from_list(self, client, sample_corpus_node):
        """Dissolved nodes don't appear in GET /nodes."""
        nid = sample_corpus_node["id"]
        await client.put(
            f"/api/nodes/{nid}",
            json={"geldig_tot": "2025-11-01"},
        )

        resp = await client.get("/api/nodes")
        ids = [n["id"] for n in resp.json()]
        assert nid not in ids

    async def test_dissolve_closes_temporal_records(self, client, sample_corpus_node):
        """Dissolution closes all active temporal records."""
        nid = sample_corpus_node["id"]
        await client.put(
            f"/api/nodes/{nid}",
            json={"geldig_tot": "2025-11-01"},
        )

        # All temporal records should be closed
        for kind in ("titles", "statuses"):
            hist = await client.get(f"/api/nodes/{nid}/history/{kind}")
            for record in hist.json():
                assert record["geldig_tot"] is not None


# ---------------------------------------------------------------------------
# Idempotent updates
# ---------------------------------------------------------------------------


class TestIdempotent:
    async def test_same_title_no_new_record(self, client, sample_corpus_node):
        """Updating with the same title does not create a new temporal record."""
        nid = sample_corpus_node["id"]
        await client.put(
            f"/api/nodes/{nid}",
            json={"title": "Test Dossier"},
        )

        hist = await client.get(f"/api/nodes/{nid}/history/titles")
        records = hist.json()
        assert len(records) == 1

    async def test_same_status_no_new_record(self, client, sample_corpus_node):
        """Updating with the same status does not create a new temporal record."""
        nid = sample_corpus_node["id"]
        await client.put(
            f"/api/nodes/{nid}",
            json={"status": "actief"},
        )

        hist = await client.get(f"/api/nodes/{nid}/history/statuses")
        records = hist.json()
        assert len(records) == 1


# ---------------------------------------------------------------------------
# wijzig_datum override
# ---------------------------------------------------------------------------


class TestWijzigDatum:
    async def test_wijzig_datum_override(self, client, sample_corpus_node):
        """Custom wijzig_datum overrides the effective date for temporal records."""
        nid = sample_corpus_node["id"]
        resp = await client.put(
            f"/api/nodes/{nid}",
            json={"title": "Titel Achteraf", "wijzig_datum": "2025-06-01"},
        )
        assert resp.status_code == 200

        hist = await client.get(f"/api/nodes/{nid}/history/titles")
        records = hist.json()
        assert len(records) == 2
        # New record should use the custom date
        new_record = next(r for r in records if r["title"] == "Titel Achteraf")
        assert new_record["geldig_van"] == "2025-06-01"
        # Old record should be closed at the custom date
        old_record = next(r for r in records if r["title"] == "Test Dossier")
        assert old_record["geldig_tot"] == "2025-06-01"


# ---------------------------------------------------------------------------
# History endpoints — 404
# ---------------------------------------------------------------------------


class TestHistory404:
    async def test_title_history_404(self, client):
        resp = await client.get(
            f"/api/nodes/{uuid.uuid4()}/history/titles",
        )
        assert resp.status_code == 404

    async def test_status_history_404(self, client):
        resp = await client.get(
            f"/api/nodes/{uuid.uuid4()}/history/statuses",
        )
        assert resp.status_code == 404
