"""Core Mattermost API client for sending DMs, channel posts,
and formatting messages.

Settings are read from:
1. AppConfig table in the database (set via admin panel)
2. Environment variables / config.py settings (fallback)
"""

import ipaddress
import logging
import time
from urllib.parse import urlparse
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.config import get_settings
from bouwmeester.models.notification import Notification
from bouwmeester.repositories.mattermost_user import MattermostUserRepository
from bouwmeester.services.mattermost_utils import escape_mattermost_md

logger = logging.getLogger(__name__)

# In-memory config cache with TTL — also cleared by admin config update endpoint.
_mm_config_cache: dict[str, str] | None = None
_mm_config_cache_ts: float = 0.0
_MM_CONFIG_CACHE_TTL = 60  # seconds


def clear_mattermost_config_cache() -> None:
    """Clear the Mattermost config cache so the next call rebuilds from DB."""
    global _mm_config_cache, _mm_config_cache_ts  # noqa: PLW0603
    _mm_config_cache = None
    _mm_config_cache_ts = 0.0


async def _load_mattermost_config(db: AsyncSession) -> dict[str, str]:
    """Load Mattermost config from the AppConfig table, decrypting secrets."""
    global _mm_config_cache, _mm_config_cache_ts  # noqa: PLW0603
    now = time.monotonic()
    cache_fresh = (now - _mm_config_cache_ts) < _MM_CONFIG_CACHE_TTL
    if _mm_config_cache is not None and cache_fresh:
        return _mm_config_cache

    try:
        from bouwmeester.core.encryption import decrypt_value
        from bouwmeester.models.app_config import AppConfig

        result = await db.execute(
            select(AppConfig.key, AppConfig.value, AppConfig.is_secret).where(
                AppConfig.key.in_(
                    [
                        "MATTERMOST_ENABLED",
                        "MATTERMOST_URL",
                        "MATTERMOST_BOT_TOKEN",
                        "MATTERMOST_WEBHOOK_TOKEN",
                        "MATTERMOST_NOTIFICATION_CHANNEL_ID",
                    ]
                )
            )
        )
        _mm_config_cache = {}
        for key, value, is_secret in result.all():
            if value:
                _mm_config_cache[key] = decrypt_value(value) if is_secret else value
        _mm_config_cache_ts = now
    except Exception:
        logger.debug("Could not load Mattermost config from database, using env vars")
        # Return empty dict but do NOT cache — allow immediate retry next call.
        return {}

    return _mm_config_cache


# Notification type → color for Mattermost attachment sidebar.
_NOTIFICATION_COLORS: dict[str, str] = {
    "task_assigned": "#3B82F6",  # blue
    "task_overdue": "#EF4444",  # red
    "task_completed": "#22C55E",  # green
    "task_reassigned": "#F59E0B",  # amber
    "node_updated": "#6366F1",  # indigo
    "edge_created": "#8B5CF6",  # violet
    "coverage_needed": "#F97316",  # orange
    "stakeholder_added": "#06B6D4",  # cyan
    "stakeholder_role_changed": "#14B8A6",  # teal
    "politieke_input_imported": "#EC4899",  # pink
    "mention": "#3B82F6",  # blue
    "access_request": "#F59E0B",  # amber
    "placement_request": "#6366F1",  # indigo
    "placement_approved": "#22C55E",  # green
    "placement_denied": "#EF4444",  # red
}

# Types that should go to the channel (broadcast) instead of DM.
_CHANNEL_NOTIFICATION_TYPES = frozenset({"politieke_input_imported"})

# Re-export for backwards compatibility within this module.
_escape_md = escape_mattermost_md


