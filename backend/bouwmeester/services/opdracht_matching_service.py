"""Service for LLM-based matching of persons/eenheden to opdrachten."""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bouwmeester.models.opdracht import Opdracht
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.repositories.opdracht import OpdrachtRepository
from bouwmeester.services.llm.base import DataSensitivity

logger = logging.getLogger(__name__)


class OpdrachtMatchingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _fetch_candidates(
        self,
    ) -> tuple[list[Person], list[dict], list[OrganisatieEenheid], list[dict]]:
        """Fetch all candidate persons and eenheden (once, for reuse)."""
        person_stmt = (
            select(Person)
            .where(Person.is_agent.is_(False))
            .options(selectinload(Person.organisatie_eenheden))
        )
        person_result = await self.db.execute(person_stmt)
        all_persons = list(person_result.scalars().all())

        kandidaat_personen = []
        for p in all_persons:
            eenheid_naam = ""
            if p.organisatie_eenheden:
                eenheid_naam = (
                    p.organisatie_eenheden[0].naam
                    if hasattr(p.organisatie_eenheden[0], "naam")
                    else ""
                )
            kandidaat_personen.append(
                {
                    "id": str(p.id),
                    "naam": p.naam,
                    "functie": p.functie or "",
                    "eenheid": eenheid_naam,
                }
            )

        eenheid_stmt = select(OrganisatieEenheid).options(
            selectinload(OrganisatieEenheid.parent_records)
        )
        eenheid_result = await self.db.execute(eenheid_stmt)
        all_eenheden = list(eenheid_result.scalars().all())

        kandidaat_eenheden = []
        for e in all_eenheden:
            kandidaat_eenheden.append(
                {
                    "id": str(e.id),
                    "naam": e.naam,
                    "type": e.type or "",
                }
            )

        return all_persons, kandidaat_personen, all_eenheden, kandidaat_eenheden

    async def suggest_and_link(
        self,
        opdracht: Opdracht,
        all_persons: list[Person] | None = None,
        kandidaat_personen: list[dict] | None = None,
        all_eenheden: list[OrganisatieEenheid] | None = None,
        kandidaat_eenheden: list[dict] | None = None,
    ) -> list[ResourcePermission]:
        """Match persons/eenheden to an opdracht via LLM and create links.

        Accepts pre-fetched candidates to avoid redundant queries in bulk mode.
        """
        from bouwmeester.services.llm.factory import get_llm_service_for

        llm = await get_llm_service_for(DataSensitivity.CONFIDENTIAL, self.db)
        if llm is None:
            logger.warning("Geen LLM-provider beschikbaar voor CONFIDENTIAL data")
            return []

        # Gather context from opdracht
        fcc_contact_fields: dict[str, str] = {}
        fcc_afdeling: str | None = None
        fcc_raw = getattr(opdracht, "fcc_raw_data", None)
        if fcc_raw and isinstance(fcc_raw, dict):
            for key in (
                "Contact_opdrachtnemer",
                "Contactpersoon_opdrachtgever",
                "Eigenaar",
            ):
                val = fcc_raw.get(key)
                if val and str(val).strip() and str(val).strip().lower() != "ntb":
                    fcc_contact_fields[key] = str(val).strip()
            fcc_afdeling = getattr(opdracht, "fcc_afdeling", None) or fcc_raw.get(
                "Afdeling_PDD"
            )

        # Fetch candidates if not provided (single-opdracht mode)
        if all_persons is None or kandidaat_personen is None:
            (
                all_persons,
                kandidaat_personen,
                all_eenheden,
                kandidaat_eenheden,
            ) = await self._fetch_candidates()

        # Skip if nothing to match against
        if not kandidaat_personen and not kandidaat_eenheden:
            return []

        # Call LLM
        match_result = await llm.match_opdracht_contacts(
            opdracht_titel=opdracht.titel,
            opdracht_beschrijving=opdracht.beschrijving,
            fcc_contact_fields=fcc_contact_fields,
            fcc_afdeling=fcc_afdeling,
            kandidaat_personen=kandidaat_personen,
            kandidaat_eenheden=kandidaat_eenheden or [],
        )

        if not match_result.matches:
            return []

        # Fetch existing links to avoid duplicates
        existing_stmt = select(ResourcePermission).where(
            ResourcePermission.resource_type == "opdracht",
            ResourcePermission.resource_id == opdracht.id,
        )
        existing_result = await self.db.execute(existing_stmt)
        existing_rps = list(existing_result.scalars().all())

        existing_person_ids = {
            rp.person_id for rp in existing_rps if rp.person_id is not None
        }
        existing_eenheid_ids = {
            rp.organisatie_eenheid_id
            for rp in existing_rps
            if rp.organisatie_eenheid_id is not None
        }

        # Valid IDs for quick lookup
        valid_person_ids = {p.id for p in all_persons}
        valid_eenheid_ids = {e.id for e in (all_eenheden or [])}

        repo = OpdrachtRepository(self.db)
        created: list[ResourcePermission] = []

        for match in match_result.matches:
            try:
                target_id = UUID(match.target_id)
            except ValueError:
                continue

            if match.link_type == "person":
                if target_id in existing_person_ids:
                    continue
                if target_id not in valid_person_ids:
                    continue
                rp = await repo.add_member(
                    opdracht_id=opdracht.id,
                    person_id=target_id,
                    rol=match.suggested_rol,
                    source="ai",
                    ai_confidence=match.confidence,
                    ai_reason=match.reason,
                )
                existing_person_ids.add(target_id)
                created.append(rp)

            elif match.link_type == "organisatie_eenheid":
                if target_id in existing_eenheid_ids:
                    continue
                if target_id not in valid_eenheid_ids:
                    continue
                rp = await repo.add_eenheid(
                    opdracht_id=opdracht.id,
                    eenheid_id=target_id,
                    rol=match.suggested_rol,
                    source="ai",
                    ai_confidence=match.confidence,
                    ai_reason=match.reason,
                )
                existing_eenheid_ids.add(target_id)
                created.append(rp)

        logger.info(
            "Opdracht %s: %d contacten gematcht via LLM",
            opdracht.id,
            len(created),
        )
        return created

    async def match_all_unlinked(self) -> dict[str, int]:
        """Match contacts for all opdrachten that have no members yet.

        Returns {"matched": N, "skipped": M, "total": T}.
        """
        from sqlalchemy import and_, exists

        has_link = exists().where(
            and_(
                ResourcePermission.resource_type == "opdracht",
                ResourcePermission.resource_id == Opdracht.id,
            )
        )
        stmt = select(Opdracht).where(~has_link).order_by(Opdracht.created_at)
        result = await self.db.execute(stmt)
        opdrachten = list(result.scalars().all())

        if not opdrachten:
            return {"matched": 0, "skipped": 0, "total": 0}

        # Fetch candidates once for all opdrachten
        (
            all_persons,
            kandidaat_personen,
            all_eenheden,
            kandidaat_eenheden,
        ) = await self._fetch_candidates()

        matched = 0
        skipped = 0
        for opdracht in opdrachten:
            try:
                created = await self.suggest_and_link(
                    opdracht,
                    all_persons=all_persons,
                    kandidaat_personen=kandidaat_personen,
                    all_eenheden=all_eenheden,
                    kandidaat_eenheden=kandidaat_eenheden,
                )
                if created:
                    matched += 1
                else:
                    skipped += 1
            except Exception:
                logger.exception("Fout bij matchen opdracht %s", opdracht.id)
                skipped += 1

        logger.info(
            "Bulk match: %d gematcht, %d overgeslagen van %d totaal",
            matched,
            skipped,
            len(opdrachten),
        )
        return {
            "matched": matched,
            "skipped": skipped,
            "total": len(opdrachten),
        }
