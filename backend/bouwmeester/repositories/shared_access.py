"""Repository for cross-org shared access grants."""

from datetime import date
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from bouwmeester.models.shared_access import SharedAccess
from bouwmeester.repositories.base import BaseRepository


class SharedAccessRepository(BaseRepository[SharedAccess]):
    model = SharedAccess

    async def list_for_eenheden(self, eenheid_ids: list[UUID]) -> list[SharedAccess]:
        """Return active shares involving the given eenheden."""
        if not eenheid_ids:
            return []
        today = date.today()
        stmt = (
            select(SharedAccess)
            .where(
                or_(
                    SharedAccess.source_eenheid_id.in_(eenheid_ids),
                    SharedAccess.target_eenheid_id.in_(eenheid_ids),
                ),
                SharedAccess.geldig_van <= today,
                or_(
                    SharedAccess.geldig_tot.is_(None),
                    SharedAccess.geldig_tot >= today,
                ),
            )
            .options(
                selectinload(SharedAccess.source_eenheid),
                selectinload(SharedAccess.target_eenheid),
            )
            .order_by(SharedAccess.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_incoming_for_eenheden(
        self, eenheid_ids: list[UUID]
    ) -> list[SharedAccess]:
        """Return active shares where any of the given eenheden are the target."""
        if not eenheid_ids:
            return []
        today = date.today()
        stmt = (
            select(SharedAccess)
            .where(
                SharedAccess.target_eenheid_id.in_(eenheid_ids),
                SharedAccess.geldig_van <= today,
                or_(
                    SharedAccess.geldig_tot.is_(None),
                    SharedAccess.geldig_tot >= today,
                ),
            )
            .options(
                selectinload(SharedAccess.source_eenheid),
                selectinload(SharedAccess.source_node),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_shared_eenheid_ids(
        self, target_eenheid_ids: list[UUID]
    ) -> list[UUID]:
        """Return source eenheid IDs shared with any of the target eenheden."""
        if not target_eenheid_ids:
            return []
        today = date.today()
        stmt = select(SharedAccess.source_eenheid_id).where(
            SharedAccess.target_eenheid_id.in_(target_eenheid_ids),
            SharedAccess.source_eenheid_id.is_not(None),
            SharedAccess.geldig_van <= today,
            or_(
                SharedAccess.geldig_tot.is_(None),
                SharedAccess.geldig_tot >= today,
            ),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_shared_node_ids(self, target_eenheid_ids: list[UUID]) -> list[UUID]:
        """Return source node IDs shared with any of the target eenheden."""
        if not target_eenheid_ids:
            return []
        today = date.today()
        stmt = select(SharedAccess.source_node_id).where(
            SharedAccess.target_eenheid_id.in_(target_eenheid_ids),
            SharedAccess.source_node_id.is_not(None),
            SharedAccess.geldig_van <= today,
            or_(
                SharedAccess.geldig_tot.is_(None),
                SharedAccess.geldig_tot >= today,
            ),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
