"""API routes for tasks."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import require_found
from bouwmeester.core.auth import OptionalUser, effective_person_id
from bouwmeester.core.authz import require, require_move, requires
from bouwmeester.core.database import get_db
from bouwmeester.core.deletion import delete_guarded
from bouwmeester.core.org_context import OrgContext, get_org_context
from bouwmeester.core.permissions import PermissionContext, get_permission_context
from bouwmeester.models.person import Person
from bouwmeester.repositories.task import TaskRepository
from bouwmeester.schema.inbox import InboxResponse
from bouwmeester.schema.task import (
    EenheidOverviewResponse,
    ReorderRequest,
    TaskCreate,
    TaskResponse,
    TaskStatus,
    TaskUpdate,
)
from bouwmeester.services.activity_service import (
    ActivityService,
    log_activity,
    resolve_actor,
)
from bouwmeester.services.agent_rules import require_may_assign
from bouwmeester.services.eenheid_overview_service import EenheidOverviewService
from bouwmeester.services.inbox_service import InboxService
from bouwmeester.services.mention_helper import sync_and_notify_mentions
from bouwmeester.services.notification_service import NotificationService
from bouwmeester.services.task_rules import require_task_create, require_task_links
from bouwmeester.services.visibility_filters import task_response, task_responses

router = APIRouter(prefix="/tasks", tags=["tasks"])

_READ_TASK = requires("task:read", "task")
_UPDATE_TASK = requires("task:update", "task")


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    current_user: OptionalUser,
    status_filter: TaskStatus | None = Query(None, alias="status"),
    node_id: UUID | None = Query(None),
    assignee_id: UUID | None = Query(None),
    organisatie_eenheid_id: UUID | None = Query(None),
    opdracht_id: UUID | None = Query(None),
    include_children: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
    org_ctx: OrgContext = Depends(get_org_context),
) -> list[TaskResponse]:
    """List tasks with optional filters."""
    repo = TaskRepository(db)
    if opdracht_id is not None:
        tasks = await repo.get_by_opdracht(
            opdracht_id, skip=skip, limit=limit, org_ctx=org_ctx
        )
    elif node_id is not None:
        tasks = await repo.get_by_node(node_id, skip=skip, limit=limit, org_ctx=org_ctx)
    elif assignee_id is not None:
        tasks = await repo.get_by_assignee(
            assignee_id, skip=skip, limit=limit, org_ctx=org_ctx
        )
    elif organisatie_eenheid_id is not None:
        tasks = await repo.get_by_organisatie_eenheid(
            organisatie_eenheid_id,
            include_children=include_children,
            skip=skip,
            limit=limit,
            org_ctx=org_ctx,
        )
    else:
        tasks = await repo.get_all(
            skip=skip,
            limit=limit,
            status=status_filter,
            org_ctx=org_ctx,
        )
    return await task_responses(db, perm_ctx, tasks)


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    data: TaskCreate,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> TaskResponse:
    """Create a task linked to a node. Notifies assignee and team manager."""
    await require_task_create(db, perm_ctx, data)
    repo = TaskRepository(db)
    task = await repo.create(data)

    await sync_and_notify_mentions(
        db,
        "task",
        task.id,
        data.description,
        task.title,
        sender_id=perm_ctx.person_id,
        source_task_id=task.id,
        source_node_id=task.node_id,
    )

    resolved_id, resolved_naam = await resolve_actor(current_user, actor_id, db)

    # Notify assignee
    notif_svc = NotificationService(db)
    if task.assignee_id:
        assignee = await db.get(Person, task.assignee_id)
        if assignee:
            await notif_svc.notify_task_assigned(task, assignee, actor_id=resolved_id)

    # Notify team manager
    if task.organisatie_eenheid_id:
        await notif_svc.notify_team_manager(
            task, task.organisatie_eenheid_id, exclude_person_id=task.assignee_id
        )

    assignee_naam = assignee.naam if task.assignee_id and assignee else None
    await ActivityService(db).log_event(
        "task.created",
        actor_id=resolved_id,
        actor_naam=resolved_naam,
        task_id=task.id,
        node_id=task.node_id,
        details={
            "title": task.title,
            "priority": task.priority,
            "assignee_id": str(task.assignee_id) if task.assignee_id else None,
            "assignee_naam": assignee_naam,
        },
    )

    return await task_response(db, perm_ctx, task)


@router.get("/my", response_model=list[TaskResponse])
async def get_my_tasks(
    current_user: OptionalUser,
    person_id: UUID | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> list[TaskResponse]:
    """Get tasks assigned to the current user (or person_id in dev mode).

    No org_ctx filter: a user is always entitled to see tasks assigned to
    them, even in units they cannot otherwise browse.
    """
    pid = effective_person_id(current_user, person_id)
    repo = TaskRepository(db)
    tasks = await repo.get_by_assignee(pid, skip=skip, limit=limit)
    return await task_responses(db, perm_ctx, tasks)


@router.get("/inbox", response_model=InboxResponse)
async def get_task_inbox(
    current_user: OptionalUser,
    person_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> InboxResponse:
    """Get aggregated inbox data for a person (tasks, notifications, deadlines).

    Inbox is self-scoped (own tasks and activity); what it names is
    redacted to what the caller reads (``visibility_filters.inbox_items``).
    """
    pid = effective_person_id(current_user, person_id)
    service = InboxService(db)
    return await service.get_inbox(pid, perm_ctx)


@router.get("/unassigned", response_model=list[TaskResponse])
async def get_unassigned_tasks(
    current_user: OptionalUser,
    organisatie_eenheid_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
    org_ctx: OrgContext = Depends(get_org_context),
) -> list[TaskResponse]:
    """List tasks that have no assignee, optionally filtered by org unit."""
    if organisatie_eenheid_id is not None:
        await require(
            db, perm_ctx, "task:read", "task", eenheid_id=organisatie_eenheid_id
        )
    repo = TaskRepository(db)
    tasks = await repo.get_unassigned(organisatie_eenheid_id, org_ctx=org_ctx)
    return await task_responses(db, perm_ctx, tasks)


@router.get("/work-types", response_model=list[str])
async def get_work_types(
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    org_ctx: OrgContext = Depends(get_org_context),
) -> list[str]:
    """Return distinct work_type values for autocomplete."""
    repo = TaskRepository(db)
    return await repo.get_distinct_work_types(org_ctx=org_ctx)


@router.get("/eenheid-overview", response_model=EenheidOverviewResponse)
async def get_eenheid_overview(
    current_user: OptionalUser,
    organisatie_eenheid_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
    org_ctx: OrgContext = Depends(get_org_context),
) -> EenheidOverviewResponse:
    """Overview of the tasks of an organisatie-eenheid the caller sees."""
    await require(db, perm_ctx, "task:read", "task", eenheid_id=organisatie_eenheid_id)
    service = EenheidOverviewService(db, perm_ctx, org_ctx)
    return await service.get_overview(organisatie_eenheid_id)


@router.get("/{id}", response_model=TaskResponse)
async def get_task(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(_READ_TASK),
) -> TaskResponse:
    """Get a single task by ID, including assignee and node summaries."""
    repo = TaskRepository(db)
    task = require_found(await repo.get(id), "Task")
    return await task_response(db, perm_ctx, task)


@router.get("/{id}/subtasks", response_model=list[TaskResponse])
async def get_task_subtasks(
    id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(_READ_TASK),
    org_ctx: OrgContext = Depends(get_org_context),
) -> list[TaskResponse]:
    """List subtasks of a parent task."""
    repo = TaskRepository(db)
    subtasks = await repo.get_subtasks(id, org_ctx=org_ctx)
    return await task_responses(db, perm_ctx, subtasks)


@router.put("/{id}/subtasks/reorder", response_model=list[TaskResponse])
async def reorder_subtasks(
    id: UUID,
    data: ReorderRequest,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(_UPDATE_TASK),
    org_ctx: OrgContext = Depends(get_org_context),
) -> list[TaskResponse]:
    """Reorder the subtasks of a parent task the caller sees."""
    repo = TaskRepository(db)
    require_found(await repo.get(id), "Task")
    try:
        subtasks = await repo.reorder_subtasks(id, data.task_ids, org_ctx=org_ctx)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return await task_responses(db, perm_ctx, subtasks)


@router.put("/{id}", response_model=TaskResponse)
async def update_task(
    id: UUID,
    data: TaskUpdate,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(_UPDATE_TASK),
) -> TaskResponse:
    """Update a task. Notifies on assignee change, completion, or org unit change."""
    repo = TaskRepository(db)

    # Capture old state before update
    old_task = require_found(await repo.get(id), "Task")

    await require_task_links(db, perm_ctx, data)
    await require_move(
        db, perm_ctx, "task", old_task, data.model_dump(exclude_unset=True)
    )
    await require_may_assign(db, perm_ctx, data, current=old_task.assignee_id)
    old_assignee_id = old_task.assignee_id
    old_status = old_task.status
    old_org_unit_id = old_task.organisatie_eenheid_id

    task = require_found(await repo.update(id, data), "Task")

    await sync_and_notify_mentions(
        db,
        "task",
        task.id,
        data.description,
        task.title,
        sender_id=perm_ctx.person_id,
        source_task_id=task.id,
        source_node_id=task.node_id,
    )

    resolved_id, resolved_naam = await resolve_actor(current_user, actor_id, db)
    notif_svc = NotificationService(db)

    # Detect assignee changes
    new_assignee_id = task.assignee_id
    if new_assignee_id and new_assignee_id != old_assignee_id:
        new_assignee = await db.get(Person, new_assignee_id)
        if new_assignee:
            if old_assignee_id:
                # Reassignment: notify both
                await notif_svc.notify_task_reassigned(
                    task, old_assignee_id, new_assignee, actor_id=resolved_id
                )
            else:
                # First assignment
                await notif_svc.notify_task_assigned(
                    task,
                    new_assignee,
                    actor_id=resolved_id,
                )

    # Detect status → done
    if task.status == "done" and old_status != "done":
        await notif_svc.notify_task_completed(task, actor_id=resolved_id)

    # Detect org unit change
    new_org_unit_id = task.organisatie_eenheid_id
    if new_org_unit_id and new_org_unit_id != old_org_unit_id:
        await notif_svc.notify_team_manager(
            task, new_org_unit_id, exclude_person_id=task.assignee_id
        )

    # Build change details for audit log
    changes: dict = {}
    if old_status != task.status:
        changes["old_status"] = old_status
        changes["new_status"] = task.status
    if old_assignee_id != task.assignee_id:
        changes["old_assignee_id"] = str(old_assignee_id) if old_assignee_id else None
        changes["new_assignee_id"] = str(task.assignee_id) if task.assignee_id else None
        if task.assignee_id:
            new_person = await db.get(Person, task.assignee_id)
            changes["new_assignee_naam"] = new_person.naam if new_person else None

    await ActivityService(db).log_event(
        "task.updated",
        actor_id=resolved_id,
        actor_naam=resolved_naam,
        task_id=task.id,
        node_id=task.node_id,
        details={"title": task.title, **changes},
    )

    return await task_response(db, perm_ctx, task)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    id: UUID,
    current_user: OptionalUser,
    actor_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(requires("task:delete", "task")),
) -> None:
    """Delete a task with its subtasks; 409 when the caller may not delete
    every subtask (``core.deletion``)."""
    task = require_found(await TaskRepository(db).get(id), "Task")
    task_title = task.title
    task_node_id = task.node_id
    await delete_guarded(db, perm_ctx, "task", id)
    await log_activity(
        db,
        current_user,
        actor_id,
        "task.deleted",
        details={
            "task_id": str(id),
            "node_id": str(task_node_id) if task_node_id else None,
            "title": task_title,
        },
    )
