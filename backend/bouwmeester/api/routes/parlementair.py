"""API routes for parliamentary item imports and review."""

import logging
from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import require_found
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.authority import require_can_name_owner
from bouwmeester.core.authz import require, requires
from bouwmeester.core.database import get_db
from bouwmeester.core.org_context import OrgContext, get_org_context, sees_node
from bouwmeester.core.permissions import (
    PermissionContext,
    get_permission_context,
    require_permission,
    require_system_permission,
)
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.edge import Edge
from bouwmeester.models.parlementair_item import ParlementairItem, SuggestedEdge
from bouwmeester.models.person import Person
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.task import Task
from bouwmeester.repositories.parlementair_item import (
    ParlementairItemRepository,
    SuggestedEdgeRepository,
)
from bouwmeester.repositories.task import TaskRepository
from bouwmeester.schema.parlementair_item import (
    ParlementairItemResponse,
    SuggestedEdgeResponse,
)
from bouwmeester.schema.task import TaskCreate
from bouwmeester.services.activity_service import log_activity
from bouwmeester.services.edge_schema_service import EdgeSchemaService
from bouwmeester.services.task_rules import require_task_create

logger = logging.getLogger(__name__)

SUGGESTED_EDGE_DESCRIPTION = "Automatisch voorgesteld vanuit parlementaire import"
_NO_NODE = "Deze import heeft nog geen gekoppeld item"


class FollowUpTask(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(None, max_length=10000)
    assignee_id: UUID | None = None
    deadline: date | None = None


class CompleteReviewRequest(BaseModel):
    eigenaar_id: UUID
    tasks: list[FollowUpTask] = []


router = APIRouter(prefix="/parlementair", tags=["parlementair"])


async def _require_can_review(
    db: AsyncSession, perm_ctx: PermissionContext, import_id: UUID
) -> ParlementairItem:
    """Reviewing an item is acting on its politieke_input node.

    The node decides where ``parlementair:review`` must be held.  An item
    without a node yet (out of scope) is decided like a new node without
    eenheid.
    """
    item = require_found(await db.get(ParlementairItem, import_id), "Import")
    await require(
        db, perm_ctx, "parlementair:review", "corpus_node", item.corpus_node_id
    )
    return item


def _sees_target(edge: SuggestedEdge, org_ctx: OrgContext) -> bool:
    """Does the caller see the suggestion's (loaded) target node?

    Suggestions embed their target node; ``parlementair:read`` must not
    reveal nodes the org filter hides.  Decided on the loaded row with the
    ``node:read`` rule (``sees_node``: eenheid, resource roles, shares), so a
    list costs no extra queries.
    """
    target = edge.target_node
    return target is not None and sees_node(
        org_ctx, target.id, target.organisatie_eenheid_id
    )


def _item_response(
    item: ParlementairItem, org_ctx: OrgContext
) -> ParlementairItemResponse:
    """The item with only the suggestions whose target node the caller sees."""
    response = ParlementairItemResponse.model_validate(item)
    visible = {edge.id for edge in item.suggested_edges if _sees_target(edge, org_ctx)}
    response.suggested_edges = [
        edge for edge in response.suggested_edges if edge.id in visible
    ]
    return response


def _edge_response(edge: SuggestedEdge, org_ctx: OrgContext) -> SuggestedEdgeResponse:
    """One suggestion, its target node left out when the caller cannot see it.

    A reviewer acts on the item's node; the target may lie elsewhere.
    """
    response = SuggestedEdgeResponse.model_validate(edge)
    if not _sees_target(edge, org_ctx):
        response.target_node = None
    return response


# Reviewing a suggestion is parlementair:review on its item's node; core.authz
# decides that on the suggested edge itself.
_REVIEW_EDGE = requires("suggested_edge:update", "suggested_edge", path_param="edge_id")
_RESET_EDGE = requires("suggested_edge:delete", "suggested_edge", path_param="edge_id")


@router.get("/imports", response_model=list[ParlementairItemResponse])
async def list_imports(
    current_user: OptionalUser,
    status_filter: str | None = Query(None, alias="status"),
    bron: str | None = None,
    type_filter: str | None = Query(None, alias="type"),
    search: str | None = Query(None, max_length=500),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(get_org_context),
    _perm=Depends(require_permission("parlementair:read")),
) -> list[ParlementairItemResponse]:
    """List imported parliamentary items. Filter by status, bron, type, or search."""
    repo = ParlementairItemRepository(db)
    imports = await repo.get_all(
        status=status_filter,
        bron=bron,
        item_type=type_filter,
        search=search,
        skip=skip,
        limit=limit,
    )
    return [_item_response(item, org_ctx) for item in imports]


@router.get("/imports/{import_id}", response_model=ParlementairItemResponse)
async def get_import(
    import_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(get_org_context),
    _perm=Depends(require_permission("parlementair:read")),
) -> ParlementairItemResponse:
    """Get a single parliamentary import item by ID."""
    repo = ParlementairItemRepository(db)
    item = require_found(await repo.get_by_id(import_id), "Import")
    return _item_response(item, org_ctx)


@router.post("/imports/trigger")
async def trigger_import(
    current_user: OptionalUser,
    item_types: list[str] | None = Query(None, alias="types"),
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_system_permission("parlementair:import")),
) -> dict:
    """Trigger a manual parliamentary item import poll."""
    from bouwmeester.services.parlementair_import_service import (
        ParlementairImportService,
    )

    service = ParlementairImportService(db)
    count = await service.poll_and_import(item_types=item_types)

    await log_activity(
        db,
        current_user,
        actor_id,
        "parlementair.import_triggered",
        details={"count": count},
    )

    return {"message": f"{count} items geïmporteerd", "imported": count}


