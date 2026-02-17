"""LLM service package — multi-provider architecture with capability-based routing."""

from bouwmeester.services.llm.base import (
    BaseLLMService,
    DataSensitivity,
    EdgeRelevanceResult,
    GapAnalysisResult,
    ProviderCapabilities,
    SearchInterpretationResult,
    SummarizeResult,
    TagExtractionResult,
    TagSuggestionResult,
    TaskSuggestionResult,
)
from bouwmeester.services.llm.factory import (
    clear_config_cache,
    get_llm_service,
    get_llm_service_for,
)

__all__ = [
    "BaseLLMService",
    "DataSensitivity",
    "EdgeRelevanceResult",
    "GapAnalysisResult",
    "ProviderCapabilities",
    "SearchInterpretationResult",
    "SummarizeResult",
    "TagExtractionResult",
    "TagSuggestionResult",
    "TaskSuggestionResult",
    "clear_config_cache",
    "get_llm_service",
    "get_llm_service_for",
]
