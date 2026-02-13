"""Abstract base class for LLM providers with capability-based data classification."""

import json
import logging
from abc import ABC, abstractmethod
from enum import StrEnum

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class DataSensitivity(StrEnum):
    """Data sensitivity levels for LLM provider routing."""

    PUBLIC = "public"  # Parliamentary data, public tag names
    INTERNAL = "internal"  # Corpus node titles/descriptions (policy content)
    CONFIDENTIAL = "confidential"  # Person names, org structure, tasks


class ProviderCapabilities(BaseModel):
    """Declares what data sensitivity levels a provider may process."""

    allowed_data: set[DataSensitivity]

    def supports(self, level: DataSensitivity) -> bool:
        return level in self.allowed_data


class TagExtractionResult(BaseModel):
    matched_tags: list[str]
    suggested_new_tags: list[str]
    samenvatting: str


class TagSuggestionResult(BaseModel):
    matched_tags: list[str]
    suggested_new_tags: list[str]


class EdgeRelevanceResult(BaseModel):
    score: float  # 0.0 - 1.0
    suggested_edge_type: str
    reason: str


class SummarizeResult(BaseModel):
    summary: str


class BaseLLMService(ABC):
    """Abstract base for all LLM providers."""

    capabilities: ProviderCapabilities

    def _parse_json(self, content: str) -> dict:
        """Parse JSON from LLM response, handling markdown code blocks."""
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        return json.loads(content.strip())

    @abstractmethod
    async def _complete(self, prompt: str, max_tokens: int = 1024) -> str:
        """Send a prompt to the LLM and return the text response."""
        ...

    async def extract_tags(
        self,
        titel: str,
        onderwerp: str,
        document_tekst: str | None,
        bestaande_tags: list[str],
        context_hint: str = "motie",
    ) -> TagExtractionResult:
        """Extract relevant tags from a parliamentary item text.

        Only public text and tag names are sent. No corpus node content
        or personal data is included.
        """
        from bouwmeester.services.llm.prompts import build_extract_tags_prompt

        prompt = build_extract_tags_prompt(
            titel=titel,
            onderwerp=onderwerp,
            document_tekst=document_tekst,
            bestaande_tags=bestaande_tags,
            context_hint=context_hint,
        )
        try:
            text = await self._complete(prompt)
            result = self._parse_json(text)
            return TagExtractionResult(
                matched_tags=result.get("matched_tags", []),
                suggested_new_tags=result.get("suggested_new_tags", []),
                samenvatting=result.get("samenvatting", ""),
            )
        except Exception:
            logger.exception("Fout bij LLM tag-extractie")
            return TagExtractionResult(
                matched_tags=[],
                suggested_new_tags=[],
                samenvatting="Tag-extractie mislukt",
            )

    async def suggest_tags(
        self,
        title: str,
        description: str | None,
        node_type: str,
        bestaande_tags: list[str],
    ) -> TagSuggestionResult:
        """Suggest tags for a corpus node based on its content."""
        from bouwmeester.services.llm.prompts import build_suggest_tags_prompt

        prompt = build_suggest_tags_prompt(
            title=title,
            description=description,
            node_type=node_type,
            bestaande_tags=bestaande_tags,
        )
        try:
            text = await self._complete(prompt)
            result = self._parse_json(text)
            return TagSuggestionResult(
                matched_tags=result.get("matched_tags", []),
                suggested_new_tags=result.get("suggested_new_tags", []),
            )
        except Exception:
            logger.exception("Fout bij LLM tag-suggestie")
            return TagSuggestionResult(matched_tags=[], suggested_new_tags=[])

    async def score_edge_relevance(
        self,
        source_title: str,
        source_description: str | None,
        target_title: str,
        target_description: str | None,
    ) -> EdgeRelevanceResult:
        """Score the relevance of a potential edge between two nodes."""
        from bouwmeester.services.llm.prompts import build_edge_relevance_prompt

        prompt = build_edge_relevance_prompt(
            source_title=source_title,
            source_description=source_description,
            target_title=target_title,
            target_description=target_description,
        )
        try:
            text = await self._complete(prompt)
            result = self._parse_json(text)
            return EdgeRelevanceResult(
                score=float(result.get("score", 0.0)),
                suggested_edge_type=result.get(
                    "suggested_edge_type", "gerelateerd_aan"
                ),
                reason=result.get("reason", ""),
            )
        except Exception:
            logger.exception("Fout bij LLM edge-relevantie scoring")
            return EdgeRelevanceResult(
                score=0.0,
                suggested_edge_type="gerelateerd_aan",
                reason="Scoring mislukt",
            )

    async def summarize(
        self,
        text: str,
        max_words: int = 100,
    ) -> SummarizeResult:
        """Produce a concise Dutch summary of the given text."""
        from bouwmeester.services.llm.prompts import build_summarize_prompt

        prompt = build_summarize_prompt(text=text, max_words=max_words)
        try:
            response = await self._complete(prompt, max_tokens=512)
            return SummarizeResult(summary=response.strip())
        except Exception:
            logger.exception("Fout bij LLM samenvatting")
            return SummarizeResult(summary="Samenvatting mislukt")