def _validate_mattermost_url(url: str) -> None:
    """Validate that MATTERMOST_URL is not pointing to internal/metadata endpoints."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"MATTERMOST_URL must use http or https, got: {parsed.scheme}")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("MATTERMOST_URL has no hostname")

    # Allow Docker service names (no dots, not an IP).
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        # It's a hostname — block localhost explicitly.
        if hostname in ("localhost", "127.0.0.1", "0.0.0.0"):
            raise ValueError("MATTERMOST_URL must not point to localhost")
        return

    # It's an IP — block private, loopback, link-local, reserved, and multicast.
    if (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
    ):
        raise ValueError(f"MATTERMOST_URL must not point to {addr}")


class MattermostService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()
        self.repo = MattermostUserRepository(session)
        self._client: httpx.AsyncClient | None = None
        self._config: dict[str, str] | None = None

    async def _get_config(self) -> dict[str, str]:
        """Load Mattermost config from DB (cached), falling back to env vars."""
        if self._config is None:
            self._config = await _load_mattermost_config(self.session)
        return self._config

    def _cfg(self, key: str, fallback: str | bool = "") -> str:
        """Sync config access (use after _get_config has been called)."""
        if self._config:
            val = self._config.get(key)
            if val:
                return val
        return str(getattr(self.settings, key, fallback))

    async def is_enabled(self) -> bool:
        await self._get_config()
        enabled = self._cfg("MATTERMOST_ENABLED", False)
        bot_token = self._cfg("MATTERMOST_BOT_TOKEN")
        return bool(enabled and enabled.lower() not in ("false", "0", "") and bot_token)

    async def _get_client(self) -> httpx.AsyncClient:
        await self._get_config()
        if self._client is None:
            url = self._cfg("MATTERMOST_URL")
            token = self._cfg("MATTERMOST_BOT_TOKEN")
            if not token:
                raise ValueError("MATTERMOST_BOT_TOKEN is not configured")
            _validate_mattermost_url(url)
            self._client = httpx.AsyncClient(
                base_url=url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=10.0,
            )
        return self._client

    async def get_bot_user_id(self) -> str | None:
        """Get the bot's own Mattermost user ID."""
        client = await self._get_client()
        try:
            resp = await client.get("/api/v4/users/me")
            resp.raise_for_status()
            return resp.json().get("id")
        except httpx.HTTPError:
            logger.exception("Failed to get bot user ID")
            return None

    async def get_bot_dm_url(self) -> str | None:
        """Build a browser URL for DMing the bot: {base}/{team}/messages/@{username}."""
        client = await self._get_client()
        try:
            me_resp = await client.get("/api/v4/users/me")
            me_resp.raise_for_status()
            username = me_resp.json().get("username")
            if not username:
                return None

            # Try bot's own teams first, fall back to any team on the server.
            # Bot accounts are often not explicitly added to a team.
            team_name: str | None = None
            teams_resp = await client.get("/api/v4/users/me/teams")
            teams_resp.raise_for_status()
            teams = teams_resp.json()
            if teams:
                team_name = teams[0].get("name")

            if not team_name:
                all_teams_resp = await client.get(
                    "/api/v4/teams", params={"per_page": 1}
                )
                all_teams_resp.raise_for_status()
                all_teams = all_teams_resp.json()
                if all_teams:
                    team_name = all_teams[0].get("name")

            if not team_name:
                return None

            base_url = self._cfg("MATTERMOST_URL").rstrip("/")
            return f"{base_url}/{team_name}/messages/@{username}"
        except httpx.HTTPError:
            logger.exception("Failed to build bot DM URL")
            return None

    async def send_dm(
        self,
        person_id: UUID,
        text: str,
        props: dict | None = None,
    ) -> bool:
        """Send a direct message to a person via their Mattermost mapping."""
        mapping = await self.repo.get_by_person_id(person_id)
        if not mapping:
            logger.debug("No Mattermost mapping for person %s", person_id)
            return False

        client = await self._get_client()
        bot_user_id = await self.get_bot_user_id()
        if not bot_user_id:
            return False

        try:
            # Create or get DM channel.
            ch_resp = await client.post(
                "/api/v4/channels/direct",
                json=[bot_user_id, mapping.mattermost_user_id],
            )
            ch_resp.raise_for_status()
            channel_id = ch_resp.json()["id"]

            payload: dict = {"channel_id": channel_id, "message": text}
            if props:
                payload["props"] = props

            msg_resp = await client.post("/api/v4/posts", json=payload)
            msg_resp.raise_for_status()
            return True
        except httpx.HTTPError:
            logger.exception("Failed to send DM to person %s", person_id)
            return False

    async def send_channel_message(
        self,
        channel_id: str,
        text: str,
        props: dict | None = None,
    ) -> bool:
        """Post a message to a Mattermost channel."""
        client = await self._get_client()
        try:
            payload: dict = {"channel_id": channel_id, "message": text}
            if props:
                payload["props"] = props
            resp = await client.post("/api/v4/posts", json=payload)
            resp.raise_for_status()
            return True
        except httpx.HTTPError:
            logger.exception("Failed to send channel message to %s", channel_id)
            return False

    def _deep_link(self, notification: Notification) -> str:
        """Build a deep link back to the Bouwmeester frontend."""
        base = self.settings.FRONTEND_URL.rstrip("/")
        # Validate scheme to prevent open redirect via misconfigured FRONTEND_URL.
        parsed = urlparse(base)
        if parsed.scheme not in ("http", "https"):
            logger.warning("FRONTEND_URL has invalid scheme: %s", parsed.scheme)
            return ""
        if notification.related_task_id:
            return f"{base}/taken?task={notification.related_task_id}"
        if notification.related_node_id:
            return f"{base}/nodes/{notification.related_node_id}"
        return base

    def format_notification(
        self, notification: Notification, *, with_actions: bool = True
    ) -> tuple[str, dict]:
        """Format a notification into a Mattermost message with rich attachment.

        Returns (text, props) where props contains attachments and optionally
        interactive button integrations.
        """
        color = _NOTIFICATION_COLORS.get(notification.type, "#94A3B8")
        deep_link = self._deep_link(notification)

        fields = []
        if notification.related_node_id:
            fields.append(
                {
                    "short": True,
                    "title": "Node",
                    "value": str(notification.related_node_id),
                }
            )
        if notification.related_task_id:
            fields.append(
                {
                    "short": True,
                    "title": "Taak",
                    "value": str(notification.related_task_id),
                }
            )

        from bouwmeester.utils.tiptap import tiptap_to_plain

        plain_message = tiptap_to_plain(notification.message) or ""

        escaped_title = _escape_md(notification.title)
        escaped_message = _escape_md(plain_message)
        attachment: dict = {
            "fallback": escaped_title,
            "color": color,
            "title": escaped_title,
            "title_link": deep_link,
            "text": escaped_message,
            "fields": fields,
            "footer": "Bouwmeester",
        }

        # Add interactive buttons for actionable notification types.
        if with_actions:
            actions = self._build_actions(notification, deep_link)
            if actions:
                attachment["actions"] = actions

        props: dict = {"attachments": [attachment]}
        return ("", props)

    def _build_actions(self, notification: Notification, deep_link: str) -> list[dict]:
        """Build interactive button actions for a notification."""
        backend_url = self.settings.BACKEND_URL.rstrip("/")
        actions: list[dict] = []

        # Add "Taak afronden" for task-related notifications.
        if (
            notification.type in ("task_assigned", "task_overdue")
            and notification.related_task_id
        ):
            actions.append(
                {
                    "id": "complete_task",
                    "name": "Taak afronden",
                    "integration": {
                        "url": f"{backend_url}/api/mattermost/action",
                        "context": {
                            "action": "complete_task",
                            "task_id": str(notification.related_task_id),
                            "notification_id": str(notification.id),
                        },
                    },
                }
            )

        return actions

    async def send_notification(self, notification: Notification) -> bool:
        """Route a notification to DM or channel based on type."""
        if not await self.is_enabled():
            return False

        text, props = self.format_notification(notification)

        if notification.type in _CHANNEL_NOTIFICATION_TYPES:
            channel_id = self._cfg("MATTERMOST_NOTIFICATION_CHANNEL_ID")
            if not channel_id:
                logger.debug("No notification channel configured, skipping broadcast")
                return False
            return await self.send_channel_message(channel_id, text, props)

        return await self.send_dm(notification.person_id, text, props)

    async def get_bot_dm_posts(
        self, since: int, *, max_channels: int = 50
    ) -> list[dict]:
        """Poll for new DMs sent to the bot since a given timestamp (ms).

        Used by the link code poller to detect incoming link codes.
        Caps the number of DM channels checked to avoid API rate-limiting.
        """
        bot_user_id = await self.get_bot_user_id()
        if not bot_user_id:
            return []

        client = await self._get_client()
        try:
            # Get DM channels for the bot.
            resp = await client.get(
                f"/api/v4/users/{bot_user_id}/channels",
                params={"last_delete_at": 0},
            )
            resp.raise_for_status()
            channels = resp.json()

            dm_channels = [ch for ch in channels if ch.get("type") == "D"]
            # Sort by last_post_at descending so we check the most recently
            # active channels first, then cap to avoid API storms.
            dm_channels.sort(key=lambda c: c.get("last_post_at", 0), reverse=True)
            dm_channels = dm_channels[:max_channels]

            posts = []
            for ch in dm_channels:
                try:
                    pr = await client.get(
                        f"/api/v4/channels/{ch['id']}/posts",
                        params={"since": since, "per_page": 20},
                    )
                    pr.raise_for_status()
                    data = pr.json()
                    for post_id in data.get("order", []):
                        post = data["posts"].get(post_id, {})
                        # Only look at messages from others (not the bot).
                        if post.get("user_id") != bot_user_id:
                            posts.append(post)
                except httpx.HTTPError:
                    logger.debug("Failed to get posts for channel %s", ch["id"])
                    continue

            return posts
        except httpx.HTTPError:
            logger.exception("Failed to poll bot DMs")
            return []

    async def reply_to_post(self, channel_id: str, root_id: str, message: str) -> bool:
        """Reply to a specific post in a channel."""
        client = await self._get_client()
        try:
            resp = await client.post(
                "/api/v4/posts",
                json={
                    "channel_id": channel_id,
                    "root_id": root_id,
                    "message": message,
                },
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPError:
            logger.exception("Failed to reply to post %s", root_id)
            return False

    async def update_post(
        self, post_id: str, message: str, props: dict | None = None
    ) -> bool:
        """Update an existing Mattermost post."""
        client = await self._get_client()
        try:
            payload: dict = {"id": post_id, "message": message}
            if props:
                payload["props"] = props
            resp = await client.put(f"/api/v4/posts/{post_id}", json=payload)
            resp.raise_for_status()
            return True
        except httpx.HTTPError:
            logger.exception("Failed to update post %s", post_id)
            return False

    async def get_username(self, mattermost_user_id: str) -> str:
        """Fetch the Mattermost username for a user ID."""
        client = await self._get_client()
        try:
            resp = await client.get(f"/api/v4/users/{mattermost_user_id}")
            resp.raise_for_status()
            return resp.json().get("username", mattermost_user_id)
        except httpx.HTTPError:
            return mattermost_user_id

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
