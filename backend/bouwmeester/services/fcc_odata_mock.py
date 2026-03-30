"""
Mock client for the Fortes Change Cloud OData API.

Drop-in replacement for ``FccODataClient`` that returns realistic sample data
using the real FCC schema (Portfolio_item entity with Dutch field names).
"""

import logging
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

_MOCK_PORTFOLIO_ITEMS: list[dict[str, Any]] = [
    {
        "Portfolio_itemKey": "900001",
        "Naam": "Realisatie publieke NL-Wallet",
        "Omschrijving": (
            "Realisatie van de publieke NL-Wallet voor digitale identiteit."
        ),
        "Type": "Initiatief",
        "Status": "",
        "Funnelfase": "GDI Doorontwikkeling",
        "Budget_huidig_jaar_": 4_900_000,
        "Gerealiseerde_kosten_huidig_jaar_": 0,
        "Budget_totaal_": 0,
        "Gerealiseerde_kosten_totaal_": 0,
        "Startdatum_gepland_": "2026-01-01",
        "Einddatum_gepland_": "2026-12-31",
        "Laatst_gewijzigd_op": "2026-03-28",
        "Uitvoeringsorganisatie": "ICTU",
        "Afdeling_PDD": "Toegang",
        "PDD_Domein": "Toegang",
        "Eigenaar": "",
        "Contact_opdrachtnemer": "NTB",
        "Contactpersoon_opdrachtgever": "",
        "Status_Planning_2": "green",
        "Status_Budget": "green",
        "Status_Risico_s": "green",
        "Status_Doelrealisatie": "orange",
        "Portfolio": "Directie PDD",
        "Labels": "GDI,Sub-opdracht",
    },
    {
        "Portfolio_itemKey": "900002",
        "Naam": "Doorontwikkeling DigiD",
        "Omschrijving": "Doorontwikkeling van DigiD inclusief niveau Hoog.",
        "Type": "Initiatief",
        "Status": "",
        "Funnelfase": "GDI Doorontwikkeling",
        "Budget_huidig_jaar_": 12_000_000,
        "Gerealiseerde_kosten_huidig_jaar_": 3_200_000,
        "Startdatum_gepland_": "2026-01-01",
        "Einddatum_gepland_": "2026-12-31",
        "Laatst_gewijzigd_op": "2026-03-25",
        "Uitvoeringsorganisatie": "Logius",
        "Afdeling_PDD": "Toegang",
        "PDD_Domein": "Toegang",
        "Status_Planning_2": "green",
        "Status_Budget": "green",
        "Portfolio": "Directie PDD",
        "Labels": "GDI",
    },
    {
        "Portfolio_itemKey": "900003",
        "Naam": "Beheer en exploitatie Overheid.nl",
        "Omschrijving": "Beheer en doorontwikkeling van Overheid.nl.",
        "Type": "Initiatief",
        "Status": "",
        "Funnelfase": "GDI Doorontwikkeling",
        "Budget_huidig_jaar_": 3_500_000,
        "Gerealiseerde_kosten_huidig_jaar_": 1_100_000,
        "Startdatum_gepland_": "2026-01-01",
        "Einddatum_gepland_": "2026-12-31",
        "Laatst_gewijzigd_op": "2026-03-20",
        "Uitvoeringsorganisatie": "KOOP",
        "Afdeling_PDD": "Informatie",
        "PDD_Domein": "Informatie",
        "Status_Planning_2": "green",
        "Status_Budget": "orange",
        "Portfolio": "Directie PDD",
    },
    {
        "Portfolio_itemKey": "900004",
        "Naam": "Implementatie API Design Rules",
        "Omschrijving": (
            "Brede implementatie van de API Design Rules bij landelijke voorzieningen."
        ),
        "Type": "Initiatief",
        "Status": "",
        "Funnelfase": "GDI Doorontwikkeling",
        "Budget_huidig_jaar_": 750_000,
        "Gerealiseerde_kosten_huidig_jaar_": 200_000,
        "Startdatum_gepland_": "2026-04-01",
        "Einddatum_gepland_": "2027-03-31",
        "Laatst_gewijzigd_op": "2026-03-15",
        "Uitvoeringsorganisatie": "Logius",
        "Afdeling_PDD": "Interactie",
        "PDD_Domein": "Interactie",
        "Status_Planning_2": "green",
        "Status_Budget": "green",
        "Portfolio": "Directie PDD",
    },
    {
        "Portfolio_itemKey": "900005",
        "Naam": "Programma Federatief Datastelsel",
        "Omschrijving": "Realisatie van het Federatief Datastelsel voor de overheid.",
        "Type": "Initiatief",
        "Status": "",
        "Funnelfase": "GDI Doorontwikkeling",
        "Budget_huidig_jaar_": 2_800_000,
        "Gerealiseerde_kosten_huidig_jaar_": 0,
        "Startdatum_gepland_": "2025-09-01",
        "Einddatum_gepland_": "2027-08-31",
        "Laatst_gewijzigd_op": "2026-03-22",
        "Uitvoeringsorganisatie": "ICTU",
        "Afdeling_PDD": "Data",
        "PDD_Domein": "Data",
        "Status_Planning_2": "orange",
        "Status_Budget": "green",
        "Portfolio": "Directie PDD",
    },
]

