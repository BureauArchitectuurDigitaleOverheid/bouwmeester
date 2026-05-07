"""Repository for Mattermost user mappings and link codes."""

import secrets
import string
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.config import get_settings
from bouwmeester.models.mattermost_user import MattermostLinkCode, MattermostUser

_CODE_CHARS = string.ascii_lowercase + string.digits


class MattermostUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_person_id(self, person_id: UUID) -> MattermostUser | None:
        stmt = select(MattermostUser).where(MattermostUser.person_id == person_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_mattermost_user_id(
        self, mattermost_user_id: str
    ) -> MattermostUser | None:
        stmt = select(MattermostUser).where(
            MattermostUser.mattermost_user_id == mattermost_user_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_mattermost_username(
        self, mattermost_username: str
    ) -> MattermostUser | None:
        stmt = select(MattermostUser).where(
            MattermostUser.mattermost_username == mattermost_username
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_mapping(
        self,
        person_id: UUID,
        mattermost_user_id: str,
        mattermost_username: str,
    ) -> MattermostUser:
        mapping = MattermostUser(
            person_id=person_id,
            mattermost_user_id=mattermost_user_id,
            mattermost_username=mattermost_username,
        )
        self.session.add(mapping)
        await self.session.flush()
        await self.session.refresh(mapping)
        return mapping

    async def delete_by_person_id(self, person_id: UUID) -> bool:
        stmt = delete(MattermostUser).where(MattermostUser.person_id == person_id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    # ---- Link codes ----

    async def get_active_code(self, person_id: UUID) -> MattermostLinkCode | None:
        """Return the active (non-expired) link code for a person, if any."""
        now = datetime.now(UTC)
        stmt = select(MattermostLinkCode).where(
            MattermostLinkCode.person_id == person_id,
            MattermostLinkCode.expires_at > now,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_link_code(self, person_id: UUID) -> MattermostLinkCode:
        # Delete any existing codes for this person.
        await self.session.execute(
            delete(MattermostLinkCode).where(MattermostLinkCode.person_id == person_id)
        )
        settings = get_settings()
        code = "BM-" + "".join(
            secrets.choice(_CODE_CHARS)
            for _ in range(settings.MATTERMOST_LINK_CODE_LENGTH)
        )
        now = datetime.now(UTC)
        link_code = MattermostLinkCode(
            person_id=person_id,
            code=code,
            expires_at=now
            + timedelta(
                minutes=settings.MATTERMOST_LINK_CODE_TTL_MINUTES,
            ),
        )
        self.session.add(link_code)
        await self.session.flush()
        await self.session.refresh(link_code)
        return link_code

    async def verify_code(self, code: str) -> MattermostLinkCode | None:
        now = datetime.now(UTC)
        stmt = select(MattermostLinkCode).where(
            MattermostLinkCode.code == code,
            MattermostLinkCode.expires_at > now,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_code(self, code: str) -> None:
        await self.session.execute(
            delete(MattermostLinkCode).where(MattermostLinkCode.code == code)
        )
        await self.session.flush()

    async def cleanup_expired_codes(self) -> int:
        now = datetime.now(UTC)
        stmt = delete(MattermostLinkCode).where(MattermostLinkCode.expires_at <= now)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount
