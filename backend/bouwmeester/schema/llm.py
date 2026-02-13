"""Pydantic schemas for LLM-powered features."""

from pydantic import BaseModel, ConfigDict, Field


class TagSuggestionRequest(BaseModel):
    title: str = Field(max_length=500)
    description: str | None = Field(default=None, max_length=50000)
    node_type: str = "dossier"


class TagSuggestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    matched_tags: list[str]
    suggested_new_tags: list[str]
    available: bool = True


class EdgeSuggestionRequest(BaseModel):
    node_id: str


class EdgeSuggestionItem(BaseModel):
    target_node_id: str
    target_node_title: str
    target_node_type: str
    confidence: float
    suggested_edge_type: str
    reason: str


class EdgeSuggestionResponse(BaseModel):
    suggestions: list[EdgeSuggestionItem]
    available: bool = True


class SummarizeRequest(BaseModel):
    text: str = Field(max_length=50000)
    max_words: int = Field(default=100, ge=10, le=500)


class SummarizeResponse(BaseModel):
    summary: str
    available: bool = True
