"""Tests for per-initiatief funnel-kolommen (lead_column)."""

import uuid

from bouwmeester.repositories.lead_column import LeadColumnRepository


async def _create_initiatief_with_defaults(db_session, *, naam: str = "Init"):
    """Insert an initiatief and seed the 7 default columns.

    Bypasses InitiatiefRepository.create (which would also try to write
    a ResourcePermission for created_by_id) by adding the model directly
    and seeding columns through the repo.
    """
    from bouwmeester.models.initiatief import Initiatief

    init = Initiatief(id=uuid.uuid4(), naam=naam)
    db_session.add(init)
    await db_session.flush()
    await LeadColumnRepository(db_session).seed_defaults(init.id)
    return init


async def test_seed_defaults_creates_seven_columns(client, db_session):
    init = await _create_initiatief_with_defaults(db_session)
    resp = await client.get(f"/api/initiatieven/{init.id}/columns")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data) == 7
    slugs = [c["slug"] for c in data]
    assert slugs == [
        "inbox",
        "verkennen",
        "eerste_gesprek",
        "interne_check",
        "follow_up",
        "in_the_pocket",
        "koelkast",
    ]
    by_slug = {c["slug"]: c for c in data}
    # is_active_stage flags should exclude the three "non-active" stages
    assert by_slug["inbox"]["is_active_stage"] is False
    assert by_slug["in_the_pocket"]["is_active_stage"] is False
    assert by_slug["koelkast"]["is_active_stage"] is False
    assert by_slug["verkennen"]["is_active_stage"] is True
    # is_public_visible flags should include the four publically-visible stages
    assert by_slug["eerste_gesprek"]["is_public_visible"] is True
    assert by_slug["in_the_pocket"]["is_public_visible"] is True
    assert by_slug["inbox"]["is_public_visible"] is False


