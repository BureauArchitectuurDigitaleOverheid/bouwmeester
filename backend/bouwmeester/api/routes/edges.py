"""API routes for edges."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import require_deleted, require_found
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.repositories.edge import EdgeRepository
from bouwmeester.schema.edge import EdgeCreate, EdgeResponse, EdgeUpdate, EdgeWithNodes
from bouwmeester.services.activity_service import (
    ActivityService,
    log_activity,
    resolve_actor,
)
from bouwmeester.services.notification_service import NotificationService

router = APIRouter(prefix="/edges", tags=["edges"])


@router.get("", response_model=list[EdgeWithNodes])
async def list_edges(
    current_user: OptionalUser,
    from_node_id: UUID | None = None,
    to_node_id: UUID | None = None,
    node_id: UUID | None = None,
    edge_type_id: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[EdgeWithNodes]:
    repo = EdgeRepository(db)
    edges = await repo.get_all(
        skip=skip,
        limit=limit,
        from_node_id=from_node_id,
        to_node_id=to_node_id,
        node_id=node_id,
        edge_type_id=edge_type_id,
    )
    return [EdgeWithNodes.model_validate(e) for e in edges]


@router.post("", response_model=EdgeResponse, status_code=status.HTTP_201_CREATED)
async def create_edge(
    data: EdgeCreate,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> EdgeResponse:
    repo = EdgeRepository(db)
    try:
        edge = await repo.create(data)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Deze verbinding bestaat al.",
        )

    resolved_id, resolved_naam = await resolve_actor(current_user, actor_id, db)

    # Notify stakeholders of both nodes
    from_node = await db.get(CorpusNode, data.from_node_id)
    to_node = await db.get(CorpusNode, data.to_node_id)
    if from_node and to_node:
        notif_svc = NotificationService(db)
        await notif_svc.notify_edge_created(
            from_node, to_node, actor_id=resolved_id
        )

    await ActivityService(db).log_event(
        "edge.created",
        actor_id=resolved_id,
        actor_naam=resolved_naam,
        edge_id=edge.id,
        details={
            "from_node_id": str(data.from_node_id),
            "from_node_title": from_node.title if from_node else None,
            "to_node_id": str(data.to_node_id),
            "to_node_title": to_node.title if to_node else None,
            "edge_type": data.edge_type_id,
        },
    )

    return EdgeResponse.model_validate(edge)


@router.get("/{id}", response_model=EdgeWithNodes)
async def get_edge(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> EdgeWithNodes:
    repo = EdgeRepository(db)
    edge = require_found(await repo.get(id), "Edge")
    return EdgeWithNodes.model_validate(edge)


@router.put("/{id}", response_model=EdgeResponse)
async def update_edge(
    id: UUID,
    data: EdgeUpdate,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> EdgeResponse:
    repo = EdgeRepository(db)
    edge = require_found(await repo.update(id, data), "Edge")

    await log_activity(
        db, current_user, actor_id, "edge.updated",
        edge_id=edge.id,
        details={"edge_type": edge.edge_type_id},
    )

    return EdgeResponse.model_validate(edge)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_edge(
    id: UUID,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = EdgeRepository(db)
    edge = await repo.get(id)
    edge_details: dict = {}
    if edge:
        from_node = await db.get(CorpusNode, edge.from_node_id)
        to_node = await db.get(CorpusNode, edge.to_node_id)
        edge_details = {
            "from_node_id": str(edge.from_node_id),
            "from_node_title": from_node.title if from_node else None,
            "to_node_id": str(edge.to_node_id),
            "to_node_title": to_node.title if to_node else None,
            "edge_type": edge.edge_type_id,
        }
    require_deleted(await repo.delete(id), "Edge")
    await log_activity(
        db, current_user, actor_id, "edge.deleted",
        details={**edge_details, "edge_id": str(id)},
    )
