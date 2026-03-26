"""Pydantic schemas for FeatureToggle."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FeatureToggleResponse(BaseModel):
    id: UUID
    organisatie_eenheid_id: UUID
    feature_key: str
    enabled: bool

    model_config = ConfigDict(from_attributes=True)


class FeatureToggleUpdate(BaseModel):
    feature_key: str
    enabled: bool


class FeatureToggleBulkUpdate(BaseModel):
    toggles: list[FeatureToggleUpdate]


class EenheidFeatureConfig(BaseModel):
    organisatie_eenheid_id: UUID
    organisatie_eenheid_naam: str
    features: dict[str, bool]