async def test_create_column(client, db_session):
    init = await _create_initiatief_with_defaults(db_session)
    resp = await client.post(
        f"/api/initiatieven/{init.id}/columns",
        json={
            "name": "Strategisch",
            "color": "bg-red-100 text-red-800",
            "is_active_stage": True,
            "is_public_visible": False,
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "Strategisch"
    assert data["slug"] == "strategisch"
    assert data["sort_order"] == 7  # appended after the 7 defaults


async def test_create_column_duplicate_name_409(client, db_session):
    init = await _create_initiatief_with_defaults(db_session)
    resp = await client.post(
        f"/api/initiatieven/{init.id}/columns",
        json={"name": "Inbox", "color": "bg-red-100 text-red-800"},
    )
    assert resp.status_code == 409, resp.text


async def test_update_column_rename(client, db_session):
    init = await _create_initiatief_with_defaults(db_session)
    listing = await client.get(f"/api/initiatieven/{init.id}/columns")
    inbox = next(c for c in listing.json() if c["slug"] == "inbox")
    resp = await client.put(
        f"/api/initiatieven/{init.id}/columns/{inbox['id']}",
        json={"name": "Aanmeldingen"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["name"] == "Aanmeldingen"
    # Slug stays immutable so existing leads keep their FK reference
    assert data["slug"] == "inbox"


async def test_delete_empty_column(client, db_session):
    init = await _create_initiatief_with_defaults(db_session)
    listing = await client.get(f"/api/initiatieven/{init.id}/columns")
    koelkast = next(c for c in listing.json() if c["slug"] == "koelkast")
    resp = await client.delete(f"/api/initiatieven/{init.id}/columns/{koelkast['id']}")
    assert resp.status_code == 204
    after = await client.get(f"/api/initiatieven/{init.id}/columns")
    assert all(c["slug"] != "koelkast" for c in after.json())


async def test_delete_non_empty_requires_move_to(client, db_session):
    from bouwmeester.models.lead import Lead

    init = await _create_initiatief_with_defaults(db_session)
    db_session.add(Lead(title="X", stage="verkennen", initiatief_id=init.id))
    await db_session.flush()
    listing = await client.get(f"/api/initiatieven/{init.id}/columns")
    verkennen = next(c for c in listing.json() if c["slug"] == "verkennen")
    follow_up = next(c for c in listing.json() if c["slug"] == "follow_up")

    # Without move_to: 400
    resp = await client.delete(f"/api/initiatieven/{init.id}/columns/{verkennen['id']}")
    assert resp.status_code == 400
    assert "move_to" in resp.text.lower()

    # With move_to: 204 and lead now in target column
    resp = await client.delete(
        f"/api/initiatieven/{init.id}/columns/{verkennen['id']}"
        f"?move_to={follow_up['id']}"
    )
    assert resp.status_code == 204
    await db_session.flush()
    from sqlalchemy import select

    moved = (
        await db_session.execute(
            select(Lead.stage).where(Lead.initiatief_id == init.id)
        )
    ).scalar_one()
    assert moved == "follow_up"


async def test_delete_last_column_blocked(client, db_session):
    init = await _create_initiatief_with_defaults(db_session)
    listing = await client.get(f"/api/initiatieven/{init.id}/columns")
    # Delete six of the seven (all empty); the 7th deletion must fail.
    for col in listing.json()[:-1]:
        resp = await client.delete(f"/api/initiatieven/{init.id}/columns/{col['id']}")
        assert resp.status_code == 204, (col, resp.text)
    last = listing.json()[-1]
    resp = await client.delete(f"/api/initiatieven/{init.id}/columns/{last['id']}")
    assert resp.status_code == 400
    assert "tenminste 1 kolom" in resp.text.lower()


async def test_reorder_columns(client, db_session):
    init = await _create_initiatief_with_defaults(db_session)
    listing = await client.get(f"/api/initiatieven/{init.id}/columns")
    ids = [c["id"] for c in listing.json()]
    reversed_ids = list(reversed(ids))
    resp = await client.post(
        f"/api/initiatieven/{init.id}/columns/reorder",
        json={"column_ids": reversed_ids},
    )
    assert resp.status_code == 200, resp.text
    after = await client.get(f"/api/initiatieven/{init.id}/columns")
    after_ids = [c["id"] for c in after.json()]
    assert after_ids == reversed_ids


async def test_reorder_mismatch_400(client, db_session):
    init = await _create_initiatief_with_defaults(db_session)
    listing = await client.get(f"/api/initiatieven/{init.id}/columns")
    ids = [c["id"] for c in listing.json()][:-1]  # missing one
    resp = await client.post(
        f"/api/initiatieven/{init.id}/columns/reorder",
        json={"column_ids": ids},
    )
    assert resp.status_code == 400


async def test_create_lead_with_unknown_stage_422(client, db_session):
    init = await _create_initiatief_with_defaults(db_session)
    resp = await client.post(
        "/api/leads",
        json={
            "title": "Test",
            "stage": "niet-bestaand",
            "initiatief_id": str(init.id),
        },
    )
    assert resp.status_code == 422, resp.text
    assert "niet-bestaand" in resp.text


async def test_orphan_lead_accepts_default_slugs(client, db_session):
    """Lead zonder initiatief_id valt terug op de 7 default-slugs."""
    resp = await client.post(
        "/api/leads",
        json={"title": "Orphan", "stage": "verkennen"},
    )
    assert resp.status_code == 201, resp.text


async def test_orphan_lead_rejects_unknown_slug(client, db_session):
    resp = await client.post(
        "/api/leads",
        json={"title": "Orphan", "stage": "strategisch"},
    )
    assert resp.status_code == 422, resp.text


async def test_lead_count_returned_in_list(client, db_session):
    from bouwmeester.models.lead import Lead

    init = await _create_initiatief_with_defaults(db_session)
    db_session.add(Lead(title="A", stage="verkennen", initiatief_id=init.id))
    db_session.add(Lead(title="B", stage="verkennen", initiatief_id=init.id))
    await db_session.flush()
    resp = await client.get(f"/api/initiatieven/{init.id}/columns")
    by_slug = {c["slug"]: c for c in resp.json()}
    assert by_slug["verkennen"]["lead_count"] == 2
    assert by_slug["inbox"]["lead_count"] == 0
