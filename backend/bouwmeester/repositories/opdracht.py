"""Repository for Opdracht CRUD and filtering."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from bouwmeester.models.opdracht import Opdracht, OpdrachtNode
from bouwmeester.repositories.base import BaseRepository
from bouwmeester.schema.opdracht import (
    OpdrachtCreate,
    OpdrachtNodeCreate,
    OpdrachtUpdate,
)


class OpdrachtRepository(BaseRepository[Opdracht]):
    model = Opdracht

    async def create(self, data: OpdrachtCreate) -> Opdracht:
        node_koppelingen_data = data.node_koppelingen or []
        dump = data.model_dump(exclude={"node_koppelingen"})
        opdracht = Opdracht(**dump)
        self.session.add(opdracht)
        await self.session.flush()

        for koppeling in node_koppelingen_data:
            link = OpdrachtNode(
                opdracht_id=opdracht.id,
                node_id=koppeling.node_id,
                relatie_type=koppeling.relatie_type,
            )
            self.session.add(link)

        await self.session.flush()

        # Re-fetch with eager loading to avoid MissingGreenlet on node_koppelingen
        stmt = (
            select(Opdracht)
            .where(Opdracht.id == opdracht.id)
            .options(selectinload(Opdracht.node_koppelingen))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def update(self, id: UUID, data: OpdrachtUpdate) -> Opdracht | None:
        stmt = (
            select(Opdracht)
            .where(Opdracht.id == id)
            .options(selectinload(Opdracht.node_koppelingen))
        )
        result = await self.session.execute(stmt)
        obj = result.scalar_one_or_none()
        if obj is None:
            return None
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(obj, key, value)
        await self.session.flush()

        # Re-fetch to pick up server-side defaults (updated_at) and relationships
        stmt2 = (
            select(Opdracht)
            .where(Opdracht.id == id)
            .options(selectinload(Opdracht.node_koppelingen))
        )
        result2 = await self.session.execute(stmt2)
        return result2.scalar_one()

    async def get(self, id: UUID) -> Opdracht | None:
        stmt = (
            select(Opdracht)
            .where(Opdracht.id == id)
            .options(selectinload(Opdracht.node_koppelingen))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        *,
        begrotingsjaar: int | None = None,
        type: str | None = None,
        status: str | None = None,
        instrument_id: UUID | None = None,
        opdrachtnemer_id: UUID | None = None,
        opdrachtgever_id: UUID | None = None,
        verantwoordelijke_id: UUID | None = None,
    ) -> list[Opdracht]:
        stmt = (
            select(Opdracht)
            .options(selectinload(Opdracht.node_koppelingen))
            .offset(skip)
            .limit(limit)
        )
        if begrotingsjaar is not None:
            stmt = stmt.where(Opdracht.begrotingsjaar == begrotingsjaar)
        if type is not None:
            stmt = stmt.where(Opdracht.type == type)
        if status is not None:
            stmt = stmt.where(Opdracht.status == status)
        if instrument_id is not None:
            stmt = stmt.where(Opdracht.instrument_id == instrument_id)
        if opdrachtnemer_id is not None:
            stmt = stmt.where(Opdracht.opdrachtnemer_id == opdrachtnemer_id)
        if opdrachtgever_id is not None:
            stmt = stmt.where(Opdracht.opdrachtgever_id == opdrachtgever_id)
        if verantwoordelijke_id is not None:
            stmt = stmt.where(Opdracht.verantwoordelijke_id == verantwoordelijke_id)
        stmt = stmt.order_by(Opdracht.begrotingsjaar.desc(), Opdracht.titel)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_instrument(
        self,
        instrument_id: UUID,
        begrotingsjaar: int | None = None,
    ) -> list[Opdracht]:
        stmt = (
            select(Opdracht)
            .where(Opdracht.instrument_id == instrument_id)
            .options(selectinload(Opdracht.node_koppelingen))
        )
        if begrotingsjaar is not None:
            stmt = stmt.where(Opdracht.begrotingsjaar == begrotingsjaar)
        stmt = stmt.order_by(Opdracht.begrotingsjaar.desc(), Opdracht.titel)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_node(self, node_id: UUID) -> list[Opdracht]:
        """Get opdrachten linked to a node via instrument_id or OpdrachtNode."""
        direct = select(Opdracht.id).where(Opdracht.instrument_id == node_id)
        via_junction = select(OpdrachtNode.opdracht_id).where(
            OpdrachtNode.node_id == node_id
        )
        combined = direct.union(via_junction).subquery()
        stmt = (
            select(Opdracht)
            .where(Opdracht.id.in_(select(combined.c.id)))
            .options(selectinload(Opdracht.node_koppelingen))
            .order_by(Opdracht.begrotingsjaar.desc(), Opdracht.titel)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add_node_koppeling(
        self,
        opdracht_id: UUID,
        data: OpdrachtNodeCreate,
    ) -> OpdrachtNode:
        link = OpdrachtNode(
            opdracht_id=opdracht_id,
            node_id=data.node_id,
            relatie_type=data.relatie_type,
        )
        self.session.add(link)
        await self.session.flush()
        await self.session.refresh(link)
        return link

    async def remove_node_koppeling(
        self, opdracht_id: UUID, koppeling_id: UUID
    ) -> bool:
        obj = await self.session.get(OpdrachtNode, koppeling_id)
        if obj is None or obj.opdracht_id != opdracht_id:
            return False
        await self.session.delete(obj)
        await self.session.flush()
        return True

    async def get_summary(
        self,
        *,
        begrotingsjaar: int | None = None,
        type: str | None = None,
        status: str | None = None,
        instrument_id: UUID | None = None,
        opdrachtnemer_id: UUID | None = None,
        opdrachtgever_id: UUID | None = None,
        verantwoordelijke_id: UUID | None = None,
    ) -> dict:
        """Aggregate count, total budget, total gerealiseerd."""
        stmt = select(
            func.count(Opdracht.id).label("count"),
            func.coalesce(func.sum(Opdracht.budget), 0).label("totaal_budget"),
            func.coalesce(func.sum(Opdracht.gerealiseerd), 0).label(
                "totaal_gerealiseerd"
            ),
        )
        if begrotingsjaar is not None:
            stmt = stmt.where(Opdracht.begrotingsjaar == begrotingsjaar)
        if type is not None:
            stmt = stmt.where(Opdracht.type == type)
        if status is not None:
            stmt = stmt.where(Opdracht.status == status)
        if instrument_id is not None:
            stmt = stmt.where(Opdracht.instrument_id == instrument_id)
        if opdrachtnemer_id is not None:
            stmt = stmt.where(Opdracht.opdrachtnemer_id == opdrachtnemer_id)
        if opdrachtgever_id is not None:
            stmt = stmt.where(Opdracht.opdrachtgever_id == opdrachtgever_id)
        if verantwoordelijke_id is not None:
            stmt = stmt.where(Opdracht.verantwoordelijke_id == verantwoordelijke_id)
        result = await self.session.execute(stmt)
        row = result.one()
        return dict(row._mapping)

    async def aggregate_by_instrument(
        self,
        instrument_id: UUID,
    ) -> list[dict]:
        """Aggregate budget/gerealiseerd per begrotingsjaar for an instrument."""
        stmt = (
            select(
                Opdracht.begrotingsjaar,
                func.coalesce(func.sum(Opdracht.budget), 0).label("budget"),
                func.coalesce(func.sum(Opdracht.gerealiseerd), 0).label("gerealiseerd"),
                func.coalesce(func.sum(Opdracht.volgend_jaar_benodigd), 0).label(
                    "volgend_jaar_benodigd"
                ),
                func.coalesce(func.sum(Opdracht.volgend_jaar_aangevraagd), 0).label(
                    "volgend_jaar_aangevraagd"
                ),
                func.count(Opdracht.id).label("opdracht_count"),
            )
            .where(Opdracht.instrument_id == instrument_id)
            .group_by(Opdracht.begrotingsjaar)
            .order_by(Opdracht.begrotingsjaar)
        )
        result = await self.session.execute(stmt)
        return [dict(row._mapping) for row in result.all()]

    async def get_budget_summaries(
        self, instrument_ids: list[UUID]
    ) -> dict[UUID, tuple[Decimal, Decimal]]:
        """Return {instrument_id: (total_budget, total_gerealiseerd)} for given IDs."""
        if not instrument_ids:
            return {}
        stmt = (
            select(
                Opdracht.instrument_id,
                func.coalesce(func.sum(Opdracht.budget), 0).label("budget"),
                func.coalesce(func.sum(Opdracht.gerealiseerd), 0).label("gerealiseerd"),
            )
            .where(Opdracht.instrument_id.in_(instrument_ids))
            .group_by(Opdracht.instrument_id)
        )
        result = await self.session.execute(stmt)
        return {
            row.instrument_id: (row.budget, row.gerealiseerd) for row in result.all()
        }