@router.post("/imports/reprocess")
async def reprocess_imports(
    current_user: OptionalUser,
    item_type: Literal["motie", "kamervraag", "toezegging"] = Query("toezegging"),
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_system_permission("parlementair:import")),
) -> dict:
    """Re-process imported items that have no suggested edges.

    Runs LLM tag extraction and matching on items that were imported
    without it (e.g. toezeggingen before LLM was enabled).
    """
    from bouwmeester.services.parlementair_import_service import (
        ParlementairImportService,
    )

    service = ParlementairImportService(db)
    result = await service.reprocess_imported_items(item_type=item_type)

    await log_activity(
        db,
        current_user,
        actor_id,
        "parlementair.reprocess_triggered",
        details=result,
    )

    return result


@router.get("/review-queue", response_model=list[ParlementairItemResponse])
async def get_review_queue(
    current_user: OptionalUser,
    type_filter: str | None = Query(None, alias="type"),
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(get_org_context),
    _perm=Depends(require_permission("parlementair:read")),
) -> list[ParlementairItemResponse]:
    """Get parliamentary items pending review, optionally filtered by type."""
    repo = ParlementairItemRepository(db)
    imports = await repo.get_review_queue(item_type=type_filter)
    return [_item_response(item, org_ctx) for item in imports]


@router.put("/imports/{import_id}/reject", response_model=ParlementairItemResponse)
async def reject_import(
    import_id: UUID,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
    org_ctx: OrgContext = Depends(get_org_context),
) -> ParlementairItemResponse:
    """Reject a parliamentary import item (sets status to rejected)."""
    await _require_can_review(db, perm_ctx, import_id)
    repo = ParlementairItemRepository(db)
    item = require_found(
        await repo.update_status(import_id, "rejected", reviewed_at=datetime.now(UTC)),
        "Import",
    )

    await log_activity(
        db,
        current_user,
        actor_id,
        "parlementair.rejected",
        details={"item_id": str(import_id)},
    )

    return _item_response(item, org_ctx)


@router.put("/imports/{import_id}/reopen", response_model=ParlementairItemResponse)
async def reopen_import(
    import_id: UUID,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
    org_ctx: OrgContext = Depends(get_org_context),
) -> ParlementairItemResponse:
    """Reopen a rejected or out-of-scope item for review."""
    from bouwmeester.services.parlementair_import_service import (
        ParlementairImportService,
    )

    await _require_can_review(db, perm_ctx, import_id)
    repo = ParlementairItemRepository(db)
    item = require_found(await repo.get_by_id(import_id), "Import")
    if item.status not in ("rejected", "out_of_scope"):
        raise HTTPException(
            status_code=400,
            detail="Alleen afgewezen of buiten-scope items kunnen heropend worden",
        )

    item = require_found(
        await repo.update_status(import_id, "imported", reviewed_at=None), "Import"
    )

    # Ensure corpus node exists (out-of-scope items skip node creation)
    service = ParlementairImportService(db)
    item = await service.ensure_corpus_node(item)

    # Create a review task (same logic as initial import)
    try:
        await service.create_review_task(item)
    except Exception:
        logger.exception("Error creating review task for reopened item %s", import_id)

    await log_activity(
        db,
        current_user,
        actor_id,
        "parlementair.reopened",
        details={"item_id": str(import_id)},
    )

    # Re-fetch to ensure all relationships are loaded for serialization
    item = await repo.get_by_id(import_id)
    return _item_response(item, org_ctx)


