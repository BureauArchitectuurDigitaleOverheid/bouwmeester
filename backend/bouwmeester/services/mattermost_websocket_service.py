"""Persistente Mattermost-websocket voor het meelezen in gekoppelde kanalen.

Auth/heartbeat/reconnect, plus recovery via REST na disconnect. Voor de
verwerking van individuele posts delegeren we naar
``MattermostIngestService``.

Protocol-referentie: het Mattermost websocket-protocol uit
`claude-threads/src/platform/mattermost/client.ts`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from urllib.parse import urlparse

import httpx
import websockets
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import async_session
from bouwmeester.models.mattermost_channel_link import MattermostChannelLink
from bouwmeester.services.mattermost_ingest_service import MattermostIngestService
from bouwmeester.services.mattermost_service import (
    MattermostService,
    _load_mattermost_config,
)

logger = logging.getLogger(__name__)


_HEARTBEAT_INTERVAL = 30.0  # sec
_RECONNECT_BACKOFF_BASE = 2.0
_RECONNECT_BACKOFF_MAX = 60.0
_BACKOFF_RESET_AFTER_HEALTHY_SEC = 120.0


def _ws_url_from_http(http_url: str) -> str:
    """Vervang het scheme zodat http(s) → ws(s) en plak `/api/v4/websocket`."""
    parsed = urlparse(http_url.rstrip("/"))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    netloc = parsed.netloc
    return f"{scheme}://{netloc}/api/v4/websocket"


class MattermostWebsocketService:
    """Eén persistente websocket-verbinding voor het meelezen.

    Loop-pattern: ``run()`` blijft draaien tot de event-loop hem stopt.
    Bij disconnects past hij exponential backoff toe binnen dezelfde call.
    """

    def __init__(self) -> None:
        self._seq = 0
        self._stop = False
        self._bot_user_id: str | None = None
        self._mm_base_url: str | None = None

    async def run(self) -> None:
        """Hoofdloop: connect, auth, lees events, reconnect bij disconnect."""
        backoff = _RECONNECT_BACKOFF_BASE
        while not self._stop:
            connected_at: float | None = None
            try:
                async with async_session() as bootstrap:
                    config = await _load_mattermost_config(bootstrap)
                enabled = (config.get("MATTERMOST_ENABLED") or "").lower()
                if enabled in ("", "false", "0"):
                    await asyncio.sleep(_RECONNECT_BACKOFF_MAX)
                    continue

                http_url = config.get("MATTERMOST_URL", "")
                token = config.get("MATTERMOST_BOT_TOKEN", "")
                if not http_url or not token:
                    logger.debug("Mattermost niet geconfigureerd, skip websocket-loop")
                    await asyncio.sleep(_RECONNECT_BACKOFF_MAX)
                    continue

                self._mm_base_url = http_url.rstrip("/")
                ws_url = _ws_url_from_http(http_url)
                logger.info("Mattermost websocket: connect %s", ws_url)
                async with websockets.connect(
                    ws_url, ping_interval=None, max_size=2 * 1024 * 1024
                ) as ws:
                    connected_at = time.monotonic()
                    await self._authenticate(ws, token)
                    await self._resolve_bot_user_id()
                    await self._recover_missed_posts()
                    await self._read_loop(ws)
                    backoff = _RECONNECT_BACKOFF_BASE
            except asyncio.CancelledError:
                logger.info("Mattermost websocket: loop cancelled")
                raise
            except Exception:
                logger.exception(
                    "Mattermost websocket: error, reconnect in %.1fs", backoff
                )

            if self._stop:
                break

            # Reset backoff als we lang stabiel verbonden waren.
            if (
                connected_at is not None
                and time.monotonic() - connected_at > _BACKOFF_RESET_AFTER_HEALTHY_SEC
            ):
                backoff = _RECONNECT_BACKOFF_BASE

            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _RECONNECT_BACKOFF_MAX)

    async def stop(self) -> None:
        self._stop = True

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    async def _authenticate(self, ws, token: str) -> None:
        await ws.send(
            json.dumps(
                {
                    "seq": self._next_seq(),
                    "action": "authentication_challenge",
                    "data": {"token": token},
                }
            )
        )
        # Wacht op de eerste paar messages tot we hello/auth-ok zien.
        for _ in range(5):
            raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            event = msg.get("event")
            if event == "hello":
                logger.info("Mattermost websocket: authenticated")
                return
            if msg.get("status") == "OK":
                continue
            if msg.get("status") == "FAIL" or msg.get("error"):
                raise RuntimeError(f"Mattermost websocket auth failed: {msg}")
        raise RuntimeError("Mattermost websocket: no hello received")

    async def _resolve_bot_user_id(self) -> None:
        async with async_session() as session:
            service = MattermostService(session)
            try:
                self._bot_user_id = await service.get_bot_user_id()
            finally:
                await service.close()

    async def _read_loop(self, ws) -> None:
        last_activity = time.monotonic()
        while not self._stop:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=_HEARTBEAT_INTERVAL)
                last_activity = time.monotonic()
            except TimeoutError:
                # Stuur een lichte ping via een no-op authentication_challenge?
                # Mattermost gebruikt geen expliciet ping/pong voor clients;
                # bij langdurige stilte (>2x interval) breken we de connectie.
                if time.monotonic() - last_activity > _HEARTBEAT_INTERVAL * 2:
                    raise RuntimeError("Mattermost websocket: idle timeout")
                continue

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            await self._dispatch(msg)

    async def _dispatch(self, msg: dict) -> None:
        event = msg.get("event")
        if event != "posted":
            # `post_edited`, `post_deleted`, `reaction_added` worden in een
            # latere PR ingehaakt. Voor PR1 alleen 'posted'.
            return

        data = msg.get("data") or {}
        post_raw = data.get("post")
        if not post_raw:
            return
        try:
            post = json.loads(post_raw) if isinstance(post_raw, str) else post_raw
        except json.JSONDecodeError:
            logger.warning("Kan posted-event niet parsen")
            return

        post_id = post.get("id")
        channel_id = post.get("channel_id")
        if not post_id or not channel_id:
            return

        async with async_session() as session:
            try:
                await self._record_post(session, post)
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception("Fout bij verwerken Mattermost-post %s", post_id)

    async def _record_post(self, session: AsyncSession, post: dict) -> None:
        """Verwerk één Mattermost-post via :class:`MattermostIngestService`."""
        ingest = MattermostIngestService(
            session,
            bot_user_id=self._bot_user_id,
            mm_base_url=self._mm_base_url,
        )
        await ingest.ingest_post(post)

    async def _recover_missed_posts(self) -> None:
        """Haal posts op die binnenkwamen terwijl we offline waren.

        We doen dit per gekoppeld kanaal, vanaf ``last_seen_post_at``.
        Posts die we al hadden (unique post_id) worden door de
        IntegrityError-handler in ``_record_post`` afgevangen.
        """
        async with async_session() as session:
            stmt = select(MattermostChannelLink).where(
                MattermostChannelLink.disabled_at.is_(None)
            )
            result = await session.execute(stmt)
            links = list(result.scalars().all())

            if not links:
                return

            service = MattermostService(session)
            try:
                if not await service.is_enabled():
                    return
                for link in links:
                    since = link.last_seen_post_at or 0
                    if since == 0:
                        # Niet recoveren bij verse koppeling — anders
                        # importeren we een hele kanaal-historie.
                        continue
                    try:
                        posts = await service.get_channel_posts_since(
                            link.channel_id, since
                        )
                    except httpx.HTTPError:
                        logger.exception(
                            "Recovery faalde voor kanaal %s", link.channel_id
                        )
                        continue
                    for post in posts:
                        try:
                            await self._record_post(session, post)
                        except Exception:
                            logger.exception(
                                "Recovery: fout bij post %s", post.get("id")
                            )
                await session.commit()
            finally:
                await service.close()
