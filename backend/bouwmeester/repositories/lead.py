"""Repository for Lead CRUD and queries."""

from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from bouwmeester.core.org_context import OrgContext, apply_org_filter
from bouwmeester.models.lead import Lead
from bouwmeester.models.lead_activity import LeadActivity
from bouwmeester.repositories.base import BaseRepository
from bouwmeester.schema.lead import LeadCreate, LeadStage, LeadUpdate


def _lead_options():
    """Standard eager-load options for lead queries."""
    return [
        selectinload(Lead.assignee),
        selectinload(Lead.externe_organisatie),
        selectinload(Lead.organisatie_eenheid),
        selectinload(Lead.attachments),
    ]


class LeadRepository(BaseRepository[Lead]):
    model = Lead

    async def get(self, id: UUID, org_ctx: OrgContext | None = None) -> Lead | None:
        stmt = select(Lead).where(Lead.id == id).options(*_lead_options())
        stmt = apply_org_filter(stmt, Lead.organisatie_eenheid_id, org_ctx)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_detail(
        self, id: UUID, org_ctx: OrgContext | None = None
    ) -> Lead | None:
        from bouwmeester.models.lead_contact import LeadContact
        from bouwmeester.models.lead_node import LeadNode

        stmt = (
            select(Lead)
            .where(Lead.id == id)
            .options(
                selectinload(Lead.assignee),
                selectinload(Lead.externe_organisatie),
                selectinload(Lead.organisatie_eenheid),
                selectinload(Lead.attachments),
                selectinload(Lead.activities).selectinload(LeadActivity.author),
                selectinload(Lead.contacts).selectinload(LeadContact.person),
                selectinload(Lead.linked_nodes).selectinload(LeadNode.node),
            )
        )
        stmt = apply_org_filter(stmt, Lead.organisatie_eenheid_id, org_ctx)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        stage: LeadStage | None = None,
        tag: str | None = None,
        assignee_id: UUID | None = None,
        org_ctx: OrgContext | None = None,
    ) -> list[Lead]:
        stmt = select(Lead).options(*_lead_options()).offset(skip).limit(limit)
        if stage is not None:
            stmt = stmt.where(Lead.stage == stage)
        if tag is not None:
            stmt = stmt.where(Lead.tags.op("@>")(f'["{tag}"]'))
        if assignee_id is not None:
            stmt = stmt.where(Lead.assignee_id == assignee_id)
        stmt = apply_org_filter(stmt, Lead.organisatie_eenheid_id, org_ctx)
        stmt = stmt.order_by(Lead.sort_order.asc(), Lead.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, data: LeadCreate, author_id: UUID | None = None) -> Lead:
        lead = Lead(**data.model_dump())
        self.session.add(lead)
        await self.session.flush()

        # Auto-create "Lead aangemaakt" activity
        activity = LeadActivity(
            lead_id=lead.id,
            author_id=author_id,
            content="Lead aangemaakt",
            activity_type="note",
        )
        self.session.add(activity)
        await self.session.flush()

        await self.session.refresh(
            lead,
            attribute_names=[
                "assignee",
                "externe_organisatie",
                "organisatie_eenheid",
                "attachments",
            ],
        )
        return lead

    async def update(self, id: UUID, data: LeadUpdate) -> Lead | None:
        lead = await self.session.get(Lead, id)
        if lead is None:
            return None
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(lead, key, value)
        await self.session.flush()
        await self.session.refresh(
            lead,
            attribute_names=[
                "updated_at",
                "assignee",
                "externe_organisatie",
                "organisatie_eenheid",
                "attachments",
            ],
        )
        return lead

    async def move(
        self, id: UUID, stage: LeadStage, author_id: UUID | None = None
    ) -> Lead | None:
        lead = await self.session.get(Lead, id)
        if lead is None:
            return None
        old_stage = lead.stage
        lead.stage = stage
        await self.session.flush()

        # Auto-create stage_change activity
        activity = LeadActivity(
            lead_id=lead.id,
            author_id=author_id,
            content=f"Stage gewijzigd: {old_stage} -> {stage}",
            activity_type="stage_change",
            metadata_={"from": old_stage, "to": stage},
        )
        self.session.add(activity)
        await self.session.flush()

        await self.session.refresh(
            lead,
            attribute_names=[
                "updated_at",
                "assignee",
                "externe_organisatie",
                "organisatie_eenheid",
                "attachments",
            ],
        )
        return lead

    async def reorder(self, lead_ids: list[UUID], stage: LeadStage) -> list[Lead]:
        for idx, lead_id in enumerate(lead_ids):
            lead = await self.session.get(Lead, lead_id)
            if lead is not None and lead.stage == stage:
                lead.sort_order = idx
        await self.session.flush()
        # Return updated leads in the new order
        stmt = (
            select(Lead)
            .where(Lead.stage == stage, Lead.id.in_(lead_ids))
            .options(*_lead_options())
            .order_by(Lead.sort_order.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete(self, id: UUID) -> bool:
        lead = await self.session.get(Lead, id)
        if lead is None:
            return False
        await self.session.delete(lead)
        await self.session.flush()
        return True

    async def get_metrics(self, org_ctx: OrgContext | None = None) -> dict:
        # Total count
        total_stmt = select(func.count()).select_from(Lead)
        total_stmt = apply_org_filter(total_stmt, Lead.organisatie_eenheid_id, org_ctx)
        total = (await self.session.execute(total_stmt)).scalar_one()

        # Count per stage
        stage_stmt = select(Lead.stage, func.count()).group_by(Lead.stage)
        stage_stmt = apply_org_filter(stage_stmt, Lead.organisatie_eenheid_id, org_ctx)
        stage_result = await self.session.execute(stage_stmt)
        by_stage = {row[0]: row[1] for row in stage_result.all()}

        # Stale count: next_action_date < today and not in terminal stages
        stale_stmt = (
            select(func.count())
            .select_from(Lead)
            .where(
                Lead.next_action_date < date.today(),
                Lead.stage.notin_(["in_the_pocket", "koelkast"]),
            )
        )
        stale_stmt = apply_org_filter(stale_stmt, Lead.organisatie_eenheid_id, org_ctx)
        stale_count = (await self.session.execute(stale_stmt)).scalar_one()

        return {
            "total": total,
            "by_stage": by_stage,
            "stale_count": stale_count,
        }
