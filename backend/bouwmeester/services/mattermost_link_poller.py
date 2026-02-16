"""Processes bot DMs for link codes and verifies them.

Used by the worker loop which handles polling timing.
"""

import logging
import re

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.repositories.mattermost_user import MattermostUserRepository
from bouwmeester.services.mattermost_service import MattermostService

logger = logging.getLogger(__name__)

_LINK_CODE_PATTERN = re.compile(r"BM-[a-z0-9]{6,12}", re.IGNORECASE)


class MattermostLinkPoller:
    def __init__(
        self,
        session: AsyncSession,
        mm_service: MattermostService | None = None,
    ) -> None:
        self.session = session
        self.mm_service = mm_service or MattermostService(session)
        self.repo = MattermostUserRepository(session)

    async def _safe_reply(self, channel_id: str, root_id: str, message: str) -> None:
        """Reply to a Mattermost post, logging errors instead of propagating."""
        try:
            await self.mm_service.reply_to_post(channel_id, root_id, message)
        except Exception:
            logger.exception(
                "Failed to reply to Mattermost post %s in channel %s",
                root_id,
                channel_id,
            )

    async def process_posts(self, posts: list[dict]) -> int:
        """Process a list of DM posts looking for link codes.

        Returns number of links created.
        """
        links_created = 0

        for post in posts:
            message = post.get("message", "")
            match = _LINK_CODE_PATTERN.search(message)
            if not match:
                continue

            code = match.group(0)
            mm_user_id = post.get("user_id", "")
            channel_id = post.get("channel_id", "")
            root_id = post.get("id", "")

            # Look up the code.
            link_code = await self.repo.verify_code(code)
            if not link_code:
                await self._safe_reply(
                    channel_id,
                    root_id,
                    "Hmm, die code herken ik niet. "
                    "Misschien is-ie verlopen? Genereer een nieuwe in Instellingen.",
                )
                continue

            # Check if Mattermost user is already linked.
            existing = await self.repo.get_by_mattermost_user_id(mm_user_id)
            if existing:
                await self._safe_reply(
                    channel_id,
                    root_id,
                    "Je Mattermost-account is al gekoppeld aan een account "
                    "in Bouwmeester. Wil je opnieuw koppelen? "
                    "Ontkoppel eerst via Instellingen.",
                )
                continue

            # Get the Mattermost username.
            username = await self.mm_service.get_username(mm_user_id)

            # Create the mapping — handle race condition where another path
            # already linked this user or person concurrently.
            try:
                await self.repo.create_mapping(
                    person_id=link_code.person_id,
                    mattermost_user_id=mm_user_id,
                    mattermost_username=username,
                )
            except IntegrityError:
                await self._safe_reply(
                    channel_id,
                    root_id,
                    "Dit Bouwmeester-account is al gekoppeld aan een ander "
                    "Mattermost-account. Ontkoppel eerst via Instellingen.",
                )
                continue
            await self.repo.delete_code(code)
            links_created += 1

            await self._safe_reply(
                channel_id,
                root_id,
                ":white_check_mark: Top, je bent gekoppeld! "
                "Vanaf nu stuur ik je hier updates over taken en dossiers. "
                "Typ `/bouwmeester help` om te zien wat ik nog meer kan.",
            )
            logger.info(
                "Linked Mattermost user %s to person %s",
                mm_user_id,
                link_code.person_id,
            )

        return links_created

    async def cleanup(self) -> None:
        """Clean up expired codes."""
        await self.repo.cleanup_expired_codes()
