"""LLM service package — multi-provider architecture with capability-based routing."""

from bouwmeester.services.llm.base import (
    BaseLLMService,
    DataSensitivity,
    EdgeRelevanceResult,
    GapAnalysisResult,
    ProviderCapabilities,
    TagExtractionResult,
    TagSuggestionResult,
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
    "TagExtractionResult",
    "TagSuggestionResult",
    "clear_config_cache",
    "get_llm_service",
    "get_llm_service_for",
]
