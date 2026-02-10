"""Pydantic schemas for EdgeType."""

from pydantic import BaseModel, ConfigDict, Field


class EdgeTypeBase(BaseModel):
    id: str = Field(max_length=100)
    label_nl: str = Field(max_length=200)
    label_en: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=2000)


class EdgeTypeCreate(EdgeTypeBase):
    pass


class EdgeTypeResponse(EdgeTypeBase):
    is_custom: bool

    model_config = ConfigDict(from_attributes=True)
