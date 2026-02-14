"""Orchestration service for parliamentary item import pipeline.

Polls TK/EK APIs for new parliamentary items, extracts tags via LLM,
matches tags to existing corpus nodes, creates CorpusNode + PolitiekeInput
records, creates suggested edges, and sends notifications.
"""

import logging
import uuid
from collections import Counter
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.config import get_settings
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.node_stakeholder import NodeStakeholder
from bouwmeester.models.parlementair_item import ParlementairItem, SuggestedEdge
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
from bouwmeester.services.llm import get_llm_service
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
                await self.session.commit()
                if result:
                    imported_count += 1
            except Exception:
                logger.exception(
                    f"Error processing {strategy.item_type} {item.zaak_id}"
                )
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

            llm_service = await get_llm_service(self.session)
            if not llm_service:
                logger.warning("No LLM provider configured, skipping tag extraction")
                extraction = None
            else:
                try:
                    extraction = await llm_service.extract_tags(
                        titel=item.titel,
                        onderwerp=item.onderwerp,
                        document_tekst=item.document_tekst,
                        bestaande_tags=tag_names,
                        context_hint=strategy.context_hint(),
                    )
                except Exception:
                    logger.exception(
                        "LLM extraction failed for %s %s",
                        strategy.item_type,
                        item.zaak_nummer,
                    )
                    extraction = None

            if extraction is None:
                # LLM required but unavailable/failed — queue for later
                await self.import_repo.create(
                    type=strategy.item_type,
                    zaak_id=item.zaak_id,
                    zaak_nummer=item.zaak_nummer,
                    titel=item.titel,
                    onderwerp=item.onderwerp,
                    bron=item.bron,
                    datum=item.datum,
                    status="pending",
                    indieners=item.indieners,
                    document_tekst=item.document_tekst,
                    document_url=item.document_url,
                    deadline=item.deadline,
                    ministerie=item.ministerie,
                    extra_data=item.extra_data,
                )
                logger.warning(
                    "%s %s queued as pending: LLM extraction failed",
                    strategy.item_type,
                    item.zaak_nummer,
                )
                return False

            matched_tag_names = extraction.matched_tags
            samenvatting = extraction.samenvatting

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
        title = item.onderwerp
        if len(title) > 500:
            title = title[:497] + "..."
        node = CorpusNode(
            title=title,
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
            await self.create_review_task(
                parlementair_item,
                affected_nodes=affected_nodes,
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

    async def ensure_corpus_node(
        self,
        item: ParlementairItem,
    ) -> ParlementairItem:
        """Create a CorpusNode + PolitiekeInput for an item that lacks one.

        Used when reopening out-of-scope items that skipped corpus node
        creation during the original import.  If the item already has a
        corpus_node_id this is a no-op.
        """
        if item.corpus_node_id is not None:
            return item

        strategy = get_strategy(item.type)

        title = item.onderwerp
        if len(title) > 500:
            title = title[:497] + "..."
        node = CorpusNode(
            title=title,
            node_type="politieke_input",
            description=item.llm_samenvatting or f"Zaak: {item.titel}",
            status="actief",
        )
        self.session.add(node)
        await self.session.flush()

        pi = PolitiekeInput(
            id=node.id,
            type=strategy.politieke_input_type,
            referentie=item.zaak_nummer,
            datum=item.datum,
            status=strategy.politieke_input_status(
                FetchedItem(
                    zaak_id="",
                    zaak_nummer=item.zaak_nummer,
                    titel=item.titel,
                    onderwerp=item.onderwerp,
                    bron=item.bron,
                )
            ),
        )
        self.session.add(pi)
        await self.session.flush()

        # Link indieners as stakeholders
        await self._link_indieners(node.id, item.indieners or [], item.bron)

        # Tag the node with matched tags
        if item.matched_tags:
            tag_map = await self.tag_repo.get_by_names(item.matched_tags)
            for tag_name, tag in tag_map.items():
                try:
                    await self.tag_repo.add_tag_to_node(node.id, tag.id)
                except SQLAlchemyError:
                    logger.exception(f"Error tagging node {node.id} with '{tag_name}'")

        # Update the item to point to the new node
        item.corpus_node_id = node.id
        await self.session.flush()

        logger.info(
            f"Created corpus node {node.id} for reopened {item.type} {item.zaak_nummer}"
        )
        return item

    async def create_review_task(
        self,
        parlementair_item: ParlementairItem,
        affected_nodes: list[CorpusNode] | None = None,
    ) -> Task | None:
        """Create a review task for a parliamentary item.

        Used both during initial import and when reopening a rejected/
        out-of-scope item.  When *affected_nodes* is ``None`` (reopen
        case), the connected nodes are derived from existing suggested
        edges.
        """
        if parlementair_item.corpus_node_id is None:
            return None

        # Resolve affected nodes from suggested edges when not provided
        if affected_nodes is None:
            affected_nodes = [
                se.target_node
                for se in (parlementair_item.suggested_edges or [])
                if se.target_node is not None
            ]

        review_unit_id = await self._determine_review_unit(affected_nodes)

        # Build title/priority/deadline via the strategy for this item type
        strategy = get_strategy(parlementair_item.type)
        fetched = FetchedItem(
            zaak_id="",
            zaak_nummer=parlementair_item.zaak_nummer,
            titel=parlementair_item.titel,
            onderwerp=parlementair_item.onderwerp,
            bron=parlementair_item.bron,
            deadline=parlementair_item.deadline,
        )
        task_title = strategy.task_title(fetched)
        if len(task_title) > 200:
            task_title = task_title[:197] + "..."

        description_parts = [
            f"Zaak: {parlementair_item.zaak_nummer}",
            f"Bron: {parlementair_item.bron}",
        ]
        if parlementair_item.llm_samenvatting:
            description_parts.append(f"\n{parlementair_item.llm_samenvatting}")
        description_parts.append(
            f"\n{len(affected_nodes)} gerelateerde beleidsdossiers gevonden."
        )

        deadline = strategy.calculate_deadline(fetched)
        if deadline is None:
            deadline = self._business_days_from_now(10)

        task = Task(
            node_id=parlementair_item.corpus_node_id,
            title=task_title,
            description="\n".join(description_parts),
            priority=strategy.task_priority(fetched),
            status="open",
            deadline=deadline,
            organisatie_eenheid_id=review_unit_id,
            assignee_id=None,
            parlementair_item_id=parlementair_item.id,
        )
        self.session.add(task)
        await self.session.flush()
        logger.info(
            f"Created review task for {parlementair_item.type} "
            f"{parlementair_item.zaak_nummer} "
            f"(unit: {review_unit_id or 'none'})"
        )
        return task

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

    async def reprocess_imported_items(
        self,
        item_type: str = "toezegging",
    ) -> dict:
        """Re-process imported items that have no suggested edges.

        Runs LLM tag extraction and node matching on items that were
        imported without matching (e.g. toezeggingen before LLM was
        enabled).  Items that still don't match after LLM extraction
        are moved to out_of_scope.
        """
        strategy = get_strategy(item_type)

        # Find imported items of this type with zero suggested edges
        stmt = (
            select(ParlementairItem)
            .where(
                ParlementairItem.type == item_type,
                ParlementairItem.status.in_(["imported", "pending"]),
            )
            .outerjoin(
                SuggestedEdge,
                SuggestedEdge.parlementair_item_id == ParlementairItem.id,
            )
            .group_by(ParlementairItem.id)
            .having(func.count(SuggestedEdge.id) == 0)
        )
        result = await self.session.execute(stmt)
        items = result.scalars().all()

        if not items:
            return {"total": 0, "matched": 0, "out_of_scope": 0, "skipped": 0}

        all_tags = await self.tag_repo.get_all()
        tag_names = [t.name for t in all_tags]

        llm_service = await get_llm_service(self.session)
        if not llm_service:
            logger.warning("No LLM provider configured, cannot reprocess")
            return {
                "total": len(items),
                "matched": 0,
                "out_of_scope": 0,
                "skipped": 0,
                "error": "no_llm",
            }

        matched_count = 0
        out_of_scope_count = 0
        skipped_count = 0

        for item in items:
            try:
                extraction = await llm_service.extract_tags(
                    titel=item.titel,
                    onderwerp=item.onderwerp,
                    document_tekst=item.document_tekst,
                    bestaande_tags=tag_names,
                    context_hint=strategy.context_hint(),
                )
            except Exception:
                logger.exception(
                    "LLM extraction failed for %s %s",
                    item.type,
                    item.zaak_nummer,
                )
                skipped_count += 1
                continue

            matched_tag_names = extraction.matched_tags if extraction else []
            samenvatting = extraction.samenvatting if extraction else None

            # Update item with LLM results
            item.matched_tags = matched_tag_names
            if samenvatting:
                item.llm_samenvatting = samenvatting

            # Find matching nodes
            matched_nodes = await self._find_matching_nodes(matched_tag_names)

            if not matched_nodes:
                # No matches after LLM — move to out_of_scope and
                # remove the orphaned corpus node that was created
                # during the original (matchless) import.
                await self._detach_corpus_node(item)
                item.status = "out_of_scope"
                out_of_scope_count += 1
                await self.session.flush()
                logger.info(
                    "%s %s moved to out_of_scope (no matches after LLM)",
                    item.type,
                    item.zaak_nummer,
                )
                continue

            # Tag the corpus node (only for items that matched)
            if item.corpus_node_id and matched_tag_names:
                tag_map = await self.tag_repo.get_by_names(matched_tag_names)
                for tag_name, tag in tag_map.items():
                    try:
                        await self.tag_repo.add_tag_to_node(item.corpus_node_id, tag.id)
                    except SQLAlchemyError:
                        pass  # duplicate tag, ignore

            # Create suggested edges
            for match in matched_nodes:
                target_node = match["node"]
                try:
                    await self.edge_repo.create(
                        parlementair_item_id=item.id,
                        target_node_id=target_node.id,
                        edge_type_id=strategy.default_edge_type(),
                        confidence=match["confidence"],
                        reason=match["reason"],
                        status="pending",
                    )
                except SQLAlchemyError:
                    logger.exception(
                        "Error creating suggested edge to node %s",
                        target_node.id,
                    )

            matched_count += 1
            await self.session.flush()

            logger.info(
                "%s %s reprocessed: %d suggested edges",
                item.type,
                item.zaak_nummer,
                len(matched_nodes),
            )

        await self.session.flush()
        return {
            "total": len(items),
            "matched": matched_count,
            "out_of_scope": out_of_scope_count,
            "skipped": skipped_count,
        }

    async def _detach_corpus_node(
        self,
        item: ParlementairItem,
    ) -> None:
        """Remove the corpus node created during a matchless import.

        Deletes the CorpusNode (cascading to PolitiekeInput, edges,
        tasks, stakeholders, node_tags) and clears the FK on the item.
        """
        # Delete the corpus node (cascades to politieke_input, tasks, etc.)
        if item.corpus_node_id:
            node = await self.session.get(CorpusNode, item.corpus_node_id)
            if node:
                await self.session.delete(node)
            item.corpus_node_id = None

        await self.session.flush()

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
            is_active=True,
        )
        self.session.add(person)
        await self.session.flush()
        return person
