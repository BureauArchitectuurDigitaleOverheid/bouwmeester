"""Kamervraag import strategy — fetches schriftelijke vragen from TK."""

from datetime import date

from bouwmeester.services.import_strategies.base import FetchedItem, ImportStrategy
from bouwmeester.services.tk_api_client import TweedeKamerClient


class KamervraagStrategy(ImportStrategy):
    """Strategy for importing kamervragen (schriftelijke vragen)."""

    @property
    def item_type(self) -> str:
        return "kamervraag"

    @property
    def politieke_input_type(self) -> str:
        return "kamervraag"

    @property
    def requires_llm(self) -> bool:
        return True

    async def fetch_items(
        self,
        client: object,
        since: date | None,
        limit: int,
    ) -> list[FetchedItem]:
        if not isinstance(client, TweedeKamerClient):
            return []

        from datetime import datetime as dt

        since_dt = dt.combine(since, dt.min.time()) if since else None
        zaken = await client.fetch_zaak_by_soort(
            soort="Schriftelijke vragen",
            since=since_dt,
            limit=limit,
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
