"""Tests for the unauthenticated public initiatief endpoint.

This is the only unauth route in the system; the 404-on-private logic is a
deliberate security decision (do not leak existence). Regressions here are
silent, so test thoroughly.
"""

import uuid
from datetime import UTC, datetime


async def _create_initiatief(
    db_session,
    *,
    naam: str,
    slug: str | None,
    public: bool = False,
):
    from bouwmeester.models.initiatief import Initiatief

    init = Initiatief(
        id=uuid.uuid4(),
        naam=naam,
        slug=slug,
        beschrijving=f"Beschrijving van {naam}",
        kleur="#3B82F6",
        public_page_enabled=public,
    )
    db_session.add(init)
    await db_session.flush()
    return init


async def _create_update(
    db_session,
    *,
    initiatief_id: uuid.UUID,
    titel: str,
    body: str | None = "Body",
    published: bool = False,
):
    from bouwmeester.models.initiatief_update import InitiatiefUpdatePost

    post = InitiatiefUpdatePost(
        id=uuid.uuid4(),
        initiatief_id=initiatief_id,
        titel=titel,
        body=body,
        published_at=datetime.now(UTC) if published else None,
    )
    db_session.add(post)
    await db_session.flush()
    return post


async def test_public_initiatief_404_for_unknown_slug(client):
    resp = await client.get("/api/public/initiatieven/by-slug/onbestaand")
    assert resp.status_code == 404


async def test_public_initiatief_404_when_disabled(client, db_session):
    await _create_initiatief(db_session, naam="Privé", slug="prive-test", public=False)
    resp = await client.get("/api/public/initiatieven/by-slug/prive-test")
    assert resp.status_code == 404, (
        "moet 404 geven, niet 403, om bestaan niet te lekken"
    )


async def test_public_initiatief_returns_only_safe_fields(client, db_session):
    init = await _create_initiatief(
        db_session, naam="Publiek RR", slug="publiek-rr", public=True
    )
    resp = await client.get("/api/public/initiatieven/by-slug/publiek-rr")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {
        "naam": "Publiek RR",
        "slug": "publiek-rr",
        "beschrijving": "Beschrijving van Publiek RR",
        "kleur": "#3B82F6",
        "updates": [],
    }
    # Geen interne velden in de response
    for forbidden in (
        "id",
        "funnel_enabled",
        "public_page_enabled",
        "score_strategisch_label",
        "score_politiek_label",
        "score_positie_label",
        "created_by_id",
        "created_at",
        "updated_at",
    ):
        assert forbidden not in data, f"{forbidden} mag niet in publieke response"
    # Geen lead-data
    assert "leads" not in data
    assert init.id  # silence lint


async def test_public_initiatief_only_published_updates(client, db_session):
    init = await _create_initiatief(db_session, naam="Mix", slug="mix", public=True)
    await _create_update(
        db_session,
        initiatief_id=init.id,
        titel="Concept (geheim)",
        body="<script>alert(1)</script>",
        published=False,
    )
    await _create_update(
        db_session,
        initiatief_id=init.id,
        titel="Gepubliceerd",
        body="Hallo wereld",
        published=True,
    )
    resp = await client.get("/api/public/initiatieven/by-slug/mix")
    assert resp.status_code == 200
    updates = resp.json()["updates"]
    assert len(updates) == 1
    assert updates[0]["titel"] == "Gepubliceerd"
    titles = {u["titel"] for u in updates}
    assert "Concept (geheim)" not in titles, "drafts mogen niet lekken"
    # Update-shape check: alleen veilige velden
    update = updates[0]
    for forbidden in ("id", "initiatief_id", "created_at", "updated_at"):
        assert forbidden not in update


async def test_public_initiatief_disable_flips_to_404(client, db_session):
    init = await _create_initiatief(
        db_session, naam="Toggle", slug="toggle", public=True
    )
    resp = await client.get("/api/public/initiatieven/by-slug/toggle")
    assert resp.status_code == 200
    init.public_page_enabled = False
    await db_session.flush()
    resp = await client.get("/api/public/initiatieven/by-slug/toggle")
    assert resp.status_code == 404
