"""Pydantic schemas for LLM-powered features."""

from pydantic import BaseModel, ConfigDict


class TagSuggestionRequest(BaseModel):
    title: str
    description: str | None = None
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
    text: str
    max_words: int = 100


class SummarizeResponse(BaseModel):
    summary: str
    available: bool = True
