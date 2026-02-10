"""API routes for corpus nodes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import require_deleted, require_found
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.models.person import Person
from bouwmeester.repositories.node_stakeholder import NodeStakeholderRepository
from bouwmeester.repositories.task import TaskRepository
from bouwmeester.schema.corpus_node import (
    CorpusNodeCreate,
    CorpusNodeResponse,
    CorpusNodeUpdate,
    CorpusNodeWithEdges,
    NodeStatusRecord,
    NodeTitleRecord,
    NodeType,
)
from bouwmeester.schema.edge import EdgeResponse
from bouwmeester.schema.graph import (
    GraphNeighborsResponse,
    GraphViewResponse,
    NeighborEntry,
)
from bouwmeester.schema.person import (
    NodeStakeholderCreate,
    NodeStakeholderResponse,
    NodeStakeholderUpdate,
)
from bouwmeester.schema.tag import NodeTagCreate, NodeTagResponse, TagCreate
from bouwmeester.schema.task import TaskResponse
from bouwmeester.services.activity_service import (
    ActivityService,
    resolve_actor_id,
    resolve_actor_naam_from_db,
)
from bouwmeester.services.mention_helper import sync_and_notify_mentions
from bouwmeester.services.node_service import NodeService
from bouwmeester.services.notification_service import NotificationService

# Resolve forward reference to EdgeResponse in CorpusNodeWithEdges.
CorpusNodeWithEdges.model_rebuild()

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.get("", response_model=list[CorpusNodeResponse])
async def list_nodes(
    current_user: OptionalUser,
    node_type: NodeType | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[CorpusNodeResponse]:
    service = NodeService(db)
    node_type_str = node_type.value if node_type else None
    nodes = await service.get_all(skip=skip, limit=limit, node_type=node_type_str)
    return [CorpusNodeResponse.model_validate(n) for n in nodes]


@router.post("", response_model=CorpusNodeResponse, status_code=status.HTTP_201_CREATED)
async def create_node(
    data: CorpusNodeCreate,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> CorpusNodeResponse:
    service = NodeService(db)
    node = await service.create(data)

    await sync_and_notify_mentions(
        db,
        "node",
        node.id,
        data.description,
        node.title,
        source_node_id=node.id,
    )

    await ActivityService(db).log_event(
        "node.created",
        actor_id=resolve_actor_id(current_user, actor_id),
        actor_naam=await resolve_actor_naam_from_db(current_user, actor_id, db),
        node_id=node.id,
        details={"title": node.title, "node_type": node.node_type},
    )

    return CorpusNodeResponse.model_validate(node)


@router.get("/{id}", response_model=CorpusNodeWithEdges)
async def get_node(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> CorpusNodeWithEdges:
    service = NodeService(db)
    node = require_found(await service.get(id), "Node")
    edges_from = [EdgeResponse.model_validate(e) for e in node.edges_from]
    edges_to = [EdgeResponse.model_validate(e) for e in node.edges_to]
    return CorpusNodeWithEdges(
        id=node.id,
        title=node.title,
        description=node.description,
        node_type=node.node_type,
        status=node.status,
        geldig_van=node.geldig_van,
        geldig_tot=node.geldig_tot,
        created_at=node.created_at,
        updated_at=node.updated_at,
        edge_count=len(edges_from) + len(edges_to),
        edges_from=edges_from,
        edges_to=edges_to,
    )


@router.put("/{id}", response_model=CorpusNodeResponse)
async def update_node(
    id: UUID,
    data: CorpusNodeUpdate,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> CorpusNodeResponse:
    service = NodeService(db)
    node = require_found(await service.update(id, data), "Node")

    await sync_and_notify_mentions(
        db,
        "node",
        node.id,
        data.description,
        node.title,
        source_node_id=node.id,
    )

    # Notify stakeholders of this node update (excluding the actor)
    resolved_actor = resolve_actor_id(current_user, actor_id)
    if resolved_actor:
        actor = await db.get(Person, resolved_actor)
        if actor:
            notif_svc = NotificationService(db)
            await notif_svc.notify_node_updated(node, actor)

    await ActivityService(db).log_event(
        "node.updated",
        actor_id=resolved_actor,
        actor_naam=await resolve_actor_naam_from_db(current_user, actor_id, db),
        node_id=node.id,
        details={"title": node.title},
    )

    return CorpusNodeResponse.model_validate(node)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node(
    id: UUID,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = NodeService(db)
    node = await service.get(id)
    node_title = node.title if node else None
    node_type = node.node_type if node else None
    require_deleted(await service.delete(id), "Node")
    await ActivityService(db).log_event(
        "node.deleted",
        actor_id=resolve_actor_id(current_user, actor_id),
        actor_naam=await resolve_actor_naam_from_db(current_user, actor_id, db),
        details={"node_id": str(id), "title": node_title, "node_type": node_type},
    )


@router.get("/{id}/neighbors", response_model=GraphNeighborsResponse)
async def get_neighbors(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> GraphNeighborsResponse:
    service = NodeService(db)
    result = await service.get_neighbors(id)
    require_found(result["node"], "Node")
    return GraphNeighborsResponse(
        node=CorpusNodeResponse.model_validate(result["node"]),
        neighbors=[
            NeighborEntry(
                node=CorpusNodeResponse.model_validate(n["node"]),
                edge=EdgeResponse.model_validate(n["edge"]),
            )
            for n in result["neighbors"]
        ],
    )


@router.get("/{id}/graph", response_model=GraphViewResponse)
async def get_graph(
    id: UUID,
    current_user: OptionalUser,
    depth: int = Query(2, ge=1, le=5),
    db: AsyncSession = Depends(get_db),
) -> GraphViewResponse:
    service = NodeService(db)
    result = await service.get_graph(id, depth=depth)
    return GraphViewResponse(
        nodes=[CorpusNodeResponse.model_validate(n) for n in result["nodes"]],
        edges=[EdgeResponse.model_validate(e) for e in result["edges"]],
    )


@router.get("/{id}/tasks", response_model=list[TaskResponse])
async def get_node_tasks(
    id: UUID,
    current_user: OptionalUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[TaskResponse]:
    # Verify node exists
    service = NodeService(db)
    require_found(await service.get(id), "Node")

    task_repo = TaskRepository(db)
    tasks = await task_repo.get_by_node(id, skip=skip, limit=limit)
    return [TaskResponse.model_validate(t) for t in tasks]


@router.get("/{id}/stakeholders", response_model=list[NodeStakeholderResponse])
async def get_node_stakeholders(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> list[NodeStakeholderResponse]:
    # Verify node exists
    service = NodeService(db)
    require_found(await service.get(id), "Node")

    repo = NodeStakeholderRepository(db)
    stakeholders = await repo.get_by_node(id)
    return [NodeStakeholderResponse.model_validate(s) for s in stakeholders]


@router.post(
    "/{id}/stakeholders",
    response_model=NodeStakeholderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_node_stakeholder(
    id: UUID,
    data: NodeStakeholderCreate,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> NodeStakeholderResponse:
    service = NodeService(db)
    node = require_found(await service.get(id), "Node")
    require_found(await db.get(Person, data.person_id), "Person")

    repo = NodeStakeholderRepository(db)
    stakeholder = await repo.create_stakeholder(id, data.person_id, data.rol)

    # Notify the newly added person (skip if they added themselves)
    notif_svc = NotificationService(db)
    await notif_svc.notify_stakeholder_added(
        node,
        data.person_id,
        data.rol,
        actor_id=resolve_actor_id(current_user, actor_id),
    )

    await ActivityService(db).log_event(
        "stakeholder.added",
        actor_id=resolve_actor_id(current_user, actor_id),
        actor_naam=await resolve_actor_naam_from_db(current_user, actor_id, db),
        node_id=id,
        details={"person_id": str(data.person_id), "rol": data.rol},
    )

    await db.commit()

    return NodeStakeholderResponse.model_validate(stakeholder)


@router.put(
    "/{id}/stakeholders/{stakeholder_id}",
    response_model=NodeStakeholderResponse,
)
async def update_node_stakeholder(
    id: UUID,
    stakeholder_id: UUID,
    data: NodeStakeholderUpdate,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> NodeStakeholderResponse:
    repo = NodeStakeholderRepository(db)
    stakeholder = require_found(
        await repo.get_with_person(stakeholder_id, id),
        "Stakeholder",
    )

    old_rol = stakeholder.rol
    stakeholder.rol = data.rol
    await db.flush()
    await db.refresh(stakeholder)

    # Notify if role actually changed
    if old_rol != data.rol:
        service = NodeService(db)
        node = await service.get(id)
        if node:
            notif_svc = NotificationService(db)
            await notif_svc.notify_stakeholder_role_changed(
                node, stakeholder.person_id, old_rol, data.rol
            )

    await ActivityService(db).log_event(
        "stakeholder.updated",
        actor_id=resolve_actor_id(current_user, actor_id),
        actor_naam=await resolve_actor_naam_from_db(current_user, actor_id, db),
        node_id=id,
        details={"old_rol": old_rol, "new_rol": data.rol},
    )

    await db.commit()

    return NodeStakeholderResponse.model_validate(stakeholder)


@router.delete(
    "/{id}/stakeholders/{stakeholder_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_node_stakeholder(
    id: UUID,
    stakeholder_id: UUID,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = NodeStakeholderRepository(db)
    stakeholder = require_found(
        await repo.get_with_person(stakeholder_id, id),
        "Stakeholder",
    )

    stakeholder_person_id = str(stakeholder.person_id)
    stakeholder_rol = stakeholder.rol
    await db.delete(stakeholder)

    await ActivityService(db).log_event(
        "stakeholder.removed",
        actor_id=resolve_actor_id(current_user, actor_id),
        actor_naam=await resolve_actor_naam_from_db(current_user, actor_id, db),
        node_id=id,
        details={"person_id": stakeholder_person_id, "rol": stakeholder_rol},
    )

    await db.commit()


@router.get("/{id}/tags", response_model=list[NodeTagResponse])
async def get_node_tags(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> list[NodeTagResponse]:
    from bouwmeester.repositories.tag import TagRepository

    service = NodeService(db)
    require_found(await service.get(id), "Node")

    tag_repo = TagRepository(db)
    node_tags = await tag_repo.get_by_node(id)
    return [NodeTagResponse.model_validate(nt) for nt in node_tags]


@router.post(
    "/{id}/tags",
    response_model=NodeTagResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_tag_to_node(
    id: UUID,
    data: NodeTagCreate,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> NodeTagResponse:
    from bouwmeester.repositories.tag import TagRepository

    service = NodeService(db)
    require_found(await service.get(id), "Node")

    tag_repo = TagRepository(db)

    # If tag_name is given, find or create tag
    if data.tag_name and not data.tag_id:
        existing = await tag_repo.get_by_name(data.tag_name)
        if existing:
            tag_id = existing.id
        else:
            new_tag = await tag_repo.create(TagCreate(name=data.tag_name))
            tag_id = new_tag.id
    elif data.tag_id:
        tag_id = data.tag_id
    else:
        raise HTTPException(status_code=400, detail="Provide tag_id or tag_name")

    node_tag = await tag_repo.add_tag_to_node(id, tag_id)

    await ActivityService(db).log_event(
        "tag.added",
        actor_id=resolve_actor_id(current_user, actor_id),
        actor_naam=await resolve_actor_naam_from_db(current_user, actor_id, db),
        node_id=id,
        details={"tag_id": str(tag_id)},
    )

    return NodeTagResponse.model_validate(node_tag)


@router.delete("/{id}/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_tag_from_node(
    id: UUID,
    tag_id: UUID,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> None:
    from bouwmeester.repositories.tag import TagRepository

    tag_repo = TagRepository(db)
    require_deleted(await tag_repo.remove_tag_from_node(id, tag_id), "Tag link")

    await ActivityService(db).log_event(
        "tag.removed",
        actor_id=resolve_actor_id(current_user, actor_id),
        actor_naam=await resolve_actor_naam_from_db(current_user, actor_id, db),
        node_id=id,
        details={"tag_id": str(tag_id)},
    )


@router.get("/{id}/history/titles", response_model=list[NodeTitleRecord])
async def get_node_title_history(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> list[NodeTitleRecord]:
    service = NodeService(db)
    require_found(await service.get(id), "Node")
    records = await service.get_title_history(id)
    return [NodeTitleRecord.model_validate(r) for r in records]


@router.get("/{id}/history/statuses", response_model=list[NodeStatusRecord])
async def get_node_status_history(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> list[NodeStatusRecord]:
    service = NodeService(db)
    require_found(await service.get(id), "Node")
    records = await service.get_status_history(id)
    return [NodeStatusRecord.model_validate(r) for r in records]


@router.get("/{id}/parlementair-item")
async def get_node_parlementair_item(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
) -> dict | None:
    """Get linked parliamentary item data for a politieke_input node."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from bouwmeester.models.parlementair_item import ParlementairItem

    stmt = (
        select(ParlementairItem)
        .where(ParlementairItem.corpus_node_id == id)
        .options(selectinload(ParlementairItem.suggested_edges))
    )
    result = await db.execute(stmt)
    item = result.scalar_one_or_none()
    if item is None:
        return None
    return {
        "type": item.type,
        "indieners": item.indieners or [],
        "document_url": item.document_url,
        "zaak_nummer": item.zaak_nummer,
        "bron": item.bron,
        "datum": str(item.datum) if item.datum else None,
        "deadline": str(item.deadline) if item.deadline else None,
        "ministerie": item.ministerie,
    }
