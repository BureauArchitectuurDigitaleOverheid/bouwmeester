"""Kamervraag import strategy — fetches schriftelijke vragen from TK."""

from datetime import date, datetime

from bouwmeester.services.import_strategies.base import FetchedItem, ImportStrategy
from bouwmeester.services.tk_api_client import TweedeKamerClient

# Cap kamervragen per poll to avoid excessive LLM calls
MAX_KAMERVRAAG_FETCH = 25


class KamervraagStrategy(ImportStrategy):
    """Strategy for importing kamervragen (schriftelijke vragen).

    Fetches recent kamervragen from the TK API. Since there is no
    relevance pre-filter (unlike moties which filter by 'aangenomen'),
    the fetch limit is capped to avoid excessive LLM calls.
    """

    @property
    def item_type(self) -> str:
        return "kamervraag"

    @property
    def politieke_input_type(self) -> str:
        return "kamervraag"

    @property
    def requires_llm(self) -> bool:
        return True

    @property
    def supports_ek(self) -> bool:
        return False

    async def fetch_items(
        self,
        client: object,
        since: date | None,
        limit: int,
    ) -> list[FetchedItem]:
        if not isinstance(client, TweedeKamerClient):
            return []

        since_dt = datetime.combine(since, datetime.min.time()) if since else None
        effective_limit = min(limit, MAX_KAMERVRAAG_FETCH)
        zaken = await client.fetch_zaak_by_soort(
            soort="Schriftelijke vragen",
            since=since_dt,
            limit=effective_limit,
        )
        return [
            FetchedItem(
                zaak_id=z.zaak_id,
                zaak_nummer=z.zaak_nummer,
                titel=z.titel,
                onderwerp=z.onderwerp,
                datum=z.datum.date() if z.datum else None,
                indieners=z.indieners,
                document_tekst=z.document_tekst,
                document_url=z.document_url,
                bron=z.bron,
                deadline=z.termijn.date() if z.termijn else None,
            )
            for z in zaken
        ]

    def task_title(self, item: FetchedItem) -> str:
        return f"Beoordeel kamervraag: {item.onderwerp}"

    def task_priority(self, item: FetchedItem) -> str:
        return "hoog"

    def notification_title(self, node_title: str) -> str:
        return f"Nieuwe kamervraag: {node_title}"

    def context_hint(self) -> str:
        return "kamervraag"
