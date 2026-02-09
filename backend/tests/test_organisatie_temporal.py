"""Tests for temporal organisatie-eenheid features.

Covers: create with temporal records, update (rename/reparent/manager change),
dissolution, active-only filtering, search across historical names,
history endpoints, tree structure, and managed-by endpoint.
"""

import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.person import Person

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def sample_eenheid(client: AsyncClient) -> dict:
    """Create a root organisatie-eenheid."""
    resp = await client.post(
        "/api/organisatie",
        json={"naam": "Ministerie Test", "type": "ministerie"},
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture
async def child_eenheid(client: AsyncClient, sample_eenheid: dict) -> dict:
    """Create a child eenheid under the root."""
    resp = await client.post(
        "/api/organisatie",
        json={
            "naam": "Directie Alpha",
            "type": "directie",
            "parent_id": sample_eenheid["id"],
        },
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture
async def manager_person(db_session: AsyncSession) -> Person:
    """Create a person to use as manager."""
    person = Person(
        id=uuid.uuid4(),
        naam="Manager Test",
        email="manager@example.com",
        functie="directeur",
        is_active=True,
    )
    db_session.add(person)
    await db_session.flush()
    return person


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class TestCreate:
    async def test_create_sets_geldig_van(self, client, sample_eenheid):
        """Created eenheid gets geldig_van = today, geldig_tot = null."""
        assert sample_eenheid["geldig_van"] == str(date.today())
        assert sample_eenheid["geldig_tot"] is None

    async def test_create_produces_naam_record(self, client, sample_eenheid):
        """Creating an eenheid also creates a temporal name record."""
        eid = sample_eenheid["id"]
        resp = await client.get(f"/api/organisatie/{eid}/history/namen")
        assert resp.status_code == 200
        records = resp.json()
        assert len(records) == 1
        assert records[0]["naam"] == "Ministerie Test"
        assert records[0]["geldig_tot"] is None

    async def test_create_produces_parent_record(self, client, child_eenheid):
        """Child eenheid has a temporal parent record."""
        eid = child_eenheid["id"]
        resp = await client.get(f"/api/organisatie/{eid}/history/parents")
        assert resp.status_code == 200
        records = resp.json()
        assert len(records) == 1
        assert records[0]["parent_id"] == child_eenheid["parent_id"]
        assert records[0]["geldig_tot"] is None

    async def test_create_root_no_parent_record(self, client, sample_eenheid):
        """Root eenheid has no temporal parent records."""
        eid = sample_eenheid["id"]
        resp = await client.get(f"/api/organisatie/{eid}/history/parents")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create_with_manager(
        self,
        client,
        manager_person,
    ):
        """Creating with manager_id produces a temporal manager record."""
        resp = await client.post(
            "/api/organisatie",
            json={
                "naam": "Unit met Manager",
                "type": "directie",
                "manager_id": str(manager_person.id),
            },
        )
        assert resp.status_code == 201
        eid = resp.json()["id"]

        hist = await client.get(f"/api/organisatie/{eid}/history/managers")
        assert hist.status_code == 200
        records = hist.json()
        assert len(records) == 1
        assert records[0]["manager_id"] == str(manager_person.id)
        assert records[0]["geldig_tot"] is None


# ---------------------------------------------------------------------------
# Update — rename
# ---------------------------------------------------------------------------


class TestRename:
    async def test_rename_closes_old_name(self, client, sample_eenheid):
        """Renaming closes the old name record and opens a new one."""
        eid = sample_eenheid["id"]
        resp = await client.put(
            f"/api/organisatie/{eid}",
            json={"naam": "Ministerie Nieuw"},
        )
        assert resp.status_code == 200
        assert resp.json()["naam"] == "Ministerie Nieuw"

        hist = await client.get(f"/api/organisatie/{eid}/history/namen")
        records = hist.json()
        assert len(records) == 2
        # Most recent first (desc order)
        assert records[0]["naam"] == "Ministerie Nieuw"
        assert records[0]["geldig_tot"] is None
        assert records[1]["naam"] == "Ministerie Test"
        assert records[1]["geldig_tot"] is not None

    async def test_rename_searchable_by_old_name(self, client, sample_eenheid):
        """After rename, search still finds unit by old name."""
        eid = sample_eenheid["id"]
        await client.put(
            f"/api/organisatie/{eid}",
            json={"naam": "Ministerie Nieuw"},
        )
        resp = await client.get(
            "/api/organisatie/search",
            params={"q": "Ministerie Test"},
        )
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["id"] == eid
        # Current name is the new one
        assert results[0]["naam"] == "Ministerie Nieuw"


# ---------------------------------------------------------------------------
# Update — reparent
# ---------------------------------------------------------------------------


class TestReparent:
    async def test_reparent_closes_old_parent(
        self,
        client,
        sample_eenheid,
        child_eenheid,
    ):
        """Reparenting closes the old parent record."""
        # Create new parent
        new_parent = await client.post(
            "/api/organisatie",
            json={"naam": "DG Twee", "type": "directoraat_generaal"},
        )
        new_pid = new_parent.json()["id"]

        eid = child_eenheid["id"]
        await client.put(
            f"/api/organisatie/{eid}",
            json={"parent_id": new_pid},
        )

        hist = await client.get(f"/api/organisatie/{eid}/history/parents")
        records = hist.json()
        assert len(records) == 2
        assert records[0]["parent_id"] == new_pid
        assert records[0]["geldig_tot"] is None
        assert records[1]["parent_id"] == sample_eenheid["id"]
        assert records[1]["geldig_tot"] is not None


# ---------------------------------------------------------------------------
# Update — manager change
# ---------------------------------------------------------------------------


class TestManagerChange:
    async def test_assign_manager(
        self,
        client,
        sample_eenheid,
        manager_person,
    ):
        """Assigning a manager creates a temporal manager record."""
        eid = sample_eenheid["id"]
        resp = await client.put(
            f"/api/organisatie/{eid}",
            json={"manager_id": str(manager_person.id)},
        )
        assert resp.status_code == 200
        assert resp.json()["manager_id"] == str(manager_person.id)

        hist = await client.get(f"/api/organisatie/{eid}/history/managers")
        records = hist.json()
        assert len(records) == 1
        assert records[0]["manager_id"] == str(manager_person.id)

    async def test_change_manager(
        self,
        client,
        manager_person,
        second_person,
    ):
        """Changing manager closes old record, opens new."""
        # Create eenheid with first manager
        create_resp = await client.post(
            "/api/organisatie",
            json={
                "naam": "Directie X",
                "type": "directie",
                "manager_id": str(manager_person.id),
            },
        )
        eid = create_resp.json()["id"]

        # Change to second manager
        await client.put(
            f"/api/organisatie/{eid}",
            json={"manager_id": str(second_person.id)},
        )

        hist = await client.get(f"/api/organisatie/{eid}/history/managers")
        records = hist.json()
        assert len(records) == 2
        assert records[0]["manager_id"] == str(second_person.id)
        assert records[0]["geldig_tot"] is None
        assert records[1]["manager_id"] == str(manager_person.id)
        assert records[1]["geldig_tot"] is not None

    async def test_managed_by_endpoint(
        self,
        client,
        sample_eenheid,
        manager_person,
    ):
        """GET /managed-by/{person_id} uses temporal manager table."""
        eid = sample_eenheid["id"]
        await client.put(
            f"/api/organisatie/{eid}",
            json={"manager_id": str(manager_person.id)},
        )

        resp = await client.get(
            f"/api/organisatie/managed-by/{manager_person.id}",
        )
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["id"] == eid


# ---------------------------------------------------------------------------
# Dissolution
# ---------------------------------------------------------------------------


class TestDissolution:
    async def test_dissolve_sets_geldig_tot(self, client, sample_eenheid):
        """Setting geldig_tot dissolves the unit."""
        eid = sample_eenheid["id"]
        resp = await client.put(
            f"/api/organisatie/{eid}",
            json={"geldig_tot": "2025-11-01"},
        )
        assert resp.status_code == 200
        assert resp.json()["geldig_tot"] == "2025-11-01"

    async def test_dissolved_excluded_from_list(self, client, sample_eenheid):
        """Dissolved units don't appear in GET /organisatie."""
        eid = sample_eenheid["id"]
        await client.put(
            f"/api/organisatie/{eid}",
            json={"geldig_tot": "2025-11-01"},
        )

        resp = await client.get("/api/organisatie")
        ids = [e["id"] for e in resp.json()]
        assert eid not in ids

    async def test_dissolved_excluded_from_tree(self, client, sample_eenheid):
        """Dissolved units don't appear in tree format."""
        eid = sample_eenheid["id"]
        await client.put(
            f"/api/organisatie/{eid}",
            json={"geldig_tot": "2025-11-01"},
        )

        resp = await client.get("/api/organisatie", params={"format": "tree"})
        assert resp.status_code == 200

        def find_id(nodes, target):
            for n in nodes:
                if n["id"] == target:
                    return True
                if find_id(n.get("children", []), target):
                    return True
            return False

        assert not find_id(resp.json(), eid)

    async def test_dissolve_closes_temporal_records(
        self,
        client,
        manager_person,
    ):
        """Dissolution closes all active temporal records."""
        # Create with parent and manager
        parent_resp = await client.post(
            "/api/organisatie",
            json={"naam": "Parent", "type": "ministerie"},
        )
        pid = parent_resp.json()["id"]

        child_resp = await client.post(
            "/api/organisatie",
            json={
                "naam": "Child",
                "type": "directie",
                "parent_id": pid,
                "manager_id": str(manager_person.id),
            },
        )
        cid = child_resp.json()["id"]

        # Dissolve
        await client.put(
            f"/api/organisatie/{cid}",
            json={"geldig_tot": "2025-11-01"},
        )

        # All temporal records should be closed
        for kind in ("namen", "parents", "managers"):
            hist = await client.get(f"/api/organisatie/{cid}/history/{kind}")
            for record in hist.json():
                assert record["geldig_tot"] is not None


# ---------------------------------------------------------------------------
# Search across all names
# ---------------------------------------------------------------------------


class TestSearch:
    async def test_search_current_name(self, client, sample_eenheid):
        """Search finds by current name."""
        resp = await client.get(
            "/api/organisatie/search",
            params={"q": "Ministerie Test"},
        )
        assert len(resp.json()) == 1

    async def test_search_historical_name(self, client, sample_eenheid):
        """Search finds by old name after rename."""
        eid = sample_eenheid["id"]
        await client.put(
            f"/api/organisatie/{eid}",
            json={"naam": "Completely New Name"},
        )
        resp = await client.get(
            "/api/organisatie/search",
            params={"q": "Ministerie Test"},
        )
        assert len(resp.json()) == 1
        assert resp.json()[0]["naam"] == "Completely New Name"

    async def test_search_empty_returns_empty(self, client):
        """Search with empty query returns empty list."""
        resp = await client.get(
            "/api/organisatie/search",
            params={"q": ""},
        )
        assert resp.json() == []

    async def test_search_excludes_dissolved(self, client, sample_eenheid):
        """Search excludes dissolved units."""
        eid = sample_eenheid["id"]
        await client.put(
            f"/api/organisatie/{eid}",
            json={"geldig_tot": "2025-11-01"},
        )
        resp = await client.get(
            "/api/organisatie/search",
            params={"q": "Ministerie Test"},
        )
        assert len(resp.json()) == 0


# ---------------------------------------------------------------------------
# Tree structure
# ---------------------------------------------------------------------------


class TestTree:
    async def test_tree_shows_parent_child(
        self,
        client,
        sample_eenheid,
        child_eenheid,
    ):
        """Tree nests child under parent."""
        resp = await client.get("/api/organisatie", params={"format": "tree"})
        tree = resp.json()

        root = next(n for n in tree if n["id"] == sample_eenheid["id"])
        child_ids = [c["id"] for c in root["children"]]
        assert child_eenheid["id"] in child_ids

    async def test_tree_reflects_reparent(
        self,
        client,
        sample_eenheid,
        child_eenheid,
    ):
        """After reparent, tree reflects new structure."""
        new_parent = await client.post(
            "/api/organisatie",
            json={"naam": "DG Nieuw", "type": "directoraat_generaal"},
        )
        new_pid = new_parent.json()["id"]

        await client.put(
            f"/api/organisatie/{child_eenheid['id']}",
            json={"parent_id": new_pid},
        )

        resp = await client.get("/api/organisatie", params={"format": "tree"})
        tree = resp.json()

        # Child should be under new parent, not old
        old_root = next(n for n in tree if n["id"] == sample_eenheid["id"])
        assert child_eenheid["id"] not in [c["id"] for c in old_root["children"]]

        new_root = next(n for n in tree if n["id"] == new_pid)
        assert child_eenheid["id"] in [c["id"] for c in new_root["children"]]


# ---------------------------------------------------------------------------
# Update — remove parent / remove manager (set to null)
# ---------------------------------------------------------------------------


class TestRemoveRelation:
    async def test_remove_parent(self, client, child_eenheid):
        """Setting parent_id to null closes the parent record."""
        eid = child_eenheid["id"]
        resp = await client.put(
            f"/api/organisatie/{eid}",
            json={"parent_id": None},
        )
        assert resp.status_code == 200
        assert resp.json()["parent_id"] is None

        hist = await client.get(f"/api/organisatie/{eid}/history/parents")
        records = hist.json()
        assert len(records) == 1
        assert records[0]["geldig_tot"] is not None

    async def test_remove_manager(self, client, manager_person):
        """Setting manager_id to null closes the manager record."""
        create_resp = await client.post(
            "/api/organisatie",
            json={
                "naam": "Eenheid M",
                "type": "afdeling",
                "manager_id": str(manager_person.id),
            },
        )
        eid = create_resp.json()["id"]

        resp = await client.put(
            f"/api/organisatie/{eid}",
            json={"manager_id": None},
        )
        assert resp.status_code == 200
        assert resp.json()["manager_id"] is None

        hist = await client.get(f"/api/organisatie/{eid}/history/managers")
        records = hist.json()
        assert len(records) == 1
        assert records[0]["geldig_tot"] is not None


# ---------------------------------------------------------------------------
# Update — wijzig_datum override
# ---------------------------------------------------------------------------


class TestWijzigDatum:
    async def test_wijzig_datum_override(self, client, sample_eenheid):
        """Custom wijzig_datum overrides the effective date for temporal records."""
        eid = sample_eenheid["id"]
        resp = await client.put(
            f"/api/organisatie/{eid}",
            json={"naam": "Naam Achteraf", "wijzig_datum": "2025-06-01"},
        )
        assert resp.status_code == 200

        hist = await client.get(f"/api/organisatie/{eid}/history/namen")
        records = hist.json()
        assert len(records) == 2
        # New record should use the custom date
        new_record = next(r for r in records if r["naam"] == "Naam Achteraf")
        assert new_record["geldig_van"] == "2025-06-01"
        # Old record should be closed at the custom date
        old_record = next(r for r in records if r["naam"] == "Ministerie Test")
        assert old_record["geldig_tot"] == "2025-06-01"


# ---------------------------------------------------------------------------
# Idempotent updates
# ---------------------------------------------------------------------------


class TestIdempotent:
    async def test_same_name_no_new_record(self, client, sample_eenheid):
        """Updating with the same name does not create a new temporal record."""
        eid = sample_eenheid["id"]
        await client.put(
            f"/api/organisatie/{eid}",
            json={"naam": "Ministerie Test"},
        )

        hist = await client.get(f"/api/organisatie/{eid}/history/namen")
        records = hist.json()
        assert len(records) == 1

    async def test_same_manager_no_new_record(
        self,
        client,
        manager_person,
    ):
        """Updating with the same manager does not create a new temporal record."""
        create_resp = await client.post(
            "/api/organisatie",
            json={
                "naam": "Eenheid I",
                "type": "afdeling",
                "manager_id": str(manager_person.id),
            },
        )
        eid = create_resp.json()["id"]

        await client.put(
            f"/api/organisatie/{eid}",
            json={"manager_id": str(manager_person.id)},
        )

        hist = await client.get(f"/api/organisatie/{eid}/history/managers")
        records = hist.json()
        assert len(records) == 1


# ---------------------------------------------------------------------------
# History endpoints — 404
# ---------------------------------------------------------------------------


class TestHistory404:
    async def test_naam_history_404(self, client):
        resp = await client.get(
            f"/api/organisatie/{uuid.uuid4()}/history/namen",
        )
        assert resp.status_code == 404

    async def test_parent_history_404(self, client):
        resp = await client.get(
            f"/api/organisatie/{uuid.uuid4()}/history/parents",
        )
        assert resp.status_code == 404

    async def test_manager_history_404(self, client):
        resp = await client.get(
            f"/api/organisatie/{uuid.uuid4()}/history/managers",
        )
        assert resp.status_code == 404
