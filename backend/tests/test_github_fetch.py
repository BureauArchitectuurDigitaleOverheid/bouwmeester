"""Tests voor de GitHub-status-fetcher.

Gebruikt ``httpx.MockTransport`` zodat we geen netwerk- of mock-libs
nodig hebben. De ``GitHubClient`` accepteert een ``transport``-parameter
specifiek voor dit doel.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from bouwmeester.core.github_client import GitHubClient
from bouwmeester.models.github_link import SCOPE_LEAD, GitHubLink
from bouwmeester.services.github_fetch import refresh_link_status


def _make_link(**kwargs) -> GitHubLink:
    defaults = dict(
        id=uuid.uuid4(),
        scope_type=SCOPE_LEAD,
        scope_id=uuid.uuid4(),
        url="https://github.com/foo/bar/pull/1",
        link_type="pull_request",
        owner="foo",
        repo="bar",
        ref="1",
        title=None,
        state=None,
        state_extra=None,
        etag=None,
        last_checked_at=None,
        last_changed_at=None,
        check_error=None,
    )
    defaults.update(kwargs)
    return GitHubLink(**defaults)


def _transport(handler):
    return httpx.MockTransport(handler)


async def _client_with(handler) -> GitHubClient:
    client = GitHubClient(token="testpat", transport=_transport(handler))
    await client.__aenter__()
    return client


@pytest.mark.asyncio
async def test_open_pr_sets_open_state():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/foo/bar/pulls/1"
        assert request.headers["Authorization"] == "Bearer testpat"
        return httpx.Response(
            200,
            headers={"ETag": '"abc"'},
            json={
                "state": "open",
                "merged": False,
                "draft": False,
                "title": "Add thing",
                "head": {"ref": "feat/thing"},
                "base": {"ref": "main"},
                "html_url": "https://github.com/foo/bar/pull/1",
            },
        )

    client = await _client_with(handler)
    try:
        link = _make_link()
        changed = await refresh_link_status(link, client=client)
        assert changed is True
        assert link.state == "open"
        assert link.etag == '"abc"'
        assert link.check_error is None
        assert link.last_checked_at is not None
        assert link.last_changed_at is not None
        assert link.state_extra["title"] == "Add thing"
        assert link.state_extra["head_ref"] == "feat/thing"
    finally:
        await client.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_merged_pr_state():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "state": "closed",
                "merged": True,
                "merged_at": "2026-01-01T00:00:00Z",
                "draft": False,
            },
        )

    client = await _client_with(handler)
    try:
        link = _make_link()
        await refresh_link_status(link, client=client)
        assert link.state == "merged"
        assert link.state_extra.get("merged_at") == "2026-01-01T00:00:00Z"
    finally:
        await client.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_draft_pr_state():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"state": "open", "merged": False, "draft": True},
        )

    client = await _client_with(handler)
    try:
        link = _make_link()
        await refresh_link_status(link, client=client)
        assert link.state == "draft"
    finally:
        await client.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_304_not_modified_keeps_state_clears_error():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["If-None-Match"] == '"abc"'
        return httpx.Response(304)

    client = await _client_with(handler)
    try:
        link = _make_link(
            state="open",
            etag='"abc"',
            check_error="oude fout",
            last_checked_at=datetime.now(UTC) - timedelta(hours=1),
        )
        old_changed = link.last_changed_at
        changed = await refresh_link_status(link, client=client)
        assert changed is False
        assert link.state == "open"
        assert link.etag == '"abc"'
        assert link.check_error is None
        assert link.last_changed_at == old_changed
    finally:
        await client.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_404_sets_not_found_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = await _client_with(handler)
    try:
        link = _make_link(state="open")
        changed = await refresh_link_status(link, client=client)
        assert changed is False
        assert link.check_error == "not_found"
        # State blijft staan; UI ziet check_error.
        assert link.state == "open"
    finally:
        await client.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_403_sets_no_access_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    client = await _client_with(handler)
    try:
        link = _make_link()
        await refresh_link_status(link, client=client)
        assert link.check_error == "no_access"
    finally:
        await client.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_500_sets_http_500_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = await _client_with(handler)
    try:
        link = _make_link()
        await refresh_link_status(link, client=client)
        assert link.check_error == "http_500"
    finally:
        await client.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_no_token_returns_false_without_raising():
    """Zonder GITHUB_TOKEN moet de fetch stilletjes overgeslagen worden."""
    link = _make_link()
    # Geen client meegeven → factory probeert env-token; we forceren leeg.
    client = GitHubClient(token="")
    # Niet __aenter__'en; refresh_link_status doet dat zelf en moet
    # GitHubAuthNotConfiguredError opvangen.
    changed = await refresh_link_status(link, client=None)
    assert changed is False
    assert link.state is None
    assert link.check_error is None
    # Sanity: client.is_configured = False.
    assert client.is_configured is False


@pytest.mark.asyncio
async def test_state_change_sets_last_changed_at():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"state": "closed", "merged": True, "draft": False},
        )

    client = await _client_with(handler)
    try:
        before = datetime.now(UTC) - timedelta(days=1)
        link = _make_link(
            state="open",
            last_changed_at=before,
        )
        changed = await refresh_link_status(link, client=client)
        assert changed is True
        assert link.state == "merged"
        assert link.last_changed_at is not None
        assert link.last_changed_at > before
    finally:
        await client.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_unchanged_state_keeps_last_changed_at():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"state": "open", "merged": False, "draft": False},
        )

    client = await _client_with(handler)
    try:
        before = datetime.now(UTC) - timedelta(hours=2)
        link = _make_link(state="open", last_changed_at=before)
        changed = await refresh_link_status(link, client=client)
        assert changed is False
        assert link.last_changed_at == before
    finally:
        await client.__aexit__(None, None, None)
