"""LLM service for tag extraction from motie texts using Claude."""

import json
import logging

import anthropic
from pydantic import BaseModel

from bouwmeester.core.config import get_settings

logger = logging.getLogger(__name__)


class TagExtractionResult(BaseModel):
    matched_tags: list[str]
    suggested_new_tags: list[str]
    samenvatting: str


class LLMService:
    def __init__(self) -> None:
        settings = get_settings()
        self.client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.LLM_MODEL

    def _parse_json(self, content: str) -> dict:
        """Parse JSON from LLM response, handling markdown code blocks."""
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        return json.loads(content.strip())

    _TYPE_LABELS: dict[str, str] = {
        "motie": "aangenomen motie",
        "kamervraag": "schriftelijke kamervraag",
        "toezegging": "toezegging",
        "amendement": "amendement",
        "commissiedebat": "commissiedebat",
    }

    async def extract_tags(
        self,
        titel: str,
        onderwerp: str,
        document_tekst: str | None,
        bestaande_tags: list[str],
        context_hint: str = "motie",
    ) -> TagExtractionResult:
        """Extract relevant tags from a parliamentary item text.

        Only public text and tag names (strings) are sent to Claude.
        No corpus node content or personal data is included.
        """
        type_label = self._TYPE_LABELS.get(context_hint, context_hint)
        item_content = f"TITEL: {titel}\nONDERWERP: {onderwerp}"
        if document_tekst:
            item_content += f"\n\nDOCUMENTTEKST:\n{document_tekst}"

        tags_json = json.dumps(bestaande_tags, ensure_ascii=False)
        prompt = (
            "Je bent een beleidsanalist van het ministerie van BZK"
            " (Binnenlandse Zaken en Koninkrijksrelaties)."
            f" Analyseer deze {type_label} en bepaal welke"
            " beleidstags relevant zijn.\n\n"
            f"{type_label.upper()}:\n{item_content}\n\n"
            f"BESTAANDE TAGS IN HET SYSTEEM:\n{tags_json}\n\n"
            "Instructies:\n"
            "- Selecteer ALLEEN tags die specifiek relevant"
            f" zijn voor deze {type_label}\n"
            "- Vermijd te brede/generieke tags. Tags als"
            ' "overheid", "data", "digitalisering" op zichzelf'
            " zijn te breed — gebruik altijd de meest specifieke"
            " subtag (bijv."
            ' "digitalisering/AI/generatieve-AI"'
            ' in plaats van "digitalisering")\n'
            "- Selecteer een brede parent-tag ALLEEN als de"
            f" {type_label} echt over het hele brede onderwerp gaat\n"
            "- Stel maximaal 3 nieuwe tags voor als de"
            " bestaande tags het onderwerp niet dekken\n"
            "- Nieuwe tags moeten het hiërarchische"
            " pad-formaat volgen"
            ' (bijv. "digitalisering/AI/privacy")\n'
            "- Geef een korte samenvatting (max 2 zinnen)"
            f" van wat de {type_label} vraagt en waarom\n\n"
            "Geef je analyse als JSON"
            " (en ALLEEN JSON, geen andere tekst):\n"
            "{\n"
            '  "samenvatting": "...",\n'
            '  "matched_tags": ["specifieke/tag1",'
            ' "specifieke/tag2"],\n'
            '  "suggested_new_tags":'
            ' ["nieuwe/specifieke/tag"]\n'
            "}"
        )

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )

            result = self._parse_json(response.content[0].text)

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
