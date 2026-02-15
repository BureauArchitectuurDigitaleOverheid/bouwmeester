"""Pydantic schemas for EdgeSchemaRule."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EdgeSchemaRuleCreate(BaseModel):
    from_node_type: str = Field(max_length=50)
    to_node_type: str = Field(max_length=50)
    edge_type_id: str = Field(max_length=100)


class EdgeSchemaRuleResponse(BaseModel):
    id: UUID
    from_node_type: str
    to_node_type: str
    edge_type_id: str

    model_config = ConfigDict(from_attributes=True)


class ValidEdgeTypesResponse(BaseModel):
    edge_type_ids: list[str]
    schema_active: bool
