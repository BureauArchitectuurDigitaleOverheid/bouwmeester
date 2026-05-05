"""Repository for StakeholderAssessment CRUD."""

from datetime import UTC
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bouwmeester.models.stakeholder_assessment import StakeholderAssessment
from bouwmeester.repositories.base import BaseRepository
from bouwmeester.schema.stakeholder_assessment import (
    StakeholderAssessmentCreate,
    StakeholderAssessmentUpdate,
)


class StakeholderAssessmentRepository(BaseRepository[StakeholderAssessment]):
    model = StakeholderAssessment

    async def list_for_scope(
        self, scope_type: str, scope_id: UUID
    ) -> list[StakeholderAssessment]:
        stmt = (
            select(StakeholderAssessment)
            .where(
                StakeholderAssessment.scope_type == scope_type,
                StakeholderAssessment.scope_id == scope_id,
            )
            .options(
                selectinload(StakeholderAssessment.person),
                selectinload(StakeholderAssessment.assessed_by),
            )
            .order_by(StakeholderAssessment.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, assessment_id: UUID) -> StakeholderAssessment | None:
        stmt = (
            select(StakeholderAssessment)
            .where(StakeholderAssessment.id == assessment_id)
            .options(
                selectinload(StakeholderAssessment.person),
                selectinload(StakeholderAssessment.assessed_by),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self, data: StakeholderAssessmentCreate, assessed_by_id: UUID | None = None
    ) -> StakeholderAssessment:
        from datetime import datetime

        assessment = StakeholderAssessment(
            person_id=data.person_id,
            scope_type=data.scope_type,
            scope_id=data.scope_id,
            belang=data.belang,
            houding=data.houding,
            invloed=data.invloed,
            notitie=data.notitie,
            assessed_by_id=assessed_by_id,
            assessed_at=datetime.now(UTC),
        )
        self.session.add(assessment)
        await self.session.flush()
        # Refresh column attrs (server_default/onupdate) and relations together.
        await self.session.refresh(assessment)
        await self.session.refresh(
            assessment, attribute_names=["person", "assessed_by"]
        )
        return assessment

    async def update(
        self,
        assessment_id: UUID,
        data: StakeholderAssessmentUpdate,
        assessed_by_id: UUID | None = None,
    ) -> StakeholderAssessment | None:
        from datetime import datetime

        assessment = await self.get_by_id(assessment_id)
        if assessment is None:
            return None
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(assessment, key, value)
        assessment.assessed_at = datetime.now(UTC)
        if assessed_by_id is not None:
            assessment.assessed_by_id = assessed_by_id
        await self.session.flush()
        # Refresh column attrs (server_default/onupdate) and relations together.
        await self.session.refresh(assessment)
        await self.session.refresh(
            assessment, attribute_names=["person", "assessed_by"]
        )
        return assessment

    async def delete(self, assessment_id: UUID) -> bool:
        assessment = await self.session.get(StakeholderAssessment, assessment_id)
        if assessment is None:
            return False
        await self.session.delete(assessment)
        await self.session.flush()
        return True
