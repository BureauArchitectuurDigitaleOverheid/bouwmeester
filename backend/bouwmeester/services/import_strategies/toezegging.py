"""Toezegging import strategy — fetches government commitments from TK."""

from datetime import date, datetime

from bouwmeester.services.import_strategies.base import FetchedItem, ImportStrategy
from bouwmeester.services.tk_api_client import TweedeKamerClient

# BZK-related ministry name fragment used for filtering
BZK_MINISTERIE = "Binnenlandse Zaken"


class ToezeggingStrategy(ImportStrategy):
    """Strategy for importing toezeggingen (government commitments).

    Toezeggingen are a dedicated entity in the TK API, not a Zaak sub-type.
    They have a Ministerie field that allows direct BZK filtering without LLM.
    """

    @property
    def item_type(self) -> str:
        return "toezegging"

    @property
    def politieke_input_type(self) -> str:
        return "toezegging"

    @property
    def requires_llm(self) -> bool:
        return True

    @property
    def supports_ek(self) -> bool:
        return False

    @property
    def always_import(self) -> bool:
        return True

    async def fetch_items(
        self,
        client: object,
        since: date | None,
        limit: int,
    ) -> list[FetchedItem]:
        if not isinstance(client, TweedeKamerClient):
            return []

        since_dt = datetime.combine(since, datetime.min.time()) if since else None
        toezeggingen = await client.fetch_toezeggingen(
            ministerie=BZK_MINISTERIE,
            since=since_dt,
            limit=limit,
        )
        return [
            FetchedItem(
                zaak_id=t.toezegging_id,
                zaak_nummer=t.nummer,
                titel=t.tekst[:200] if t.tekst else "",
                onderwerp=t.tekst or "",
                datum=t.datum_nakoming.date() if t.datum_nakoming else None,
                indieners=([t.naam_bewindspersoon] if t.naam_bewindspersoon else []),
                bron=t.bron,
                deadline=(t.datum_nakoming.date() if t.datum_nakoming else None),
                ministerie=t.ministerie,
                extra_data={
                    "status": t.status,
                    "activiteit_nummer": t.activiteit_nummer,
                },
            )
            for t in toezeggingen
        ]

    def politieke_input_status(self, item: FetchedItem) -> str:
        status = (item.extra_data or {}).get("status", "")
        status_map = {
            "Openstaand": "openstaand",
            "Deels voldaan": "deels_voldaan",
            "Voldaan": "voldaan",
        }
        return status_map.get(status, "openstaand")

    def task_title(self, item: FetchedItem) -> str:
        onderwerp = item.onderwerp[:80] if item.onderwerp else "onbekend"
        return f"Beoordeel toezegging: {onderwerp}"

    def task_priority(self, item: FetchedItem) -> str:
        return "normaal"

    def notification_title(self, node_title: str) -> str:
        return f"Nieuwe toezegging: {node_title}"

    def context_hint(self) -> str:
        return "toezegging"
