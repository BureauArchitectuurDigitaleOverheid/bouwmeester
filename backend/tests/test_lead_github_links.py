"""Tests voor de lead-GitHub-links endpoints."""

import uuid

import pytest
from sqlalchemy import select

from bouwmeester.models.github_link import SCOPE_LEAD, GitHubLink
from bouwmeester.models.lead import Lead


@pytest.fixture
async def sample_lead(db_session):
    lead = Lead(
        id=uuid.uuid4(),
        title="GitHub-link lead",
        stage="interne_check",
    )
    db_session.add(lead)
    await db_session.flush()
    return lead


async def test_create_branch_link_201(client, sample_lead):
    resp = await client.post(
        f"/api/leads/{sample_lead.id}/github-links",
        json={
            "url": "https://github.com/foo/bar/tree/feat/x",
            "title": "Werk-branch",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["link_type"] == "branch"
    assert body["owner"] == "foo"
    assert body["repo"] == "bar"
    assert body["ref"] == "feat/x"
    assert body["title"] == "Werk-branch"


async def test_create_pull_request_link_201(client, sample_lead):
    resp = await client.post(
        f"/api/leads/{sample_lead.id}/github-links",
        json={"url": "https://github.com/foo/bar/pull/12"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["link_type"] == "pull_request"
    assert body["ref"] == "12"


async def test_create_invalid_url_422(client, sample_lead):
    resp = await client.post(
        f"/api/leads/{sample_lead.id}/github-links",
        json={"url": "https://gitlab.com/foo/bar"},
    )
    assert resp.status_code == 422


async def test_create_duplicate_url_409(client, sample_lead):
    url = "https://github.com/foo/bar/pull/1"
    first = await client.post(
        f"/api/leads/{sample_lead.id}/github-links",
        json={"url": url},
    )
    assert first.status_code == 201
    second = await client.post(
        f"/api/leads/{sample_lead.id}/github-links",
        json={"url": url},
    )
    assert second.status_code == 409


async def test_list_returns_all_created_links(client, sample_lead):
    urls = {
        "https://github.com/foo/bar/issues/1",
        "https://github.com/foo/bar/pull/2",
    }
    for url in urls:
        resp = await client.post(
            f"/api/leads/{sample_lead.id}/github-links",
            json={"url": url},
        )
        assert resp.status_code == 201

    list_resp = await client.get(f"/api/leads/{sample_lead.id}/github-links")
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert {item["url"] for item in body} == urls


async def test_lead_detail_includes_github_links(client, sample_lead):
    await client.post(
        f"/api/leads/{sample_lead.id}/github-links",
        json={"url": "https://github.com/foo/bar"},
    )
    detail = await client.get(f"/api/leads/{sample_lead.id}")
    assert detail.status_code == 200
    body = detail.json()
    assert len(body["github_links"]) == 1
    assert body["github_links"][0]["link_type"] == "repo"


async def test_patch_updates_only_title(client, sample_lead):
    create = await client.post(
        f"/api/leads/{sample_lead.id}/github-links",
        json={"url": "https://github.com/foo/bar/pull/9", "title": "Oud"},
    )
    link_id = create.json()["id"]

    resp = await client.patch(
        f"/api/leads/{sample_lead.id}/github-links/{link_id}",
        json={"title": "Nieuw"},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Nieuw"


async def test_delete_returns_204_and_removes(client, db_session, sample_lead):
    create = await client.post(
        f"/api/leads/{sample_lead.id}/github-links",
        json={"url": "https://github.com/foo/bar/pull/3"},
    )
    link_id = create.json()["id"]

    resp = await client.delete(f"/api/leads/{sample_lead.id}/github-links/{link_id}")
    assert resp.status_code == 204

    remaining = (
        (
            await db_session.execute(
                select(GitHubLink).where(GitHubLink.id == uuid.UUID(link_id))
            )
        )
        .scalars()
        .all()
    )
    assert remaining == []


async def test_delete_lead_cascades_github_links(client, db_session, sample_lead):
    await client.post(
        f"/api/leads/{sample_lead.id}/github-links",
        json={"url": "https://github.com/foo/bar/pull/4"},
    )

    resp = await client.delete(f"/api/leads/{sample_lead.id}")
    assert resp.status_code == 204

    remaining = (
        (
            await db_session.execute(
                select(GitHubLink).where(
                    GitHubLink.scope_type == SCOPE_LEAD,
                    GitHubLink.scope_id == sample_lead.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert remaining == []


async def test_link_for_other_lead_returns_404(client, db_session, sample_lead):
    # Maak een link op sample_lead
    create = await client.post(
        f"/api/leads/{sample_lead.id}/github-links",
        json={"url": "https://github.com/foo/bar/pull/7"},
    )
    link_id = create.json()["id"]

    # Maak een tweede lead, probeer de link via die lead te benaderen
    other = Lead(id=uuid.uuid4(), title="Andere lead", stage="inbox")
    db_session.add(other)
    await db_session.flush()

    resp = await client.delete(f"/api/leads/{other.id}/github-links/{link_id}")
    assert resp.status_code == 404

    patch = await client.patch(
        f"/api/leads/{other.id}/github-links/{link_id}",
        json={"title": "x"},
    )
    assert patch.status_code == 404
