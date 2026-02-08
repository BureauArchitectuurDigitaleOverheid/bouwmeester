"""API routes for motie imports and review."""

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
from bouwmeester.repositories.motie_import import (
    MotieImportRepository,
    SuggestedEdgeRepository,
)
from bouwmeester.schema.motie_import import MotieImportResponse, SuggestedEdgeResponse

SUGGESTED_EDGE_DESCRIPTION = "Automatisch voorgesteld vanuit motie-import"


class FollowUpTask(BaseModel):
    title: str
    description: str | None = None
    assignee_id: UUID | None = None
    deadline: date | None = None


class CompleteReviewRequest(BaseModel):
    eigenaar_id: UUID
    tasks: list[FollowUpTask] = []


router = APIRouter(prefix="/moties", tags=["moties"])


@router.get("/imports", response_model=list[MotieImportResponse])
async def list_imports(
    status_filter: str | None = Query(None, alias="status"),
    bron: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[MotieImportResponse]:
    repo = MotieImportRepository(db)
    imports = await repo.get_all(
        status=status_filter, bron=bron, skip=skip, limit=limit
    )
    return [MotieImportResponse.model_validate(i) for i in imports]


@router.get("/imports/{import_id}", response_model=MotieImportResponse)
async def get_import(
    import_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> MotieImportResponse:
    repo = MotieImportRepository(db)
    motie_import = await repo.get_by_id(import_id)
    if motie_import is None:
        raise HTTPException(status_code=404, detail="Import not found")
    return MotieImportResponse.model_validate(motie_import)


@router.post("/imports/trigger")
async def trigger_import(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger a manual motie import poll."""
    # Import here to avoid circular imports at module level
    from bouwmeester.services.motie_import_service import MotieImportService

    service = MotieImportService(db)
    count = await service.poll_and_import()
    return {"message": f"{count} moties geïmporteerd", "imported": count}


@router.get("/review-queue", response_model=list[MotieImportResponse])
async def get_review_queue(
    db: AsyncSession = Depends(get_db),
) -> list[MotieImportResponse]:
    repo = MotieImportRepository(db)
    imports = await repo.get_review_queue()
    return [MotieImportResponse.model_validate(i) for i in imports]


@router.put("/imports/{import_id}/reject", response_model=MotieImportResponse)
async def reject_import(
    import_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> MotieImportResponse:
    repo = MotieImportRepository(db)
    motie_import = await repo.update_status(
        import_id, "rejected", reviewed_at=datetime.utcnow()
    )
    if motie_import is None:
        raise HTTPException(status_code=404, detail="Import not found")
    return MotieImportResponse.model_validate(motie_import)


@router.post("/imports/{import_id}/complete", response_model=MotieImportResponse)
async def complete_review(
    import_id: UUID,
    body: CompleteReviewRequest,
    db: AsyncSession = Depends(get_db),
) -> MotieImportResponse:
    repo = MotieImportRepository(db)
    motie_import = await repo.get_by_id(import_id)
    if motie_import is None:
        raise HTTPException(status_code=404, detail="Import not found")
    if motie_import.corpus_node_id is None:
        raise HTTPException(
            status_code=400, detail="Motie import has no linked corpus node"
        )

    # Validate eigenaar person exists
    person = await db.get(Person, body.eigenaar_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Eigenaar person not found")

    # Upsert eigenaar stakeholder on the corpus node
    stmt = select(NodeStakeholder).where(
        NodeStakeholder.node_id == motie_import.corpus_node_id,
        NodeStakeholder.rol == "eigenaar",
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing is None:
        db.add(
            NodeStakeholder(
                node_id=motie_import.corpus_node_id,
                person_id=body.eigenaar_id,
                rol="eigenaar",
            )
        )
    elif existing.person_id != body.eigenaar_id:
        existing.person_id = body.eigenaar_id
    await db.flush()

    # Auto-complete existing review tasks before creating new ones
    stmt = select(Task).where(
        Task.motie_import_id == import_id,
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
                node_id=motie_import.corpus_node_id,
                motie_import_id=import_id,
                title=t.title,
                description=t.description,
                assignee_id=t.assignee_id,
                deadline=t.deadline,
                priority="normaal",
            )
        )
    await db.flush()

    # Update motie status to reviewed
    motie_import = await repo.update_status(
        import_id, "reviewed", reviewed_at=datetime.utcnow()
    )

    return MotieImportResponse.model_validate(motie_import)


@router.put("/edges/{edge_id}/approve", response_model=SuggestedEdgeResponse)
async def approve_edge(
    edge_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> SuggestedEdgeResponse:
    suggested_edge_repo = SuggestedEdgeRepository(db)
    suggested_edge = await suggested_edge_repo.get_by_id(edge_id)
    if suggested_edge is None:
        raise HTTPException(status_code=404, detail="Suggested edge not found")

    # Fetch the parent motie_import to get corpus_node_id
    motie_import_repo = MotieImportRepository(db)
    motie_import = await motie_import_repo.get_by_id(suggested_edge.motie_import_id)
    if motie_import is None or motie_import.corpus_node_id is None:
        raise HTTPException(
            status_code=400,
            detail="Motie import has no linked corpus node",
        )

    # Create actual Edge
    edge = Edge(
        from_node_id=motie_import.corpus_node_id,
        to_node_id=suggested_edge.target_node_id,
        edge_type_id=suggested_edge.edge_type_id,
        description=SUGGESTED_EDGE_DESCRIPTION,
    )
    db.add(edge)
    await db.flush()

    # Update suggested edge status
    # Note: use the SuggestedEdge's id (not the path param) and set
    # the created Edge's id via the 'edge_id' column
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
