"""Orchestration service for parliamentary item import pipeline.

Polls TK/EK APIs for new parliamentary items, extracts tags via LLM,
matches tags to existing corpus nodes, creates CorpusNode + PolitiekeInput
records, creates suggested edges, and sends notifications.
"""

import logging
import uuid
from collections import Counter
from datetime import date, datetime, timedelta

import anthropic
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.config import get_settings
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.node_stakeholder import NodeStakeholder
from bouwmeester.models.person import Person
from bouwmeester.models.politieke_input import PolitiekeInput
from bouwmeester.models.task import Task
from bouwmeester.repositories.parlementair_item import (
    ParlementairItemRepository,
    SuggestedEdgeRepository,
)
from bouwmeester.repositories.tag import TagRepository
from bouwmeester.schema.tag import TagCreate
from bouwmeester.services.import_strategies.base import FetchedItem, ImportStrategy
from bouwmeester.services.import_strategies.registry import get_strategy
from bouwmeester.services.llm_service import LLMService
from bouwmeester.services.notification_service import NotificationService
from bouwmeester.services.tk_api_client import EersteKamerClient, TweedeKamerClient

logger = logging.getLogger(__name__)


class ParlementairImportService:
    """Orchestrates the full parliamentary item import pipeline.

    Steps per item:
    1. Idempotency check (skip if zaak_id already imported)
    2. LLM tag extraction from item text (if strategy requires it)
    3. Create any newly suggested tags
    4. Find matching corpus nodes via tag overlap
    5. Create CorpusNode + PolitiekeInput for the item
    6. Tag the new node with matched tags
    7. Create ParlementairItem record
    8. Create SuggestedEdge records
    9. Send notifications to stakeholders of affected nodes
    10. Create review task
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()
        self.import_repo = ParlementairItemRepository(session)
        self.edge_repo = SuggestedEdgeRepository(session)
        self.tag_repo = TagRepository(session)
        self.notification_service = NotificationService(session)

    async def poll_and_import(
        self,
        item_types: list[str] | None = None,
    ) -> int:
        """Poll TK and EK APIs for new items and import them.

        Args:
            item_types: List of item types to import. If None, uses
                configured ENABLED_IMPORT_TYPES.

        Returns the number of items successfully imported.
        """
        types_to_import = item_types or self.settings.ENABLED_IMPORT_TYPES
        imported_count = 0

        for item_type in types_to_import:
            try:
                strategy = get_strategy(item_type)
            except ValueError:
                logger.warning(f"Unknown import type: {item_type}, skipping")
                continue

            count = await self._import_type(strategy)
            imported_count += count

        return imported_count

    async def _import_type(self, strategy: ImportStrategy) -> int:
        """Import all items for a single strategy/type."""
        imported_count = 0

        # Poll Tweede Kamer
        tk_client = TweedeKamerClient(
            base_url=self.settings.TK_API_BASE_URL,
            session=self.session,
        )
        try:
            async with tk_client:
                tk_items = await strategy.fetch_items(
                    client=tk_client,
                    since=None,
                    limit=self.settings.TK_IMPORT_LIMIT,
                )
            logger.info(
                f"Fetched {len(tk_items)} {strategy.item_type} items from Tweede Kamer"
            )
        except Exception:
            logger.exception(f"Error fetching {strategy.item_type} from Tweede Kamer")
            tk_items = []

        # Poll Eerste Kamer (only if strategy supports it)
        ek_items: list[FetchedItem] = []
        if strategy.supports_ek:
            ek_client = EersteKamerClient(
                base_url=self.settings.EK_API_BASE_URL,
                session=self.session,
            )
            try:
                async with ek_client:
                    ek_items = await strategy.fetch_items(
                        client=ek_client,
                        since=None,
                        limit=self.settings.TK_IMPORT_LIMIT,
                    )
                logger.info(
                    f"Fetched {len(ek_items)} {strategy.item_type} "
                    f"items from Eerste Kamer"
                )
            except Exception:
                logger.exception(
                    f"Error fetching {strategy.item_type} from Eerste Kamer"
                )
                ek_items = []

        all_items = tk_items + ek_items

        for item in all_items:
            try:
                result = await self._process_item(item, strategy)
                if result:
                    imported_count += 1
            except Exception:
                logger.exception(
                    f"Error processing {strategy.item_type} {item.zaak_id}"
                )
                # Rollback so the session is usable for subsequent items
                await self.session.rollback()

        return imported_count

    async def _process_item(
        self,
        item: FetchedItem,
        strategy: ImportStrategy,
    ) -> bool:
        """Process a single item through the import pipeline.

        Returns True if the item was imported, False if skipped.
        """
        # Step 1: Idempotency check
        existing = await self.import_repo.get_by_zaak_id(item.zaak_id)
        if existing:
            logger.debug(
                f"Skipping {strategy.item_type} {item.zaak_nummer}: already imported"
            )
            return False

        # Step 2: LLM tag extraction (if strategy requires it)
        matched_tag_names: list[str] = []
        samenvatting: str | None = None

        if strategy.requires_llm:
            all_tags = await self.tag_repo.get_all()
            tag_names = [t.name for t in all_tags]

            llm_service = LLMService()
            try:
                extraction = await llm_service.extract_tags(
                    titel=item.titel,
                    onderwerp=item.onderwerp,
                    document_tekst=item.document_tekst,
                    bestaande_tags=tag_names,
                    context_hint=strategy.context_hint(),
                )
            except (anthropic.APIError, ValueError):
                logger.exception(
                    f"LLM extraction failed for {strategy.item_type} {item.zaak_nummer}"
                )
                extraction = None

            matched_tag_names = extraction.matched_tags if extraction else []
            samenvatting = extraction.samenvatting if extraction else None

        # Step 3: Find matching corpus nodes via tag overlap
        matched_nodes = await self._find_matching_nodes(matched_tag_names)

        if not matched_nodes and not strategy.always_import:
            # No matches and not pre-filtered — mark as out_of_scope
            await self.import_repo.create(
                type=strategy.item_type,
                zaak_id=item.zaak_id,
                zaak_nummer=item.zaak_nummer,
                titel=item.titel,
                onderwerp=item.onderwerp,
                bron=item.bron,
                datum=item.datum,
                status="out_of_scope",
                indieners=item.indieners,
                document_tekst=item.document_tekst,
                document_url=item.document_url,
                llm_samenvatting=samenvatting,
                matched_tags=matched_tag_names,
                deadline=item.deadline,
                ministerie=item.ministerie,
                extra_data=item.extra_data,
            )
            logger.info(
                f"{strategy.item_type} {item.zaak_nummer} out_of_scope: "
                f"no matching corpus nodes"
            )
            return False

        # Step 4: Create any newly suggested tags
        if strategy.requires_llm and extraction:
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
            title=item.onderwerp,
            node_type="politieke_input",
            description=samenvatting or f"Zaak: {item.titel}",
            status="actief",
        )
        self.session.add(node)
        await self.session.flush()

        pi = PolitiekeInput(
            id=node.id,
            type=strategy.politieke_input_type,
            referentie=item.zaak_nummer,
            datum=item.datum,
            status=strategy.politieke_input_status(item),
        )
        self.session.add(pi)
        await self.session.flush()

        # Step 6: Link indieners as stakeholders
        await self._link_indieners(node.id, item.indieners, item.bron)

        # Step 7: Tag the new node with matched tags (batch lookup)
        matched_tag_map = await self.tag_repo.get_by_names(matched_tag_names)
        for tag_name, tag in matched_tag_map.items():
            try:
                await self.tag_repo.add_tag_to_node(node.id, tag.id)
            except SQLAlchemyError:
                logger.exception(f"Error tagging node {node.id} with tag '{tag_name}'")

        # Step 8: Create ParlementairItem record
        parlementair_item = await self.import_repo.create(
            type=strategy.item_type,
            zaak_id=item.zaak_id,
            zaak_nummer=item.zaak_nummer,
            titel=item.titel,
            onderwerp=item.onderwerp,
            bron=item.bron,
            datum=item.datum,
            status="imported",
            corpus_node_id=node.id,
            indieners=item.indieners,
            document_tekst=item.document_tekst,
            document_url=item.document_url,
            llm_samenvatting=samenvatting,
            matched_tags=matched_tag_names,
            imported_at=datetime.utcnow(),
            deadline=item.deadline,
            ministerie=item.ministerie,
            extra_data=item.extra_data,
        )

        # Step 9: Create SuggestedEdge records for matching nodes
        affected_nodes: list[CorpusNode] = []
        for match in matched_nodes:
            target_node = match["node"]
            confidence = match["confidence"]
            reason = match["reason"]

            try:
                await self.edge_repo.create(
                    parlementair_item_id=parlementair_item.id,
                    target_node_id=target_node.id,
                    edge_type_id=strategy.default_edge_type(),
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
                await self.notification_service.notify_parlementair_item_imported(
                    node,
                    affected_nodes,
                    item_type=strategy.item_type,
                )
            except (SQLAlchemyError, ValueError):
                logger.exception("Error sending import notifications")

        # Step 11: Create review task
        try:
            review_unit_id = await self._determine_review_unit(affected_nodes)
            task_title = strategy.task_title(item)
            if len(task_title) > 200:
                task_title = task_title[:197] + "..."

            description_parts = [
                f"Zaak: {item.zaak_nummer}",
                f"Bron: {item.bron}",
            ]
            if samenvatting:
                description_parts.append(f"\n{samenvatting}")
            description_parts.append(
                f"\n{len(affected_nodes)} gerelateerde beleidsdossiers gevonden."
            )

            # Use strategy deadline or default to 10 business days
            deadline = strategy.calculate_deadline(item)
            if deadline is None:
                deadline = self._business_days_from_now(10)

            task = Task(
                node_id=node.id,
                title=task_title,
                description="\n".join(description_parts),
                priority=strategy.task_priority(item),
                status="open",
                deadline=deadline,
                organisatie_eenheid_id=review_unit_id,
                assignee_id=None,
                parlementair_item_id=parlementair_item.id,
            )
            self.session.add(task)
            await self.session.flush()
            logger.info(
                f"Created review task for {strategy.item_type} {item.zaak_nummer} "
                f"(unit: {review_unit_id or 'none'})"
            )
        except SQLAlchemyError:
            logger.exception(
                f"Error creating review task for {strategy.item_type} "
                f"{item.zaak_nummer}"
            )

        logger.info(
            f"{strategy.item_type} {item.zaak_nummer} imported with "
            f"{len(affected_nodes)} suggested edges"
        )
        return True

    async def _determine_review_unit(
        self,
        affected_nodes: list[CorpusNode],
    ) -> uuid.UUID | None:
        """Determine the best organisatie_eenheid for a review task."""
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

        person_ids = [sh.person_id for sh in stakeholders]
        person_stmt = select(Person.organisatie_eenheid_id).where(
            Person.id.in_(person_ids),
            Person.organisatie_eenheid_id.isnot(None),
        )
        person_result = await self.session.execute(person_stmt)
        unit_ids: list[uuid.UUID] = list(person_result.scalars().all())

        if not unit_ids:
            return None

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
            if current.weekday() < 5:
                added += 1
        return current

    async def _find_matching_nodes(self, tag_names: list[str]) -> list[dict]:
        """Find corpus nodes that share tags with the item."""
        if not tag_names:
            return []

        tag_objects = await self.tag_repo.get_by_names(tag_names)

        if not tag_objects:
            return []

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

        nodes_by_id: dict[uuid.UUID, CorpusNode] = {}
        if all_node_ids:
            nodes_stmt = select(CorpusNode).where(
                CorpusNode.id.in_(all_node_ids),
                CorpusNode.node_type != "politieke_input",
            )
            nodes_result = await self.session.execute(nodes_stmt)
            for node in nodes_result.scalars().all():
                nodes_by_id[node.id] = node

        node_scores: dict[str, dict] = {}

        for tag_name, tag in tag_objects.items():
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

        results.sort(key=lambda x: x["confidence"], reverse=True)
        return results[:10]

    async def _link_indieners(
        self,
        node_id: uuid.UUID,
        indieners: list[str],
        bron: str,
    ) -> None:
        """Find or create Person records for indieners and link as stakeholders."""
        kamer = "Tweede Kamer" if bron == "tweede_kamer" else "Eerste Kamer"
        for naam in indieners:
            naam = naam.strip()
            if not naam or naam == "TK" or naam == "EK":
                continue

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
