"""Tests for LeadUpdatePost CRUD, publish flow, and .eml download."""

import uuid

import pytest

from bouwmeester.models.lead import Lead


@pytest.fixture
async def sample_lead(db_session):
    lead = Lead(id=uuid.uuid4(), title="Test lead", stage="inbox")
    db_session.add(lead)
    await db_session.flush()
    return lead


async def test_create_draft_update(client, sample_lead):
    resp = await client.post(
        f"/api/leads/{sample_lead.id}/updates",
        json={
            "titel": "Eerste",
            "body_internal": "Lange interne tekst",
            "body_public": "Korte publieke versie",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["titel"] == "Eerste"
    assert body["body_public"] == "Korte publieke versie"
    assert body["published_at"] is None


async def test_create_and_publish(client, sample_lead):
    resp = await client.post(
        f"/api/leads/{sample_lead.id}/updates",
        json={"titel": "Direct publiek", "publish": True},
    )
    assert resp.status_code == 201
    assert resp.json()["published_at"] is not None


async def test_edit_update(client, sample_lead):
    create = await client.post(
        f"/api/leads/{sample_lead.id}/updates",
        json={"titel": "Origineel"},
    )
    post_id = create.json()["id"]
    edit = await client.put(
        f"/api/leads/{sample_lead.id}/updates/{post_id}",
        json={"titel": "Bijgewerkt", "body_internal": "Nieuw"},
    )
    assert edit.status_code == 200
    assert edit.json()["titel"] == "Bijgewerkt"
    assert edit.json()["body_internal"] == "Nieuw"


async def test_publish_then_unpublish_keeps_published_by(client, sample_lead):
    create = await client.post(
        f"/api/leads/{sample_lead.id}/updates",
        json={"titel": "Audit", "publish": True},
    )
    post_id = create.json()["id"]
    publisher_id = create.json()["published_by_id"]
    unpub = await client.post(
        f"/api/leads/{sample_lead.id}/updates/{post_id}/unpublish"
    )
    assert unpub.status_code == 200
    assert unpub.json()["published_at"] is None
    assert unpub.json()["published_by_id"] == publisher_id


async def test_delete_update(client, sample_lead):
    create = await client.post(
        f"/api/leads/{sample_lead.id}/updates",
        json={"titel": "Weg ermee"},
    )
    post_id = create.json()["id"]
    delete = await client.delete(f"/api/leads/{sample_lead.id}/updates/{post_id}")
    assert delete.status_code == 204

    listing = await client.get(f"/api/leads/{sample_lead.id}/updates")
    assert listing.status_code == 200
    assert all(p["id"] != post_id for p in listing.json())


async def test_eml_download_outlook_headers(client, sample_lead):
    create = await client.post(
        f"/api/leads/{sample_lead.id}/updates",
        json={
            "titel": "Mail-test",
            "body_internal": "Beste team,\n\nEen update.",
            "mail_subject": "Subject van mail",
            "mail_to": ["a@example.org", "b@example.org"],
            "mail_cc": ["c@example.org"],
        },
    )
    post_id = create.json()["id"]
    eml = await client.get(f"/api/leads/{sample_lead.id}/updates/{post_id}/eml")
    assert eml.status_code == 200
    body = eml.text
    assert "X-Unsent: 1" in body
    assert "Subject: Subject van mail" in body
    assert "a@example.org" in body
    assert "b@example.org" in body
    assert "Cc: c@example.org" in body
    assert eml.headers["content-type"].startswith("message/rfc822")
    assert "attachment" in eml.headers["content-disposition"].lower()


async def test_parse_requires_input(client, sample_lead):
    """Without raw_text, files, or use_lead_history we must 400."""
    resp = await client.post(
        f"/api/leads/{sample_lead.id}/updates/parse",
        data={},
    )
    assert resp.status_code == 400


async def test_unknown_lead_returns_404(client):
    resp = await client.get(f"/api/leads/{uuid.uuid4()}/updates")
    assert resp.status_code == 404