async def _make_sole_person_owner(
    db: AsyncSession, perm_ctx: PermissionContext, node_id: UUID, person_id: UUID
) -> None:
    """Make *person_id* the eigenaar of the node, replacing other people.

    ``require_can_name_owner`` decides; eigenaar grants to an eenheid stay.
    """
    await require_can_name_owner(db, perm_ctx, node_id, person_id)
    grants = (
        await db.scalars(
            select(ResourcePermission).where(
                ResourcePermission.resource_type == "corpus_node",
                ResourcePermission.resource_id == node_id,
                ResourcePermission.rol == "eigenaar",
                ResourcePermission.person_id.isnot(None),
            )
        )
    ).all()
    if any(grant.person_id == person_id for grant in grants):
        return
    db.add(
        ResourcePermission(
            person_id=person_id,
            resource_type="corpus_node",
            resource_id=node_id,
            rol="eigenaar",
        )
    )
    for grant in grants:
        await db.delete(grant)
    await db.flush()


@router.post("/imports/{import_id}/complete", response_model=ParlementairItemResponse)
async def complete_review(
    import_id: UUID,
    body: CompleteReviewRequest,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
    org_ctx: OrgContext = Depends(get_org_context),
) -> ParlementairItemResponse:
    """Complete review: assign eigenaar, create follow-up tasks, mark as reviewed."""
    item = await _require_can_review(db, perm_ctx, import_id)
    repo = ParlementairItemRepository(db)
    if item.corpus_node_id is None:
        raise HTTPException(status_code=400, detail=_NO_NODE)
    require_found(await db.get(Person, body.eigenaar_id), "Eigenaar")

    # Follow-up tasks are new tasks like any other: the POST /tasks rules.
    follow_ups = [
        TaskCreate(
            node_id=item.corpus_node_id,
            parlementair_item_id=import_id,
            title=t.title,
            description=t.description,
            assignee_id=t.assignee_id,
            deadline=t.deadline,
        )
        for t in body.tasks
    ]
    for follow_up in follow_ups:
        await require_task_create(db, perm_ctx, follow_up)

    await _make_sole_person_owner(db, perm_ctx, item.corpus_node_id, body.eigenaar_id)

    # Auto-complete existing review tasks before creating new ones
    stmt = select(Task).where(
        Task.parlementair_item_id == import_id,
        Task.status.notin_(["done", "cancelled"]),
    )
    result = await db.execute(stmt)
    for task in result.scalars().all():
        task.status = "done"
    await db.flush()

    task_repo = TaskRepository(db)
    for follow_up in follow_ups:
        await task_repo.create(follow_up)

    # Update item status to reviewed
    item = await repo.update_status(
        import_id, "reviewed", reviewed_at=datetime.now(UTC)
    )

    await log_activity(
        db,
        current_user,
        actor_id,
        "parlementair.reviewed",
        details={"item_id": str(import_id), "eigenaar_id": str(body.eigenaar_id)},
    )

    return _item_response(item, org_ctx)


class UpdateSuggestedEdgeRequest(BaseModel):
    edge_type_id: str


@router.patch("/edges/{edge_id}", response_model=SuggestedEdgeResponse)
async def update_suggested_edge(
    edge_id: UUID,
    body: UpdateSuggestedEdgeRequest,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    _authz=Depends(_REVIEW_EDGE),
    org_ctx: OrgContext = Depends(get_org_context),
) -> SuggestedEdgeResponse:
    """Update a suggested edge (e.g. change its edge type) before approval."""
    suggested_edge = require_found(await db.get(SuggestedEdge, edge_id), "Suggestie")
    repo = SuggestedEdgeRepository(db)
    if suggested_edge.status != "pending":
        raise HTTPException(
            status_code=400,
            detail="Alleen openstaande suggesties kunnen worden gewijzigd",
        )
    suggested_edge.edge_type_id = body.edge_type_id
    await db.flush()
    updated = await repo.get_by_id(edge_id)
    return _edge_response(updated, org_ctx)


