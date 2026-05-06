"""Abstract base class for LLM providers with capability-based data classification."""

import json
import logging
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any

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


class OpdrachtContactMatch(BaseModel):
    target_id: str
    link_type: str  # "person" | "organisatie_eenheid"
    confidence: float
    reason: str
    suggested_rol: str
    source_field: str | None = None


class OpdrachtContactMatchResult(BaseModel):
    matches: list[OpdrachtContactMatch]


class GapAnalysisResult(BaseModel):
    narrative: str
    recommendations: list[str]


class LeadCandidateClassification(BaseModel):
    is_lead: bool
    confidence: float
    proposed_title: str
    proposed_description: str
    match_existing_lead_id: str | None
    reasoning: str


class BaseLLMService(ABC):
    """Abstract base for all LLM providers."""

    capabilities: ProviderCapabilities

    def _parse_json(self, content: str) -> dict:
        """Parse JSON from LLM response, handling markdown code blocks."""
        import re

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        content = content.strip()
        # Fix trailing commas (common LLM issue)
        content = re.sub(r",\s*([}\]])", r"\1", content)
        return json.loads(content)

    @abstractmethod
    async def _complete(self, prompt: str, max_tokens: int = 1024) -> str:
        """Send a prompt to the LLM and return the text response."""
        ...

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 2048,
    ) -> Any:
        """Multi-turn chat with function-calling tools.

        Returns the raw ChatCompletion from the OpenAI-compatible API.
        Subclasses that support tool calling should override this.
        """
        raise NotImplementedError("This provider does not support tool calling")

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

    async def match_opdracht_contacts(
        self,
        opdracht_titel: str,
        opdracht_beschrijving: str | None,
        fcc_contact_fields: dict[str, str],
        fcc_afdeling: str | None,
        kandidaat_personen: list[dict],
        kandidaat_eenheden: list[dict],
    ) -> OpdrachtContactMatchResult:
        """Match persons and org units to an opdracht using LLM analysis."""
        from bouwmeester.services.llm.prompts import (
            build_match_opdracht_contacts_prompt,
        )

        prompt = build_match_opdracht_contacts_prompt(
            opdracht_titel=opdracht_titel,
            opdracht_beschrijving=opdracht_beschrijving,
            fcc_contact_fields=fcc_contact_fields,
            fcc_afdeling=fcc_afdeling,
            kandidaat_personen=kandidaat_personen,
            kandidaat_eenheden=kandidaat_eenheden,
        )
        try:
            text = await self._complete(prompt, max_tokens=2048)
            result = self._parse_json(text)
            matches = [
                OpdrachtContactMatch(**m)
                for m in result.get("matches", [])
                if m.get("confidence", 0) >= 0.5
            ]
            return OpdrachtContactMatchResult(matches=matches)
        except Exception:
            logger.exception("Fout bij LLM opdracht contact matching")
            return OpdrachtContactMatchResult(matches=[])

    async def generate_gap_analysis(
        self,
        dossier_title: str,
        dossier_description: str | None,
        gaps: list[dict],
    ) -> GapAnalysisResult:
        """Generate a narrative summary and recommendations for policy gaps."""
        from bouwmeester.services.llm.prompts import build_gap_analysis_prompt

        prompt = build_gap_analysis_prompt(
            dossier_title=dossier_title,
            dossier_description=dossier_description,
            gaps=gaps,
        )
        try:
            text = await self._complete(prompt, max_tokens=1024)
            result = self._parse_json(text)
            return GapAnalysisResult(
                narrative=result.get("narrative", ""),
                recommendations=result.get("recommendations", []),
            )
        except Exception:
            logger.exception("Fout bij LLM gap-analyse")
            return GapAnalysisResult(narrative="", recommendations=[])

    async def is_mattermost_noise(self, message: str) -> bool:
        """True als het bericht ruis is (ack/emoji/no-content)."""
        from bouwmeester.services.llm.prompts import build_is_noise_prompt

        prompt = build_is_noise_prompt(message)
        try:
            text = await self._complete(prompt, max_tokens=64)
            result = self._parse_json(text)
            return bool(result.get("is_noise", False))
        except Exception:
            logger.exception("Fout bij LLM noise-classificatie")
            return False  # Bij twijfel: behouden.

    async def summarize_mattermost_message(
        self, message: str, *, max_words: int = 80
    ) -> str:
        """Vat een lang MM-bericht samen. Returns lege string bij fout."""
        from bouwmeester.services.llm.prompts import (
            build_summarize_mattermost_thread_prompt,
        )

        prompt = build_summarize_mattermost_thread_prompt(
            message=message, max_words=max_words
        )
        try:
            text = await self._complete(prompt, max_tokens=300)
            result = self._parse_json(text)
            return str(result.get("samenvatting") or "")
        except Exception:
            logger.exception("Fout bij LLM samenvatting")
            return ""

    async def classify_mattermost_lead_candidate(
        self,
        *,
        message: str,
        initiatief_naam: str,
        channel_display_name: str,
        recent_leads: list[dict],
    ) -> LeadCandidateClassification:
        """Classificeer een Mattermost-bericht als (mogelijke) lead.

        Wordt aangeroepen voor berichten in een aan een initiatief gekoppeld
        kanaal. CONFIDENTIAL: alleen door VLAM uitvoerbaar.
        """
        from bouwmeester.services.llm.prompts import (
            build_classify_mattermost_lead_prompt,
        )

        prompt = build_classify_mattermost_lead_prompt(
            message=message,
            initiatief_naam=initiatief_naam,
            channel_display_name=channel_display_name,
            recent_leads=recent_leads,
        )
        try:
            text = await self._complete(prompt, max_tokens=512)
            result = self._parse_json(text)
            match_id = result.get("match_existing_lead_id")
            if isinstance(match_id, str):
                match_id = match_id.strip() or None
            else:
                match_id = None
            return LeadCandidateClassification(
                is_lead=bool(result.get("is_lead", False)),
                confidence=float(result.get("confidence") or 0.0),
                proposed_title=str(result.get("proposed_title") or "")[:500],
                proposed_description=str(result.get("proposed_description") or ""),
                match_existing_lead_id=match_id,
                reasoning=str(result.get("reasoning") or ""),
            )
        except Exception:
            logger.exception("Fout bij LLM lead-classificatie")
            return LeadCandidateClassification(
                is_lead=False,
                confidence=0.0,
                proposed_title="",
                proposed_description="",
                match_existing_lead_id=None,
                reasoning="LLM-call mislukt",
            )
