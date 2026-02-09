"""API routes for parliamentary item imports and review."""

from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.database import get_db
from bouwmeester.models.edge import Edge
from bouwmeester.models.node_stakeholder import NodeStakeholder
from bouwmeester.models.person import Person
from bouwmeester.models.task import Task
from bouwmeester.repositories.parlementair_item import (
    ParlementairItemRepository,
    SuggestedEdgeRepository,
)
from bouwmeester.schema.parlementair_item import (
    ParlementairItemResponse,
    SuggestedEdgeResponse,
)

SUGGESTED_EDGE_DESCRIPTION = "Automatisch voorgesteld vanuit parlementaire import"


class FollowUpTask(BaseModel):
    title: str
    description: str | None = None
    assignee_id: UUID | None = None
    deadline: date | None = None


class CompleteReviewRequest(BaseModel):
    eigenaar_id: UUID
    tasks: list[FollowUpTask] = []


router = APIRouter(prefix="/parlementair", tags=["parlementair"])


@router.get("/imports", response_model=list[ParlementairItemResponse])
async def list_imports(
    status_filter: str | None = Query(None, alias="status"),
    bron: str | None = None,
    type_filter: str | None = Query(None, alias="type"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[ParlementairItemResponse]:
    repo = ParlementairItemRepository(db)
    imports = await repo.get_all(
        status=status_filter, bron=bron, item_type=type_filter, skip=skip, limit=limit
    )
    return [ParlementairItemResponse.model_validate(i) for i in imports]


@router.get("/imports/{import_id}", response_model=ParlementairItemResponse)
async def get_import(
    import_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ParlementairItemResponse:
    repo = ParlementairItemRepository(db)
    item = await repo.get_by_id(import_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Import not found")
    return ParlementairItemResponse.model_validate(item)


@router.post("/imports/trigger")
async def trigger_import(
    item_types: list[str] | None = Query(None, alias="types"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger a manual parliamentary item import poll."""
    from bouwmeester.services.parlementair_import_service import (
        ParlementairImportService,
    )

    service = ParlementairImportService(db)
    count = await service.poll_and_import(item_types=item_types)
    return {"message": f"{count} items geïmporteerd", "imported": count}


@router.get("/review-queue", response_model=list[ParlementairItemResponse])
async def get_review_queue(
    type_filter: str | None = Query(None, alias="type"),
    db: AsyncSession = Depends(get_db),
) -> list[ParlementairItemResponse]:
    repo = ParlementairItemRepository(db)
    imports = await repo.get_review_queue(item_type=type_filter)
    return [ParlementairItemResponse.model_validate(i) for i in imports]


@router.put("/imports/{import_id}/reject", response_model=ParlementairItemResponse)
async def reject_import(
    import_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ParlementairItemResponse:
    repo = ParlementairItemRepository(db)
    item = await repo.update_status(
        import_id, "rejected", reviewed_at=datetime.utcnow()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Import not found")
    return ParlementairItemResponse.model_validate(item)


@router.post("/imports/{import_id}/complete", response_model=ParlementairItemResponse)
async def complete_review(
    import_id: UUID,
    body: CompleteReviewRequest,
    db: AsyncSession = Depends(get_db),
) -> ParlementairItemResponse:
    repo = ParlementairItemRepository(db)
    item = await repo.get_by_id(import_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Import not found")
    if item.corpus_node_id is None:
        raise HTTPException(status_code=400, detail="Import has no linked corpus node")

    # Validate eigenaar person exists
    person = await db.get(Person, body.eigenaar_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Eigenaar person not found")

    # Upsert eigenaar stakeholder on the corpus node
    stmt = select(NodeStakeholder).where(
        NodeStakeholder.node_id == item.corpus_node_id,
        NodeStakeholder.rol == "eigenaar",
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing is None:
        db.add(
            NodeStakeholder(
                node_id=item.corpus_node_id,
                person_id=body.eigenaar_id,
                rol="eigenaar",
            )
        )
    elif existing.person_id != body.eigenaar_id:
        existing.person_id = body.eigenaar_id
    await db.flush()

    # Auto-complete existing review tasks before creating new ones
    stmt = select(Task).where(
        Task.parlementair_item_id == import_id,
        Task.status.notin_(["done", "cancelled"]),
    )
    result = await db.execute(stmt)
    for task in result.scalars().all():
        task.status = "done"
    await db.flush()

    # Create optional follow-up tasks
    for t in body.tasks:
        db.add(
            Task(
                node_id=item.corpus_node_id,
                parlementair_item_id=import_id,
                title=t.title,
                description=t.description,
                assignee_id=t.assignee_id,
                deadline=t.deadline,
                priority="normaal",
            )
        )
    await db.flush()

    # Update item status to reviewed
    item = await repo.update_status(
        import_id, "reviewed", reviewed_at=datetime.utcnow()
    )

    return ParlementairItemResponse.model_validate(item)


class UpdateSuggestedEdgeRequest(BaseModel):
    edge_type_id: str


@router.patch("/edges/{edge_id}", response_model=SuggestedEdgeResponse)
async def update_suggested_edge(
    edge_id: UUID,
    body: UpdateSuggestedEdgeRequest,
    db: AsyncSession = Depends(get_db),
) -> SuggestedEdgeResponse:
    """Update a suggested edge (e.g. change its edge type) before approval."""
    repo = SuggestedEdgeRepository(db)
    suggested_edge = await repo.get_by_id(edge_id)
    if suggested_edge is None:
        raise HTTPException(status_code=404, detail="Suggested edge not found")
    if suggested_edge.status != "pending":
        raise HTTPException(status_code=400, detail="Can only update pending edges")
    suggested_edge.edge_type_id = body.edge_type_id
    await db.flush()
    updated = await repo.get_by_id(edge_id)
    return SuggestedEdgeResponse.model_validate(updated)


@router.put("/edges/{edge_id}/approve", response_model=SuggestedEdgeResponse)
async def approve_edge(
    edge_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> SuggestedEdgeResponse:
    suggested_edge_repo = SuggestedEdgeRepository(db)
    suggested_edge = await suggested_edge_repo.get_by_id(edge_id)
    if suggested_edge is None:
        raise HTTPException(status_code=404, detail="Suggested edge not found")

    # Fetch the parent item to get corpus_node_id
    item_repo = ParlementairItemRepository(db)
    item = await item_repo.get_by_id(suggested_edge.parlementair_item_id)
    if item is None or item.corpus_node_id is None:
        raise HTTPException(
            status_code=400,
            detail="Import has no linked corpus node",
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
    suggested_edge.reviewed_at = datetime.utcnow()
    await db.flush()
    updated = await suggested_edge_repo.get_by_id(edge_id)
    return SuggestedEdgeResponse.model_validate(updated)


@router.put("/edges/{edge_id}/reject", response_model=SuggestedEdgeResponse)
async def reject_edge(
    edge_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> SuggestedEdgeResponse:
    repo = SuggestedEdgeRepository(db)
    updated = await repo.update_status(
        edge_id,
        "rejected",
        reviewed_at=datetime.utcnow(),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Suggested edge not found")
    return SuggestedEdgeResponse.model_validate(updated)


@router.put("/edges/{edge_id}/reset", response_model=SuggestedEdgeResponse)
async def reset_suggested_edge(
    edge_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> SuggestedEdgeResponse:
    """Reset a suggested edge back to pending, undoing approve/reject."""
    repo = SuggestedEdgeRepository(db)
    suggested_edge = await repo.get_by_id(edge_id)
    if suggested_edge is None:
        raise HTTPException(status_code=404, detail="Suggested edge not found")

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
    return SuggestedEdgeResponse.model_validate(updated)
