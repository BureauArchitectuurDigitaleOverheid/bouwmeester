"""Dunne async-client voor de GitHub-API.

Auth-modus:

1. Als ``GITHUB_TOKEN`` (PAT) is gezet, wordt die gebruikt.
2. App-credentials (``GITHUB_APP_ID``, ``GITHUB_APP_PRIVATE_KEY``,
   ``GITHUB_APP_INSTALLATION_ID``) komen later — dan verschuift deze
   factory naar JWT + installation-token zonder dat callers wijzigen.

De client doet **geen** retries. Statusbepaling is een best-effort
operatie binnen een lead-detail-request; bij een 5xx of timeout zetten
we ``check_error`` en gaan we door. Polling/retry is werk voor fase 2b
of fase 4 (worker).

Conditional GETs gebruiken ``If-None-Match`` met de eerder opgeslagen
ETag. 304-responses kosten geen rate-budget en komen hier terug als
``GitHubResponse(status=304, etag=<oude etag>, data=None)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from bouwmeester.core.config import get_settings


@dataclass(frozen=True)
class GitHubResponse:
    status: int
    data: dict[str, Any] | None
    etag: str | None


class GitHubAuthNotConfiguredError(Exception):
    """Raised when no PAT/App is configured but a fetch is attempted."""


class GitHubClient:
    """Wrapper rond ``httpx.AsyncClient`` met GitHub-conventies.

    De client is bewust niet als FastAPI-dependency geregistreerd; voor
    elke fetch-burst maak je een nieuwe instance binnen een ``async
    with``-block. Dat houdt de connection-pool kort en maakt mocken in
    tests triviaal.
    """

    def __init__(
        self,
        *,
        token: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        settings = get_settings()
        self._token = token if token is not None else settings.GITHUB_TOKEN
        self._base_url = (base_url or settings.GITHUB_API_BASE_URL).rstrip("/")
        self._timeout = (
            timeout if timeout is not None else settings.GITHUB_FETCH_TIMEOUT_SECONDS
        )
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    @property
    def is_configured(self) -> bool:
        """True als er een token is. UI/route kan deze flag gebruiken om
        statusfetches over te slaan zonder errors te veroorzaken."""
        return bool(self._token)

    async def __aenter__(self) -> GitHubClient:
        if not self.is_configured:
            raise GitHubAuthNotConfiguredError(
                "Geen GITHUB_TOKEN geconfigureerd. Status-fetch overgeslagen."
            )
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "bouwmeester-github-status",
        }
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=self._timeout,
            transport=self._transport,
        )
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get(self, path: str, *, etag: str | None = None) -> GitHubResponse:
        """GET op een GitHub-API-pad. ``path`` mag absoluut of relatief zijn.

        Bij ``etag`` wordt een conditional GET gedaan. 304 betekent: niets
        veranderd, gebruik de gecachete data.
        """
        if self._client is None:
            raise RuntimeError(
                "GitHubClient niet geïnitialiseerd; gebruik 'async with'."
            )

        request_headers: dict[str, str] = {}
        if etag:
            request_headers["If-None-Match"] = etag

        response = await self._client.get(path, headers=request_headers)
        new_etag = response.headers.get("ETag")

        if response.status_code == 304:
            return GitHubResponse(status=304, data=None, etag=etag)

        if response.status_code >= 400:
            return GitHubResponse(status=response.status_code, data=None, etag=new_etag)

        return GitHubResponse(
            status=response.status_code,
            data=response.json(),
            etag=new_etag,
        )
