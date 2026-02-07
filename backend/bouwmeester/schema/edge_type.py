"""Pydantic schemas for EdgeType."""

from pydantic import BaseModel, ConfigDict


class EdgeTypeBase(BaseModel):
    id: str
    label_nl: str
    label_en: str | None = None
    description: str | None = None


class EdgeTypeCreate(EdgeTypeBase):
    pass


class EdgeTypeResponse(EdgeTypeBase):
    is_custom: bool

    model_config = ConfigDict(from_attributes=True)
