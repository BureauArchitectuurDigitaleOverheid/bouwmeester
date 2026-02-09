"""Motie import strategy — fetches adopted moties from TK/EK."""

from datetime import date

from bouwmeester.services.import_strategies.base import FetchedItem, ImportStrategy
from bouwmeester.services.tk_api_client import TweedeKamerClient


class MotieStrategy(ImportStrategy):
    """Strategy for importing moties (motions)."""

    @property
    def item_type(self) -> str:
        return "motie"

    @property
    def politieke_input_type(self) -> str:
        return "motie"

    async def fetch_items(
        self,
        client: TweedeKamerClient,
        since: date | None,
        limit: int,
    ) -> list[FetchedItem]:
        from datetime import datetime as dt

        since_dt = dt.combine(since, dt.min.time()) if since else None
        moties = await client.fetch_moties(since=since_dt, limit=limit)
        return [
            FetchedItem(
                zaak_id=m.zaak_id,
                zaak_nummer=m.zaak_nummer,
                titel=m.titel,
                onderwerp=m.onderwerp,
                datum=m.datum.date() if m.datum else None,
                indieners=m.indieners,
                document_tekst=m.document_tekst,
                document_url=m.document_url,
                bron=m.bron,
            )
            for m in moties
        ]

    def task_title(self, item: FetchedItem) -> str:
        return f"Beoordeel motie: {item.onderwerp}"

    def notification_title(self, node_title: str) -> str:
        return f"Nieuwe aangenomen motie: {node_title}"
