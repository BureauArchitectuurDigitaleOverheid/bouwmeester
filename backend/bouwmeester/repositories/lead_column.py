"""Repository for LeadColumn (per-initiatief funnel-kolommen)."""

from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.slug import slugify
from bouwmeester.models.lead import Lead
from bouwmeester.models.lead_column import LeadColumn
from bouwmeester.schema.lead_column import (
    DEFAULT_COLUMNS,
    LeadColumnCreate,
    LeadColumnUpdate,
)


class LeadColumnRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_initiatief(self, initiatief_id: UUID) -> list[LeadColumn]:
        stmt = (
            select(LeadColumn)
            .where(LeadColumn.initiatief_id == initiatief_id)
            .order_by(LeadColumn.sort_order.asc(), LeadColumn.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, column_id: UUID) -> LeadColumn | None:
        return await self.session.get(LeadColumn, column_id)

    async def lead_counts_for_initiatief(self, initiatief_id: UUID) -> dict[str, int]:
        """Return {slug: count} of leads per stage in this initiatief."""
        stmt = (
            select(Lead.stage, func.count())
            .where(Lead.initiatief_id == initiatief_id)
            .group_by(Lead.stage)
        )
        result = await self.session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def count_leads_in_column(self, initiatief_id: UUID, slug: str) -> int:
        stmt = (
            select(func.count())
            .select_from(Lead)
            .where(Lead.initiatief_id == initiatief_id, Lead.stage == slug)
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def slug_or_name_exists(
        self,
        initiatief_id: UUID,
        slug: str | None = None,
        name: str | None = None,
        exclude_id: UUID | None = None,
    ) -> bool:
        clauses = []
        if slug is not None:
            clauses.append(LeadColumn.slug == slug)
        if name is not None:
            clauses.append(LeadColumn.name == name)
        if not clauses:
            return False
        from sqlalchemy import or_

        stmt = select(LeadColumn.id).where(
            LeadColumn.initiatief_id == initiatief_id, or_(*clauses)
        )
        if exclude_id is not None:
            stmt = stmt.where(LeadColumn.id != exclude_id)
        result = await self.session.execute(stmt.limit(1))
        return result.first() is not None

    async def _next_slug(self, initiatief_id: UUID, base: str) -> str:
        """Return base, base-2, base-3, ... until unique within the initiatief."""
        existing_stmt = select(LeadColumn.slug).where(
            LeadColumn.initiatief_id == initiatief_id,
            LeadColumn.slug.like(f"{base}%"),
        )
        existing = {row[0] for row in (await self.session.execute(existing_stmt)).all()}
        if base not in existing:
            return base
        i = 2
        while f"{base}-{i}" in existing:
            i += 1
        return f"{base}-{i}"

    async def _next_sort_order(self, initiatief_id: UUID) -> int:
        stmt = select(func.coalesce(func.max(LeadColumn.sort_order), -1)).where(
            LeadColumn.initiatief_id == initiatief_id
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one()) + 1

    async def create(self, initiatief_id: UUID, data: LeadColumnCreate) -> LeadColumn:
        base_slug = slugify(data.name)
        if not base_slug:
            base_slug = "kolom"
        slug = await self._next_slug(initiatief_id, base_slug)
        sort_order = await self._next_sort_order(initiatief_id)
        column = LeadColumn(
            initiatief_id=initiatief_id,
            name=data.name,
            slug=slug,
            sort_order=sort_order,
            color=data.color,
            is_active_stage=data.is_active_stage,
            is_public_visible=data.is_public_visible,
        )
        self.session.add(column)
        await self.session.flush()
        await self.session.refresh(column)
        return column

    async def update(
        self, column_id: UUID, data: LeadColumnUpdate
    ) -> LeadColumn | None:
        column = await self.get(column_id)
        if column is None:
            return None
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(column, key, value)
        await self.session.flush()
        await self.session.refresh(column)
        return column

    async def delete_with_move(
        self,
        initiatief_id: UUID,
        column_id: UUID,
        move_to_id: UUID | None,
    ) -> tuple[bool, str | None]:
        """Delete a column, optionally migrating its leads to another column.

        Returns (deleted, error_code). error_code one of:
            'not_found', 'last_column', 'leads_present', 'invalid_target'
        or None on success.
        """
        column = await self.get(column_id)
        if column is None or column.initiatief_id != initiatief_id:
            return False, "not_found"

        # Refuse to delete the last column.
        total_stmt = (
            select(func.count())
            .select_from(LeadColumn)
            .where(LeadColumn.initiatief_id == initiatief_id)
        )
        total = int((await self.session.execute(total_stmt)).scalar_one())
        if total <= 1:
            return False, "last_column"

        lead_count = await self.count_leads_in_column(initiatief_id, column.slug)
        if lead_count > 0:
            if move_to_id is None:
                return False, "leads_present"
            target = await self.get(move_to_id)
            if (
                target is None
                or target.initiatief_id != initiatief_id
                or target.id == column.id
            ):
                return False, "invalid_target"
            await self.session.execute(
                update(Lead)
                .where(
                    Lead.initiatief_id == initiatief_id,
                    Lead.stage == column.slug,
                )
                .values(stage=target.slug)
            )

        await self.session.execute(delete(LeadColumn).where(LeadColumn.id == column.id))
        await self.session.flush()
        return True, None

    async def reorder(
        self, initiatief_id: UUID, column_ids: list[UUID]
    ) -> tuple[bool, str | None]:
        """Rewrite sort_order 0..N-1 in the given order.

        Returns (ok, error_code). error_code is 'mismatch' if the set
        differs from the initiatief's columns.
        """
        existing = await self.list_for_initiatief(initiatief_id)
        existing_ids = {c.id for c in existing}
        if existing_ids != set(column_ids) or len(existing) != len(column_ids):
            return False, "mismatch"
        for idx, cid in enumerate(column_ids):
            await self.session.execute(
                update(LeadColumn).where(LeadColumn.id == cid).values(sort_order=idx)
            )
        await self.session.flush()
        return True, None

    async def seed_defaults(self, initiatief_id: UUID) -> None:
        """Insert the 7 default columns for a new initiatief.

        Idempotent: skips slugs that already exist (ON CONFLICT semantics
        emulated by checking first, since SQLAlchemy's bulk-insert lacks
        a portable upsert without dialect-specific code).
        """
        existing_stmt = select(LeadColumn.slug).where(
            LeadColumn.initiatief_id == initiatief_id
        )
        existing = {row[0] for row in (await self.session.execute(existing_stmt)).all()}
        for idx, default in enumerate(DEFAULT_COLUMNS):
            if default["slug"] in existing:
                continue
            self.session.add(
                LeadColumn(
                    initiatief_id=initiatief_id,
                    name=default["name"],
                    slug=default["slug"],
                    sort_order=idx,
                    color=default["color"],
                    is_active_stage=default["is_active_stage"],
                    is_public_visible=default["is_public_visible"],
                )
            )
        await self.session.flush()
