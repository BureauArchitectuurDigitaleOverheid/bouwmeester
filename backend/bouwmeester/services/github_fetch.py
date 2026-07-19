"""Status-fetch voor github_link records.

Eén entry-point: ``refresh_link_status``. Het bepaalt op basis van
``link_type`` welke API-call nodig is, vraagt 'm met de eventueel
opgeslagen ``etag`` en updatet het record. Errors worden in
``check_error`` gezet, niet teruggegooid: een falende fetch mag de
lead-detail-render nooit blokkeren.

Voor v1 alleen ``pull_request``. Branch/issue/repo/run komen later in
deze module bij — pattern is identiek (eigen ``_fetch_*``-helper, eigen
``state``-bepaling).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from bouwmeester.core.github_client import (
    GitHubAuthNotConfiguredError,
    GitHubClient,
    GitHubResponse,
)
from bouwmeester.models.github_link import GitHubLink

logger = logging.getLogger(__name__)


async def refresh_link_status(
    link: GitHubLink,
    *,
    client: GitHubClient | None = None,
) -> bool:
    """Refresh ``link.state`` / ``state_extra`` / ``etag`` / timestamps.

    Returns ``True`` als de state daadwerkelijk veranderd is (handig voor
    fase 4: status-change → notification of trigger).

    Schrijft naar het ORM-object maar doet **geen** ``flush``/``commit``;
    de aanroeper bepaalt dat (typisch: gewoon de request-handler
    waardoor ``get_db`` het bij success commit).
    """
    own_client = client is None
    try:
        if own_client:
            client = GitHubClient()
            await client.__aenter__()
    except GitHubAuthNotConfiguredError:
        # Geen token → niet falen, gewoon stilletjes overslaan. Het UI
        # toont de link zonder status-icoon. Dit pad is normaal in dev
        # zonder PAT.
        return False

    assert client is not None
    try:
        if link.link_type == "pull_request":
            response = await _fetch_pr(client, link)
        else:
            # Andere types nog niet ondersteund — valt onder fase 2b.
            return False

        return _apply_response(link, response)
    except httpx.TimeoutException:
        link.check_error = "timeout"
        link.last_checked_at = datetime.now(UTC)
        return False
    except Exception as exc:  # noqa: BLE001 — best-effort
        logger.warning(
            "github status fetch faalde voor %s/%s ref=%s: %s",
            link.owner,
            link.repo,
            link.ref,
            exc,
        )
        link.check_error = f"{type(exc).__name__}: {exc}"[:500]
        link.last_checked_at = datetime.now(UTC)
        return False
    finally:
        if own_client:
            await client.__aexit__(None, None, None)


async def _fetch_pr(client: GitHubClient, link: GitHubLink) -> GitHubResponse:
    if not link.ref:
        return GitHubResponse(status=400, data=None, etag=None)
    path = f"/repos/{link.owner}/{link.repo}/pulls/{link.ref}"
    return await client.get(path, etag=link.etag)


def _apply_response(link: GitHubLink, response: GitHubResponse) -> bool:
    """Schrijf de response op het link-record. Return True als state wijzigde."""
    now = datetime.now(UTC)
    link.last_checked_at = now

    if response.status == 304:
        # Niets veranderd — etag blijft, state blijft, geen check_error.
        link.check_error = None
        return False

    if response.status == 404:
        link.check_error = "not_found"
        # We laten de oude state staan; UI kan zien dat last_checked_at
        # recent is en check_error gezet — dat impliceert "verdwenen".
        return False

    if response.status == 401 or response.status == 403:
        link.check_error = "no_access"
        return False

    if response.status >= 400:
        link.check_error = f"http_{response.status}"
        return False

    if response.data is None:
        link.check_error = "empty_response"
        return False

    new_state, extra = _pr_state_from_payload(response.data)
    state_changed = new_state != link.state

    link.state = new_state
    link.state_extra = extra
    link.etag = response.etag
    link.check_error = None
    if state_changed:
        link.last_changed_at = now
    return state_changed


def _pr_state_from_payload(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Map GitHub's PR-velden naar onze ``state``-string + extra."""
    if payload.get("merged"):
        state = "merged"
    elif payload.get("draft"):
        state = "draft"
    elif payload.get("state") == "closed":
        state = "closed"
    else:
        state = "open"

    extra: dict[str, Any] = {
        "title": payload.get("title"),
        "head_ref": (payload.get("head") or {}).get("ref"),
        "base_ref": (payload.get("base") or {}).get("ref"),
        "merged_at": payload.get("merged_at"),
        "html_url": payload.get("html_url"),
    }
    # Lege/None-waardes opruimen voor compactere JSONB.
    extra = {k: v for k, v in extra.items() if v is not None}
    return state, extra
