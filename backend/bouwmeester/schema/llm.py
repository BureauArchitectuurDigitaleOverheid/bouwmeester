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


# --- C1: Smart Task Creation ---


class TaskSuggestionRequest(BaseModel):
    node_title: str = Field(max_length=500)
    node_description: str | None = Field(default=None, max_length=50000)
    node_type: str = "dossier"


class TaskSuggestionResponse(BaseModel):
    title: str
    description: str
    available: bool = True


# --- B3: Gap Detection ---


class GapItem(BaseModel):
    step_number: int
    step_question: str
    missing_types: list[str]
    present_types: list[str]
    has_stakeholders: bool = True


class GapAnalysisRequest(BaseModel):
    dossier_id: str


class GapAnalysisResponse(BaseModel):
    gaps: list[GapItem]
    completed_count: int
    total_steps: int
    narrative: str = ""
    recommendations: list[str] = []
    available: bool = True


class CorpusGapSummaryItem(BaseModel):
    dossier_id: str
    dossier_title: str
    completed_count: int
    total_steps: int
    has_stakeholders: bool


class CorpusGapOverviewResponse(BaseModel):
    items: list[CorpusGapSummaryItem]
    total: int


# --- A5: Kompas Guidance ---


class KompasGuidanceRequest(BaseModel):
    dossier_id: str
    step_node_types: list[str]
    step_description: str = ""
    max_candidates: int = Field(default=10, ge=1, le=50)


class KompasGuidanceResponse(BaseModel):
    suggestions: list[EdgeSuggestionItem]
    available: bool = True
