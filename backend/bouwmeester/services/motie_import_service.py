"""Orchestration service for motie import pipeline.

Polls TK/EK APIs for new moties, extracts tags via LLM,
matches tags to existing corpus nodes, creates CorpusNode + PolitiekeInput
records, creates suggested edges, and sends notifications.
"""

import logging
import uuid
from collections import Counter
from datetime import date, datetime, timedelta

import anthropic
import httpx
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.config import get_settings
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.node_stakeholder import NodeStakeholder
from bouwmeester.models.person import Person
from bouwmeester.models.politieke_input import PolitiekeInput
from bouwmeester.models.task import Task
from bouwmeester.repositories.motie_import import (
    MotieImportRepository,
    SuggestedEdgeRepository,
)
from bouwmeester.repositories.tag import TagRepository
from bouwmeester.schema.tag import TagCreate
from bouwmeester.services.llm_service import LLMService
from bouwmeester.services.notification_service import NotificationService
from bouwmeester.services.tk_api_client import (
    EersteKamerClient,
    MotieData,
    TweedeKamerClient,
)

logger = logging.getLogger(__name__)


class MotieImportService:
    """Orchestrates the full motie import pipeline.

    Steps per motie:
    1. Idempotency check (skip if zaak_id already imported)
    2. LLM tag extraction from motie text
    3. Create any newly suggested tags
    4. Find matching corpus nodes via tag overlap
    5. LLM edge-type suggestion per matched node
    6. Create CorpusNode + PolitiekeInput for the motie
    7. Tag the new node with matched tags
    8. Create MotieImport record
    9. Create SuggestedEdge records with LLM-chosen edge types
    10. Send notifications to stakeholders of affected nodes
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()
        self.import_repo = MotieImportRepository(session)
        self.edge_repo = SuggestedEdgeRepository(session)
        self.tag_repo = TagRepository(session)
        self.notification_service = NotificationService(session)

    async def poll_and_import(self) -> int:
        """Poll TK and EK APIs for new moties and import them.

        Returns the number of moties successfully imported.
        """
        imported_count = 0

        # Poll Tweede Kamer
        tk_client = TweedeKamerClient(
            base_url=self.settings.TK_API_BASE_URL,
            session=self.session,
        )
        try:
            async with tk_client:
                tk_moties = await tk_client.fetch_moties(
                    since=None, limit=self.settings.TK_IMPORT_LIMIT
                )
            logger.info(f"Fetched {len(tk_moties)} moties from Tweede Kamer")
        except httpx.HTTPError:
            logger.exception("Error fetching moties from Tweede Kamer")
            tk_moties = []

        # Poll Eerste Kamer
        ek_client = EersteKamerClient(
            base_url=self.settings.EK_API_BASE_URL,
            session=self.session,
        )
        try:
            async with ek_client:
                ek_moties = await ek_client.fetch_moties(since=None)
            logger.info(f"Fetched {len(ek_moties)} moties from Eerste Kamer")
        except httpx.HTTPError:
            logger.exception("Error fetching moties from Eerste Kamer")
            ek_moties = []

        all_moties = tk_moties + ek_moties

        for motie in all_moties:
            try:
                result = await self._process_motie(motie)
                if result:
                    imported_count += 1
            except (
                httpx.HTTPError,
                anthropic.APIError,
                SQLAlchemyError,
                ValueError,
                KeyError,
            ):
                logger.exception(f"Error processing motie {motie.zaak_id}")

        return imported_count

    async def _process_motie(self, motie: MotieData) -> bool:
        """Process a single motie through the import pipeline.

        Returns True if the motie was imported, False if skipped or rejected.
        """
        # Step 1: Idempotency check
        existing = await self.import_repo.get_by_zaak_id(motie.zaak_id)
        if existing:
            logger.debug(f"Skipping motie {motie.zaak_nummer}: already imported")
            return False

        # Step 2: LLM tag extraction
        all_tags = await self.tag_repo.get_all()
        tag_names = [t.name for t in all_tags]

        llm_service = LLMService()
        try:
            extraction = await llm_service.extract_tags(
                titel=motie.titel,
                onderwerp=motie.onderwerp,
                document_tekst=motie.document_tekst,
                bestaande_tags=tag_names,
            )
        except (anthropic.APIError, ValueError):
            logger.exception(f"LLM extraction failed for motie {motie.zaak_nummer}")
            extraction = None

        matched_tag_names = extraction.matched_tags if extraction else []
        samenvatting = extraction.samenvatting if extraction else None

        # Step 3: Find matching corpus nodes via tag overlap
        matched_nodes = await self._find_matching_nodes(matched_tag_names)

        if not matched_nodes:
            # No matches - create import record as out_of_scope
            await self.import_repo.create(
                zaak_id=motie.zaak_id,
                zaak_nummer=motie.zaak_nummer,
                titel=motie.titel,
                onderwerp=motie.onderwerp,
                bron=motie.bron,
                datum=motie.datum.date() if motie.datum else None,
                status="out_of_scope",
                indieners=motie.indieners,
                document_tekst=motie.document_tekst,
                document_url=motie.document_url,
                llm_samenvatting=samenvatting,
                matched_tags=matched_tag_names,
            )
            logger.info(
                f"Motie {motie.zaak_nummer} out_of_scope: no matching corpus nodes"
            )
            return False

        # Step 4: Create any newly suggested tags (only for imported moties)
        if extraction:
            for new_tag_name in extraction.suggested_new_tags:
                existing_tag = await self.tag_repo.get_by_name(new_tag_name)
                if not existing_tag:
                    try:
                        await self.tag_repo.create(TagCreate(name=new_tag_name))
                    except SQLAlchemyError:
                        logger.exception(
                            f"Error creating suggested tag '{new_tag_name}'"
                        )

        # Step 5: Create CorpusNode + PolitiekeInput
        node = CorpusNode(
            title=motie.onderwerp,
            node_type="politieke_input",
            description=samenvatting or f"Zaak: {motie.titel}",
            status="actief",
        )
        self.session.add(node)
        await self.session.flush()

        # Convert datetime to date for PolitiekeInput
        motie_datum = motie.datum.date() if motie.datum else None

        pi = PolitiekeInput(
            id=node.id,
            type="motie",
            referentie=motie.zaak_nummer,
            datum=motie_datum,
            status="aangenomen",
        )
        self.session.add(pi)
        await self.session.flush()

        # Step 6: Link indieners as stakeholders
        await self._link_indieners(node.id, motie.indieners, motie.bron)

        # Step 7: Tag the new node with matched tags (batch lookup)
        matched_tag_map = await self.tag_repo.get_by_names(matched_tag_names)
        for tag_name, tag in matched_tag_map.items():
            try:
                await self.tag_repo.add_tag_to_node(node.id, tag.id)
            except SQLAlchemyError:
                logger.exception(f"Error tagging node {node.id} with tag '{tag_name}'")

        # Step 8: Create MotieImport record
        motie_import = await self.import_repo.create(
            zaak_id=motie.zaak_id,
            zaak_nummer=motie.zaak_nummer,
            titel=motie.titel,
            onderwerp=motie.onderwerp,
            bron=motie.bron,
            datum=motie_datum,
            status="imported",
            corpus_node_id=node.id,
            indieners=motie.indieners,
            document_tekst=motie.document_tekst,
            document_url=motie.document_url,
            llm_samenvatting=samenvatting,
            matched_tags=matched_tag_names,
            imported_at=datetime.utcnow(),
        )

        # Step 8: Create SuggestedEdge records for matching nodes
        affected_nodes: list[CorpusNode] = []
        for match in matched_nodes:
            target_node = match["node"]
            confidence = match["confidence"]
            reason = match["reason"]

            try:
                await self.edge_repo.create(
                    motie_import_id=motie_import.id,
                    target_node_id=target_node.id,
                    edge_type_id="adresseert",
                    confidence=confidence,
                    reason=reason,
                    status="pending",
                )
                affected_nodes.append(target_node)
            except SQLAlchemyError:
                logger.exception(
                    f"Error creating suggested edge to node {target_node.id}"
                )

        # Step 10: Send notifications
        if affected_nodes:
            try:
                await self.notification_service.notify_motie_imported(
                    node, affected_nodes
                )
            except (SQLAlchemyError, ValueError):
                logger.exception("Error sending motie import notifications")

        # Step 11: Create review task
        try:
            review_unit_id = await self._determine_review_unit(affected_nodes)
            task_title = f"Beoordeel motie: {motie.onderwerp}"
            if len(task_title) > 200:
                task_title = task_title[:197] + "..."

            description_parts = [
                f"Zaak: {motie.zaak_nummer}",
                f"Bron: {motie.bron}",
            ]
            if samenvatting:
                description_parts.append(f"\n{samenvatting}")
            description_parts.append(
                f"\n{len(affected_nodes)} gerelateerde beleidsdossiers gevonden."
            )

            # Deadline: 10 business days from now
            deadline = self._business_days_from_now(10)

            task = Task(
                node_id=node.id,
                title=task_title,
                description="\n".join(description_parts),
                priority="hoog",
                status="open",
                deadline=deadline,
                organisatie_eenheid_id=review_unit_id,
                assignee_id=None,
                motie_import_id=motie_import.id,
            )
            self.session.add(task)
            await self.session.flush()
            logger.info(
                f"Created review task for motie {motie.zaak_nummer} "
                f"(unit: {review_unit_id or 'none'})"
            )
        except SQLAlchemyError:
            logger.exception(
                f"Error creating review task for motie {motie.zaak_nummer}"
            )

        logger.info(
            f"Motie {motie.zaak_nummer} imported with {len(affected_nodes)} "
            f"suggested edges"
        )
        return True

    async def _determine_review_unit(
        self, affected_nodes: list[CorpusNode]
    ) -> uuid.UUID | None:
        """Determine the best organisatie_eenheid for a motie review task.

        Looks at stakeholders (especially eigenaar role) of matched nodes and
        picks the most common organisatie_eenheid.
        """
        if not affected_nodes:
            return None

        node_ids = [n.id for n in affected_nodes]
        stmt = select(NodeStakeholder).where(
            NodeStakeholder.node_id.in_(node_ids),
            NodeStakeholder.rol == "eigenaar",
        )
        result = await self.session.execute(stmt)
        stakeholders = result.scalars().all()

        if not stakeholders:
            return None

        # Batch-query organisatie_eenheid_id for all stakeholder persons
        person_ids = [sh.person_id for sh in stakeholders]
        person_stmt = select(Person.organisatie_eenheid_id).where(
            Person.id.in_(person_ids),
            Person.organisatie_eenheid_id.isnot(None),
        )
        person_result = await self.session.execute(person_stmt)
        unit_ids: list[uuid.UUID] = list(person_result.scalars().all())

        if not unit_ids:
            return None

        # Return the most common unit
        counter = Counter(unit_ids)
        most_common_id, _ = counter.most_common(1)[0]
        return most_common_id

    @staticmethod
    def _business_days_from_now(days: int) -> date:
        """Calculate a date N business days from today."""
        current = date.today()
        added = 0
        while added < days:
            current += timedelta(days=1)
            if current.weekday() < 5:  # Monday=0 .. Friday=4
                added += 1
        return current

    async def _find_matching_nodes(self, tag_names: list[str]) -> list[dict]:
        """Find corpus nodes that share tags with the motie.

        Uses tag overlap scoring to rank matches:
        - Exact tag match contributes 1.0 per tag
        - Parent tag match contributes 0.7 per tag

        Confidence is normalized to [0, 1] based on the number of motie tags.
        Returns the top 10 matches sorted by confidence descending.

        Args:
            tag_names: List of tag names extracted from the motie.

        Returns:
            List of dicts with 'node' (CorpusNode), 'confidence' (float),
            'reason' (str), and 'tag_names' (list[str]) keys.
        """
        if not tag_names:
            return []

        # Resolve tag names to Tag objects (batch query)
        tag_objects = await self.tag_repo.get_by_names(tag_names)

        if not tag_objects:
            return []

        # Batch-load all tag-node mappings upfront (fixes N+1)
        all_tag_ids = set()
        for tag in tag_objects.values():
            all_tag_ids.add(tag.id)
            if tag.parent_id:
                all_tag_ids.add(tag.parent_id)

        from bouwmeester.models.tag import NodeTag

        tag_node_stmt = select(NodeTag.tag_id, NodeTag.node_id).where(
            NodeTag.tag_id.in_(all_tag_ids)
        )
        tag_node_result = await self.session.execute(tag_node_stmt)
        tag_to_nodes: dict[uuid.UUID, list[uuid.UUID]] = {}
        all_node_ids: set[uuid.UUID] = set()
        for tag_id, node_id in tag_node_result.all():
            tag_to_nodes.setdefault(tag_id, []).append(node_id)
            all_node_ids.add(node_id)

        # Batch-load all candidate nodes (fixes N+1)
        nodes_by_id: dict[uuid.UUID, CorpusNode] = {}
        if all_node_ids:
            nodes_stmt = select(CorpusNode).where(
                CorpusNode.id.in_(all_node_ids),
                CorpusNode.node_type != "politieke_input",
            )
            nodes_result = await self.session.execute(nodes_stmt)
            for node in nodes_result.scalars().all():
                nodes_by_id[node.id] = node

        # Score nodes by tag overlap
        # node_id -> {node, score, reasons, tag_names}
        node_scores: dict[str, dict] = {}

        for tag_name, tag in tag_objects.items():
            # Exact match: find nodes with this exact tag
            for node_id in tag_to_nodes.get(tag.id, []):
                nid = str(node_id)
                if nid not in node_scores and node_id in nodes_by_id:
                    node_scores[nid] = {
                        "node": nodes_by_id[node_id],
                        "score": 0.0,
                        "reasons": [],
                        "tag_names": [],
                    }
                if nid in node_scores:
                    node_scores[nid]["score"] += 1.0
                    node_scores[nid]["reasons"].append(f"tag '{tag_name}'")
                    if tag_name not in node_scores[nid]["tag_names"]:
                        node_scores[nid]["tag_names"].append(tag_name)

            # Parent tag match: if this tag has a parent, find nodes tagged
            # with the parent (broader category match)
            if tag.parent_id:
                for node_id in tag_to_nodes.get(tag.parent_id, []):
                    nid = str(node_id)
                    if nid not in node_scores and node_id in nodes_by_id:
                        node_scores[nid] = {
                            "node": nodes_by_id[node_id],
                            "score": 0.0,
                            "reasons": [],
                            "tag_names": [],
                        }
                    if nid in node_scores:
                        node_scores[nid]["score"] += 0.7
                        node_scores[nid]["reasons"].append(
                            f"parent tag van '{tag_name}'"
                        )

        # Normalize scores to [0, 1] confidence and build result list
        min_confidence = 0.5
        results = []
        max_possible = len(tag_objects)

        for data in node_scores.values():
            confidence = min(data["score"] / max(max_possible, 1), 1.0)
            if confidence < min_confidence:
                continue
            results.append(
                {
                    "node": data["node"],
                    "confidence": confidence,
                    "reason": "Gedeelde tags: " + ", ".join(data["tag_names"]),
                    "tag_names": data["tag_names"],
                }
            )

        # Sort by confidence descending, take top 10
        results.sort(key=lambda x: x["confidence"], reverse=True)
        return results[:10]

    async def _link_indieners(
        self, node_id: uuid.UUID, indieners: list[str], bron: str
    ) -> None:
        """Find or create Person records for indieners and link as stakeholders."""
        kamer = "Tweede Kamer" if bron == "tweede_kamer" else "Eerste Kamer"
        for naam in indieners:
            naam = naam.strip()
            if not naam or naam == "TK" or naam == "EK":
                continue  # Skip chamber abbreviations

            try:
                person = await self._find_or_create_person(naam, kamer)
                stakeholder = NodeStakeholder(
                    node_id=node_id,
                    person_id=person.id,
                    rol="indiener",
                )
                self.session.add(stakeholder)
            except SQLAlchemyError:
                logger.exception(f"Error linking indiener '{naam}' to node")

        await self.session.flush()

    async def _find_or_create_person(self, naam: str, kamer: str) -> Person:
        """Find a person by name+functie or create a new external person record."""
        functie = f"Kamerlid {kamer}"
        stmt = select(Person).where(
            Person.naam == naam,
            Person.functie == functie,
        )
        result = await self.session.execute(stmt)
        person = result.scalar_one_or_none()

        if person:
            return person

        person = Person(
            naam=naam,
            functie=functie,
            rol="extern",
            is_active=True,
        )
        self.session.add(person)
        await self.session.flush()
        return person