@router.put("/edges/{edge_id}/approve", response_model=SuggestedEdgeResponse)
async def approve_edge(
    edge_id: UUID,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _authz=Depends(_REVIEW_EDGE),
    org_ctx: OrgContext = Depends(get_org_context),
) -> SuggestedEdgeResponse:
    """Approve a suggested edge, creating the actual edge in the graph."""
    suggested_edge = require_found(await db.get(SuggestedEdge, edge_id), "Suggestie")
    suggested_edge_repo = SuggestedEdgeRepository(db)
    item = await db.get(ParlementairItem, suggested_edge.parlementair_item_id)
    if item is None or item.corpus_node_id is None:
        raise HTTPException(status_code=400, detail=_NO_NODE)

    # Validate against edge schema rules
    from_node = await db.get(CorpusNode, item.corpus_node_id)
    to_node = await db.get(CorpusNode, suggested_edge.target_node_id)
    if from_node and to_node:
        error = await EdgeSchemaService(db).validate_edge(
            from_node.node_type, to_node.node_type, suggested_edge.edge_type_id
        )
        if error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=error,
            )

    # Create actual Edge
    edge = Edge(
        from_node_id=item.corpus_node_id,
        to_node_id=suggested_edge.target_node_id,
        edge_type_id=suggested_edge.edge_type_id,
        description=SUGGESTED_EDGE_DESCRIPTION,
    )
    db.add(edge)
    await db.flush()

    # Update suggested edge status
    suggested_edge.status = "approved"
    suggested_edge.edge_id = edge.id
    suggested_edge.reviewed_at = datetime.now(UTC)
    await db.flush()

    await log_activity(
        db,
        current_user,
        actor_id,
        "parlementair.edge_approved",
        details={"suggested_edge_id": str(edge_id)},
    )

    updated = await suggested_edge_repo.get_by_id(edge_id)
    return _edge_response(updated, org_ctx)


@router.put("/edges/{edge_id}/reject", response_model=SuggestedEdgeResponse)
async def reject_edge(
    edge_id: UUID,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _authz=Depends(_REVIEW_EDGE),
    org_ctx: OrgContext = Depends(get_org_context),
) -> SuggestedEdgeResponse:
    """Reject a suggested edge (sets status to rejected)."""
    repo = SuggestedEdgeRepository(db)
    updated = require_found(
        await repo.update_status(edge_id, "rejected", reviewed_at=datetime.now(UTC)),
        "Suggestie",
    )

    await log_activity(
        db,
        current_user,
        actor_id,
        "parlementair.edge_rejected",
        details={"suggested_edge_id": str(edge_id)},
    )

    return _edge_response(updated, org_ctx)


@router.put("/edges/{edge_id}/reset", response_model=SuggestedEdgeResponse)
async def reset_suggested_edge(
    edge_id: UUID,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _authz=Depends(_RESET_EDGE),
    org_ctx: OrgContext = Depends(get_org_context),
) -> SuggestedEdgeResponse:
    """Reset a suggested edge back to pending, undoing approve/reject.

    Resetting an approved suggestion deletes the edge it created, so it is
    asked as deleting the suggestion.
    """
    suggested_edge = require_found(await db.get(SuggestedEdge, edge_id), "Suggestie")
    repo = SuggestedEdgeRepository(db)

    # If it was approved, delete the actual edge that was created
    if suggested_edge.status == "approved" and suggested_edge.edge_id is not None:
        actual_edge = await db.get(Edge, suggested_edge.edge_id)
        if actual_edge is not None:
            await db.delete(actual_edge)

    suggested_edge.edge_id = None
    updated = await repo.update_status(
        edge_id,
        "pending",
        reviewed_at=None,
    )

    await log_activity(
        db,
        current_user,
        actor_id,
        "parlementair.edge_reset",
        details={"suggested_edge_id": str(edge_id)},
    )

    return _edge_response(updated, org_ctx)
