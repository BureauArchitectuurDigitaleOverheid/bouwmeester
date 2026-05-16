"""FCC import service - pulls projects from Fortes Change Cloud into Opdrachten."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bouwmeester.core.config import get_settings
from bouwmeester.core.encryption import decrypt_value
from bouwmeester.core.text import unescape_html
from bouwmeester.models.app_config import AppConfig
from bouwmeester.models.opdracht import Opdracht
from bouwmeester.schema.fcc import SyncDirection, SyncStatus
from bouwmeester.services.fcc_sync_log_helper import log_fcc_sync

logger = logging.getLogger(__name__)


class FccImportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()

    async def get_config_value(self, key: str) -> str:
        """Get a config value from AppConfig, falling back to settings."""
        result = await self.session.execute(
            select(AppConfig).where(AppConfig.key == key)
        )
        entry = result.scalar_one_or_none()
        if entry and entry.value:
            return decrypt_value(entry.value)
        # Settings returns typed values (bool for FCC_PUSH_ENABLED etc.),
        # convert to str for uniform handling.
        raw = getattr(self.settings, key, "")
        return str(raw) if not isinstance(raw, str) else raw

    async def is_push_enabled(self) -> bool:
        """Check whether push (writing to FCC) is enabled."""
        val = await self.get_config_value("FCC_PUSH_ENABLED")
        return str(val).lower() == "true"

    async def get_client(self):
        """Create an FCC OData client based on configuration.

        Returns the mock client when FCC_USE_MOCK is true (for dev without
        a real FCC environment). Returns None when neither FCC_ODATA_URL
        nor FCC_USE_MOCK is configured.
        """
        use_mock = await self.get_config_value("FCC_USE_MOCK")
        if str(use_mock).lower() == "true":
            from bouwmeester.services.fcc_odata_mock import FccODataMockClient

            return FccODataMockClient()

        url = await self.get_config_value("FCC_ODATA_URL")
        api_key = await self.get_config_value("FCC_API_KEY")

        if not url:
            return None

        from bouwmeester.services.fcc_odata_client import FccODataClient

        return FccODataClient(base_url=url, api_key=api_key)

    async def poll_and_import(self) -> int:
        """Poll FCC OData for new/changed projects and import as Opdrachten."""
        client = await self.get_client()
        if client is None:
            return 0

        entity_name = (
            await self.get_config_value("FCC_PROJECT_ENTITY") or "Portfolio_item"
        )
        count = 0

        try:
            async with client:
                projects = await client.fetch_entities(
                    entity_name,
                    orderby="Laatst_gewijzigd_op desc",
                )

                for project_data in projects:
                    try:
                        imported = await self._process_project(
                            project_data, entity_name
                        )
                        if imported:
                            count += 1
                    except Exception:
                        fcc_id = project_data.get("Portfolio_itemKey", "unknown")
                        logger.exception("Error processing FCC project %s", fcc_id)
                        log_fcc_sync(
                            self.session,
                            direction="inbound",
                            action="error",
                            details={"fcc_id": fcc_id},
                            error_message=f"Import failed for {fcc_id}",
                        )
        except Exception:
            logger.exception("Error fetching FCC projects")
            log_fcc_sync(
                self.session,
                direction="inbound",
                action="error",
                error_message="Failed to connect to FCC OData API",
            )

        logger.info("FCC import: %d projects imported/updated", count)
        return count

    async def _process_project(self, data: dict, entity_type: str) -> bool:
        """Process a single FCC project. Returns True if created or updated."""
        fcc_id = str(data.get("Portfolio_itemKey", ""))
        if not fcc_id:
            return False

        # Parse modification date from FCC (Edm.Date, not DateTime)
        fcc_modified = self.parse_fcc_date(data)

        # Check for existing opdracht with this fcc_id
        stmt = select(Opdracht).where(Opdracht.fcc_id == fcc_id)
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Update only if FCC version is newer
            if (
                fcc_modified
                and existing.fcc_modified_at
                and fcc_modified <= existing.fcc_modified_at
            ):
                return False

            # Skip if we have pending changes to push
            if existing.sync_status == SyncStatus.pending_push:
                existing.sync_status = SyncStatus.conflict
                log_fcc_sync(
                    self.session,
                    opdracht_id=existing.id,
                    direction="inbound",
                    action="conflict",
                    details={
                        "fcc_id": fcc_id,
                        "reason": "Local pending_push conflicts with FCC update",
                    },
                )
                await self.session.flush()
                return True

            self._apply_fcc_data(existing, data)
            await self._resolve_opdrachtnemer(existing, data)
            existing.fcc_modified_at = fcc_modified
            existing.last_synced_at = datetime.now(UTC)
            existing.sync_status = SyncStatus.synced
            existing.fcc_raw_data = data

            log_fcc_sync(
                self.session,
                opdracht_id=existing.id,
                direction="inbound",
                action="updated",
                details={"fcc_id": fcc_id},
            )
            await self.session.flush()
            return True
        else:
            # Create new opdracht from FCC data
            opdracht = Opdracht(
                type="opdracht",
                titel=data.get("Naam") or f"FCC-{fcc_id}",
                beschrijving=data.get("Omschrijving"),
                begrotingsjaar=datetime.now(UTC).year,
                fcc_id=fcc_id,
                fcc_entity_type=entity_type,
                sync_status=SyncStatus.synced,
                sync_direction=SyncDirection.inbound,
                fcc_raw_data=data,
                fcc_modified_at=fcc_modified,
                last_synced_at=datetime.now(UTC),
                status="actief",
            )
            self._apply_fcc_data(opdracht, data)
            self.session.add(opdracht)
            await self.session.flush()
            await self._resolve_opdrachtnemer(opdracht, data)
            await self.session.flush()

            log_fcc_sync(
                self.session,
                opdracht_id=opdracht.id,
                direction="inbound",
                action="created",
                details={"fcc_id": fcc_id, "titel": opdracht.titel},
            )
            return True

    def _apply_fcc_data(self, opdracht: Opdracht, data: dict) -> None:
        """Map FCC Portfolio_item fields to Opdracht fields."""
        from datetime import date
        from decimal import Decimal

        if naam := data.get("Naam"):
            opdracht.titel = unescape_html(naam)
        if desc := data.get("Omschrijving"):
            opdracht.beschrijving = unescape_html(desc)
        if (budget := data.get("Budget_huidig_jaar_")) is not None:
            try:
                opdracht.budget = Decimal(str(budget))
            except (ValueError, TypeError):
                pass
        if (gerealiseerd := data.get("Gerealiseerde_kosten_huidig_jaar_")) is not None:
            try:
                opdracht.gerealiseerd = Decimal(str(gerealiseerd))
            except (ValueError, TypeError):
                pass
        if start := data.get("Startdatum_gepland_"):
            try:
                opdracht.startdatum = date.fromisoformat(str(start)[:10])
            except (ValueError, AttributeError):
                pass
        if end := data.get("Einddatum_gepland_"):
            try:
                opdracht.einddatum = date.fromisoformat(str(end)[:10])
            except (ValueError, AttributeError):
                pass
        if ref := data.get("Project_Nummer"):
            opdracht.referentie = ref

        # FCC metadata fields — assign unconditionally so cleared FCC values
        # propagate (empty string becomes None).
        opdracht.fcc_funnelfase = data.get("Funnelfase") or None
        opdracht.fcc_afdeling = data.get("Afdeling_PDD") or None
        opdracht.fcc_portfolio = data.get("Portfolio") or None
        opdracht.fcc_labels = data.get("Labels") or None

    async def _resolve_opdrachtnemer(self, opdracht: Opdracht, data: dict) -> None:
        """Link Uitvoeringsorganisatie to opdrachtnemer via OrganisatieEenheid.

        Strategie:
          1. Probeer match op afkorting (case-insensitive). FCC-data is
             afkorting-zwaar ('RvIG', 'RDW', 'DPC').
          2. Probeer match op naam (case-insensitive).
          3. Geen match? Maak nieuwe OrganisatieEenheid aan onder synthetische
             groep 'Marktpartijen en overige' met bron='fcc_import'.
        """
        from sqlalchemy import select as _select

        from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid

        uitvoering = unescape_html((data.get("Uitvoeringsorganisatie") or "").strip())
        if not uitvoering:
            opdracht.opdrachtnemer_eenheid_id = None
            return

        # 1. Match op afkorting
        eenheid = (
            (
                await self.session.execute(
                    _select(OrganisatieEenheid)
                    .where(
                        OrganisatieEenheid.afkorting.ilike(uitvoering),
                        OrganisatieEenheid.geldig_tot.is_(None),
                    )
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )

        # 2. Match op naam
        if eenheid is None:
            eenheid = (
                (
                    await self.session.execute(
                        _select(OrganisatieEenheid)
                        .where(
                            OrganisatieEenheid.naam.ilike(uitvoering),
                            OrganisatieEenheid.geldig_tot.is_(None),
                        )
                        .limit(1)
                    )
                )
                .scalars()
                .first()
            )

        # 3. Nieuwe rij onder Marktpartijen en overige
        if eenheid is None:
            parent = (
                (
                    await self.session.execute(
                        _select(OrganisatieEenheid).where(
                            OrganisatieEenheid.bron == "synthetisch",
                            OrganisatieEenheid.naam == "Marktpartijen en overige",
                        )
                    )
                )
                .scalars()
                .first()
            )
            eenheid = OrganisatieEenheid(
                naam=uitvoering,
                type="overig",
                bron="fcc_import",
                parent_id=parent.id if parent else None,
            )
            self.session.add(eenheid)
            await self.session.flush()

        opdracht.opdrachtnemer_eenheid_id = eenheid.id

    async def pull_single(self, opdracht_id: UUID) -> bool:
        """Re-pull a single opdracht from FCC (for conflict resolution)."""
        stmt = (
            select(Opdracht)
            .where(Opdracht.id == opdracht_id)
            .options(selectinload(Opdracht.node_koppelingen))
        )
        result = await self.session.execute(stmt)
        opdracht = result.scalar_one_or_none()

        if not opdracht or not opdracht.fcc_id:
            return False

        client = await self.get_client()
        if client is None:
            return False

        entity_name = (
            await self.get_config_value("FCC_PROJECT_ENTITY") or "Portfolio_item"
        )

        async with client:
            data = await client.get_entity(entity_name, opdracht.fcc_id)

        if data is None:
            return False

        self._apply_fcc_data(opdracht, data)
        await self._resolve_opdrachtnemer(opdracht, data)
        fcc_modified = self.parse_fcc_date(data)

        opdracht.fcc_modified_at = fcc_modified
        opdracht.last_synced_at = datetime.now(UTC)
        opdracht.sync_status = SyncStatus.synced
        opdracht.fcc_raw_data = data

        log_fcc_sync(
            self.session,
            opdracht_id=opdracht.id,
            direction="inbound",
            action="updated",
            details={"fcc_id": opdracht.fcc_id, "conflict_resolved": True},
        )
        await self.session.flush()
        return True

    @staticmethod
    def parse_fcc_date(data: dict) -> datetime | None:
        """Parse Laatst_gewijzigd_op (Edm.Date) into a timezone-aware datetime."""
        raw = data.get("Laatst_gewijzigd_op")
        if not raw:
            return None
        try:
            from datetime import date as date_type

            d = date_type.fromisoformat(str(raw)[:10])
            return datetime(d.year, d.month, d.day, tzinfo=UTC)
        except (ValueError, AttributeError):
            return None
