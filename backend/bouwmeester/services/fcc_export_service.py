"""FCC export service - pushes Opdrachten to Fortes Change Cloud."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bouwmeester.models.opdracht import Opdracht
from bouwmeester.schema.fcc import SyncDirection, SyncStatus
from bouwmeester.services.fcc_sync_log_helper import log_fcc_sync

logger = logging.getLogger(__name__)


class FccExportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def push_pending(self) -> int:
        """Push all opdrachten with sync_status='pending_push' to FCC."""
        stmt = (
            select(Opdracht)
            .where(Opdracht.sync_status == SyncStatus.pending_push)
            .options(selectinload(Opdracht.node_koppelingen))
        )
        result = await self.session.execute(stmt)
        opdrachten = list(result.scalars().all())

        count = 0
        for opdracht in opdrachten:
            try:
                success = await self._push_opdracht(opdracht)
                if success:
                    count += 1
            except Exception:
                logger.exception("Error pushing opdracht %s to FCC", opdracht.id)
                opdracht.sync_status = SyncStatus.error
                log_fcc_sync(
                    self.session,
                    opdracht_id=opdracht.id,
                    direction="outbound",
                    action="error",
                    error_message=f"Push failed for {opdracht.id}",
                )
                await self.session.flush()

        logger.info("FCC export: %d opdrachten pushed", count)
        return count

    async def push_single(self, opdracht_id: UUID, *, force: bool = False) -> bool:
        """Push a single opdracht to FCC."""
        stmt = (
            select(Opdracht)
            .where(Opdracht.id == opdracht_id)
            .options(selectinload(Opdracht.node_koppelingen))
        )
        result = await self.session.execute(stmt)
        opdracht = result.scalar_one_or_none()

        if opdracht is None:
            return False

        return await self._push_opdracht(opdracht, force=force)

    async def _push_opdracht(self, opdracht: Opdracht, *, force: bool = False) -> bool:
        """Push a single opdracht to FCC via OData."""
        from bouwmeester.services.fcc_import_service import FccImportService

        import_service = FccImportService(self.session)
        client = await import_service.get_client()
        if client is None:
            return False

        entity_name = (
            await import_service.get_config_value("FCC_PROJECT_ENTITY")
            or "Portfolio_item"
        )

        fcc_data = self._map_opdracht_to_fcc(opdracht)

        async with client:
            if opdracht.fcc_id:
                if not force:
                    # Check for conflict: fetch current FCC version
                    current = await client.get_entity(entity_name, opdracht.fcc_id)
                    if current:
                        fcc_modified = FccImportService.parse_fcc_date(current)

                        if (
                            fcc_modified
                            and opdracht.fcc_modified_at
                            and fcc_modified > opdracht.fcc_modified_at
                        ):
                            # FCC was modified after our last sync - conflict
                            opdracht.sync_status = SyncStatus.conflict
                            opdracht.fcc_raw_data = current
                            log_fcc_sync(
                                self.session,
                                opdracht_id=opdracht.id,
                                direction="outbound",
                                action="conflict",
                                details={
                                    "fcc_id": opdracht.fcc_id,
                                    "reason": "FCC version is newer",
                                    "fcc_modified": str(fcc_modified),
                                    "our_modified": str(opdracht.fcc_modified_at),
                                },
                            )
                            await self.session.flush()
                            return False

                # Update existing FCC entity
                response = await client.update_entity(
                    entity_name, opdracht.fcc_id, fcc_data
                )
                action = "updated"
            else:
                # Create new FCC entity
                response = await client.create_entity(entity_name, fcc_data)
                opdracht.fcc_id = str(
                    response.get("Portfolio_itemKey", response.get("Id", ""))
                )
                opdracht.fcc_entity_type = entity_name
                opdracht.sync_direction = SyncDirection.outbound
                action = "created"

        # Update sync state
        now = datetime.now(UTC)
        opdracht.sync_status = SyncStatus.synced
        opdracht.last_synced_at = now
        opdracht.fcc_modified_at = now
        opdracht.fcc_raw_data = response

        log_fcc_sync(
            self.session,
            opdracht_id=opdracht.id,
            direction="outbound",
            action=action,
            details={"fcc_id": opdracht.fcc_id},
        )
        await self.session.flush()
        return True

    def _map_opdracht_to_fcc(self, opdracht: Opdracht) -> dict:
        """Map Opdracht fields to FCC Portfolio_item format."""
        data: dict = {
            "Naam": opdracht.titel,
        }
        if opdracht.beschrijving:
            data["Omschrijving"] = opdracht.beschrijving
        if opdracht.budget is not None:
            data["Budget_huidig_jaar_"] = float(opdracht.budget)
        if opdracht.gerealiseerd is not None:
            data["Gerealiseerde_kosten_huidig_jaar_"] = float(opdracht.gerealiseerd)
        if opdracht.startdatum:
            data["Startdatum_gepland_"] = opdracht.startdatum.isoformat()
        if opdracht.einddatum:
            data["Einddatum_gepland_"] = opdracht.einddatum.isoformat()
        if opdracht.referentie:
            data["Project_Nummer"] = opdracht.referentie
        if opdracht.opdrachtnemer:
            data["Uitvoeringsorganisatie"] = (
                opdracht.opdrachtnemer.afkorting or opdracht.opdrachtnemer.naam
            )
        return data
