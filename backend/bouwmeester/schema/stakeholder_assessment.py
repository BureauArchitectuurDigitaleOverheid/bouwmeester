"""Pydantic schemas for StakeholderAssessment."""

import enum
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StakeholderScopeType(enum.StrEnum):
    corpus_node = "corpus_node"
    initiatief = "initiatief"


class StakeholderHouding(enum.StrEnum):
    tegen = "tegen"
    kritisch = "kritisch"
    neutraal = "neutraal"
    welwillend = "welwillend"
    voorstander = "voorstander"


class StakeholderAssessmentBase(BaseModel):
    person_id: UUID
    scope_type: StakeholderScopeType
    scope_id: UUID
    belang: int | None = Field(None, ge=1, le=5)
    houding: StakeholderHouding | None = None
    invloed: int | None = Field(None, ge=1, le=5)
    notitie: str | None = Field(None, max_length=10000)


class StakeholderAssessmentCreate(StakeholderAssessmentBase):
    pass


class StakeholderAssessmentUpdate(BaseModel):
    belang: int | None = Field(None, ge=1, le=5)
    houding: StakeholderHouding | None = None
    invloed: int | None = Field(None, ge=1, le=5)
    notitie: str | None = Field(None, max_length=10000)


class StakeholderAssessmentResponse(BaseModel):
    id: UUID
    person_id: UUID
    person_naam: str = ""
    scope_type: StakeholderScopeType
    scope_id: UUID
    belang: int | None = None
    houding: StakeholderHouding | None = None
    invloed: int | None = None
    notitie: str | None = None
    assessed_by_id: UUID | None = None
    assessed_by_naam: str | None = None
    assessed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
