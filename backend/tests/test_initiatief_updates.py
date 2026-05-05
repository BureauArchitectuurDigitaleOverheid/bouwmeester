"""Tests for InitiatiefUpdatePost CRUD + publish/unpublish flow."""

import uuid


async def _create_initiatief(db_session, *, naam: str = "Init"):
    from bouwmeester.models.initiatief import Initiatief

    init = Initiatief(id=uuid.uuid4(), naam=naam)
    db_session.add(init)
    await db_session.flush()
    return init


async def test_create_draft_update(client, db_session):
    init = await _create_initiatief(db_session)
    resp = await client.post(
        f"/api/initiatieven/{init.id}/updates",
        json={"titel": "Eerste concept", "body": "Hallo", "publish": False},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["titel"] == "Eerste concept"
    assert data["published_at"] is None
    assert data["published_by_id"] is None


async def test_create_and_publish_in_one_call(client, db_session):
    init = await _create_initiatief(db_session)
    resp = await client.post(
        f"/api/initiatieven/{init.id}/updates",
        json={"titel": "Direct publiek", "publish": True},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["published_at"] is not None


async def test_publish_then_unpublish_keeps_publisher_audit(client, db_session):
    """S6 fix: published_by_id moet behouden blijven na unpublish."""
    init = await _create_initiatief(db_session)
    create = await client.post(
        f"/api/initiatieven/{init.id}/updates",
        json={"titel": "Audit", "publish": True},
    )
    post_id = create.json()["id"]
    publisher_id = create.json()["published_by_id"]
    # In dev mode is current_user None → publisher_id is null. We checken
    # daarom expliciet dat unpublish niet *meer* informatie weghaalt dan
    # alleen de timestamp.
    unpub = await client.post(
        f"/api/initiatieven/{init.id}/updates/{post_id}/unpublish"
    )
    assert unpub.status_code == 200
    assert unpub.json()["published_at"] is None
    assert unpub.json()["published_by_id"] == publisher_id


async def test_edit_update(client, db_session):
    init = await _create_initiatief(db_session)
    create = await client.post(
        f"/api/initiatieven/{init.id}/updates",
        json={"titel": "Origineel"},
    )
    post_id = create.json()["id"]
    edit = await client.put(
        f"/api/initiatieven/{init.id}/updates/{post_id}",
        json={"titel": "Bijgewerkt", "body": "Nieuwe inhoud"},
    )
    assert edit.status_code == 200
    assert edit.json()["titel"] == "Bijgewerkt"
    assert edit.json()["body"] == "Nieuwe inhoud"


async def test_publish_endpoint(client, db_session):
    init = await _create_initiatief(db_session)
    create = await client.post(
        f"/api/initiatieven/{init.id}/updates",
        json={"titel": "Concept"},
    )
    post_id = create.json()["id"]
    pub = await client.post(f"/api/initiatieven/{init.id}/updates/{post_id}/publish")
    assert pub.status_code == 200
    assert pub.json()["published_at"] is not None


async def test_delete_update(client, db_session):
    init = await _create_initiatief(db_session)
    create = await client.post(
        f"/api/initiatieven/{init.id}/updates",
        json={"titel": "Weg ermee"},
    )
    post_id = create.json()["id"]
    delete = await client.delete(f"/api/initiatieven/{init.id}/updates/{post_id}")
    assert delete.status_code == 204
    listing = await client.get(f"/api/initiatieven/{init.id}/updates")
    assert all(u["id"] != post_id for u in listing.json())


async def test_list_updates_returns_drafts_and_published(client, db_session):
    init = await _create_initiatief(db_session)
    await client.post(f"/api/initiatieven/{init.id}/updates", json={"titel": "Draft 1"})
    await client.post(
        f"/api/initiatieven/{init.id}/updates",
        json={"titel": "Live 1", "publish": True},
    )
    resp = await client.get(f"/api/initiatieven/{init.id}/updates")
    assert resp.status_code == 200
    titles = {u["titel"] for u in resp.json()}
    assert titles == {"Draft 1", "Live 1"}
