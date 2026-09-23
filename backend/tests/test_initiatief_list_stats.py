"""The overview counts on GET /api/initiatieven."""

import uuid
from datetime import UTC, datetime, timedelta


async def _initiatief_with_columns(db_session, naam: str):
    from bouwmeester.models.initiatief import Initiatief
    from bouwmeester.repositories.lead_column import LeadColumnRepository

    init = Initiatief(id=uuid.uuid4(), naam=naam)
    db_session.add(init)
    await db_session.flush()
    await LeadColumnRepository(db_session).seed_defaults(init.id)
    return init


def _by_naam(resp, naam: str) -> dict:
    return next(i for i in resp.json() if i["naam"] == naam)


async def test_counts_leads_members_and_last_update(client, db_session, sample_person):
    from bouwmeester.models.initiatief_update import InitiatiefUpdatePost
    from bouwmeester.models.lead import Lead
    from bouwmeester.models.resource_permission import ResourcePermission

    init = await _initiatief_with_columns(db_session, "Druk")
    # `verkennen` is an active stage by default, `koelkast` is not.
    db_session.add_all(
        [
            Lead(title="A", stage="verkennen", initiatief_id=init.id),
            Lead(title="B", stage="verkennen", initiatief_id=init.id),
            Lead(title="C", stage="koelkast", initiatief_id=init.id),
            # A lead without initiatief counts nowhere.
            Lead(title="Wees", stage="verkennen"),
        ]
    )
    db_session.add(
        ResourcePermission(
            person_id=sample_person.id,
            resource_type="initiatief",
            resource_id=init.id,
            rol="eigenaar",
        )
    )
    earlier = datetime.now(UTC) - timedelta(days=3)
    later = datetime.now(UTC) - timedelta(days=1)
    db_session.add_all(
        [
            InitiatiefUpdatePost(
                initiatief_id=init.id, titel="Oud", published_at=earlier
            ),
            InitiatiefUpdatePost(
                initiatief_id=init.id, titel="Nieuw", published_at=later
            ),
            InitiatiefUpdatePost(initiatief_id=init.id, titel="Concept"),
        ]
    )
    await db_session.flush()

    resp = await client.get("/api/initiatieven")
    assert resp.status_code == 200, resp.text
    item = _by_naam(resp, "Druk")
    assert item["lead_count"] == 3
    assert item["active_lead_count"] == 2
    assert item["member_count"] == 1
    assert datetime.fromisoformat(item["last_published_at"]) == later


async def test_empty_initiatief_reports_zeroes(client, db_session):
    await _initiatief_with_columns(db_session, "Stil")

    resp = await client.get("/api/initiatieven")
    item = _by_naam(resp, "Stil")
    assert item["lead_count"] == 0
    assert item["active_lead_count"] == 0
    assert item["member_count"] == 0
    assert item["last_published_at"] is None


async def test_lead_metrics_scope_to_one_initiatief(client, db_session):
    """The funnel counts above an initiatief's board count its own leads."""
    from bouwmeester.models.lead import Lead

    mine = await _initiatief_with_columns(db_session, "Mijn")
    other = await _initiatief_with_columns(db_session, "Ander")
    db_session.add_all(
        [
            Lead(title="A", stage="verkennen", initiatief_id=mine.id),
            Lead(title="B", stage="koelkast", initiatief_id=mine.id),
            Lead(title="C", stage="verkennen", initiatief_id=other.id),
        ]
    )
    await db_session.flush()

    scoped = await client.get(f"/api/leads/metrics?initiatief_id={mine.id}")
    assert scoped.status_code == 200, scoped.text
    assert scoped.json()["total"] == 2
    assert scoped.json()["by_stage"] == {"verkennen": 1, "koelkast": 1}

    everything = await client.get("/api/leads/metrics")
    assert everything.json()["total"] >= 3