_MOCK_METADATA: dict[str, dict[str, list[str]]] = {
    "entity_sets": {
        "Portfolio": [
            "PortfolioKey",
            "Naam",
            "Status",
            "Omschrijving",
        ],
        "Portfolio_item": [
            "Portfolio_itemKey",
            "Naam",
            "Omschrijving",
            "Type",
            "Status",
            "Funnelfase",
            "Budget_huidig_jaar_",
            "Gerealiseerde_kosten_huidig_jaar_",
            "Budget_totaal_",
            "Gerealiseerde_kosten_totaal_",
            "Startdatum_gepland_",
            "Einddatum_gepland_",
            "Laatst_gewijzigd_op",
            "Uitvoeringsorganisatie",
            "Afdeling_PDD",
            "PDD_Domein",
            "Eigenaar",
            "Project_Nummer",
            "Labels",
            "Portfolio",
        ],
        "Risico": [
            "RisicoKey",
            "Omschrijving",
            "Status",
            "Prioriteit",
            "Impact",
            "Kans",
            "Portfolio_item",
        ],
        "Issue": [
            "IssueKey",
            "Omschrijving",
            "Status",
            "Prioriteit",
            "Portfolio_item",
        ],
        "CostEntry": [
            "CostEntryKey",
            "Portfolio_item",
            "MonthDate",
            "Budget",
            "Besteed",
            "Prognose",
        ],
    },
}


class FccODataMockClient:
    """
    Mock implementation of the FCC OData client.

    Uses the real FCC schema (Portfolio_item with Dutch field names).
    """

    def __init__(self, base_url: str = "", api_key: str = "") -> None:
        self.base_url = base_url
        self.api_key = api_key
        self._store: dict[str, list[dict[str, Any]]] = {
            "Portfolio_item": deepcopy(_MOCK_PORTFOLIO_ITEMS),
        }

    async def close(self) -> None:
        """No-op for the mock client."""

    async def __aenter__(self) -> "FccODataMockClient":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def discover_metadata(self) -> dict[str, dict[str, list[str]]]:
        """Return a realistic metadata schema."""
        logger.info(
            "FCC mock: returning metadata for %d entity sets",
            len(_MOCK_METADATA["entity_sets"]),
        )
        return deepcopy(_MOCK_METADATA)

    async def fetch_entities(
        self,
        entity_name: str,
        *,
        filters: str | None = None,
        select: list[str] | None = None,
        expand: str | None = None,
        top: int | None = None,
        skip: int | None = None,
        orderby: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return mock entities, applying top/skip/select/filters."""
        entities = deepcopy(self._store.get(entity_name, []))

        # Basic $filter support for key lookups
        if filters and "eq" in filters:
            # Parse "Portfolio_itemKey eq '900001'" style filters
            parts = filters.split("eq", 1)
            if len(parts) == 2:
                field = parts[0].strip()
                value = parts[1].strip().strip("'\"")
                entities = [e for e in entities if str(e.get(field)) == value]

        if skip is not None:
            entities = entities[skip:]
        if top is not None:
            entities = entities[:top]

        if select:
            select_set = set(select)
            entities = [
                {k: v for k, v in e.items() if k in select_set} for e in entities
            ]

        logger.info("FCC mock: returning %d '%s' entities", len(entities), entity_name)
        return entities

    async def get_entity(
        self,
        entity_name: str,
        key: str,
        key_field: str = "Portfolio_itemKey",
    ) -> dict[str, Any] | None:
        """Return a single entity by key field."""
        for entity in self._store.get(entity_name, []):
            if str(entity.get(key_field)) == str(key):
                logger.info("FCC mock: found '%s(%s)'", entity_name, key)
                return deepcopy(entity)
        logger.debug("FCC mock: '%s(%s)' not found", entity_name, key)
        return None

    async def create_entity(
        self, entity_name: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Create an entity in the in-memory store."""
        entity = deepcopy(data)
        if "Portfolio_itemKey" not in entity:
            entity["Portfolio_itemKey"] = str(uuid.uuid4().int)[:6]
        entity.setdefault(
            "Laatst_gewijzigd_op",
            datetime.now(UTC).strftime("%Y-%m-%d"),
        )

        self._store.setdefault(entity_name, []).append(entity)
        logger.info(
            "FCC mock: created '%s' entity with key=%s",
            entity_name,
            entity.get("Portfolio_itemKey"),
        )
        return deepcopy(entity)

    async def update_entity(
        self, entity_name: str, key: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Merge data into an existing entity."""
        for entity in self._store.get(entity_name, []):
            if str(entity.get("Portfolio_itemKey")) == str(key):
                entity.update(data)
                entity["Laatst_gewijzigd_op"] = datetime.now(UTC).strftime("%Y-%m-%d")
                logger.info("FCC mock: updated '%s(%s)'", entity_name, key)
                return deepcopy(entity)

        logger.warning(
            "FCC mock: '%s(%s)' not found for update",
            entity_name,
            key,
        )
        return {**data, "Portfolio_itemKey": key}
