"""Responses name only what the caller may read.

A response about something the caller reads often names other things: the
subtasks and opdracht of a task, the nodes an opdracht or a lead is linked
to, the resources a person holds a role on.  Those references are filtered
here, with the same ``<type>:read`` decision ``core.authz`` takes for the
thing itself.  :func:`readable_ids` locates all references of one type with
``prefetch`` and then decides each from the request cache, so a list costs a
constant number of queries.

What the caller cannot read is left out of a list of references, and an
embedded summary of it (a task's node, an opdracht's instrument) becomes
``None``; the id of the reference on the record itself stays, it is part of
the record the caller reads.
"""

from collections.abc import Iterable, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.authz import can, prefetch
from bouwmeester.core.permissions import PermissionContext
from bouwmeester.models.opdracht import Opdracht
from bouwmeester.models.task import Task
from bouwmeester.schema.lead import LeadDetailResponse
from bouwmeester.schema.opdracht import OpdrachtResponse
from bouwmeester.schema.task import TaskResponse

_READ_PERMISSION = {"corpus_node": "node:read"}


def read_permission(resource_type: str) -> str:
    """The permission that reads a resource of *resource_type*."""
    return _READ_PERMISSION.get(resource_type, f"{resource_type}:read")


async def readable_ids(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    resource_type: str,
    ids: Iterable[UUID | None],
) -> set[UUID]:
    """The ids among *ids* the caller may read (missing ones are not readable)."""
    wanted = {rid for rid in ids if rid is not None}
    if not wanted:
        return set()
    await prefetch(db, perm_ctx, resource_type, wanted)
    permission = read_permission(resource_type)
    return {
        rid for rid in wanted if await can(db, perm_ctx, permission, resource_type, rid)
    }


async def task_responses(
    db: AsyncSession, perm_ctx: PermissionContext, tasks: Sequence[Task]
) -> list[TaskResponse]:
    """Tasks the caller reads, their subtasks, node and opdracht redacted."""
    tasks = list(tasks)
    subtasks = await readable_ids(
        db, perm_ctx, "task", (s.id for t in tasks for s in t.subtasks)
    )
    nodes = await readable_ids(db, perm_ctx, "corpus_node", (t.node_id for t in tasks))
    opdrachten = await readable_ids(
        db, perm_ctx, "opdracht", (t.opdracht_id for t in tasks)
    )
    responses = []
    for task in tasks:
        response = TaskResponse.model_validate(task)
        response.subtasks = [s for s in response.subtasks if s.id in subtasks]
        if response.node_id not in nodes:
            response.node = None
        if response.opdracht_id not in opdrachten:
            response.opdracht = None
        responses.append(response)
    return responses


async def task_response(
    db: AsyncSession, perm_ctx: PermissionContext, task: Task
) -> TaskResponse:
    """One task the caller reads, redacted like :func:`task_responses`."""
    return (await task_responses(db, perm_ctx, [task]))[0]


async def opdracht_responses(
    db: AsyncSession, perm_ctx: PermissionContext, opdrachten: Sequence[Opdracht]
) -> list[OpdrachtResponse]:
    """Opdrachten the caller reads, with only the nodes they read."""
    opdrachten = list(opdrachten)
    nodes = await readable_ids(
        db,
        perm_ctx,
        "corpus_node",
        [o.instrument_id for o in opdrachten]
        + [k.node_id for o in opdrachten for k in o.node_koppelingen],
    )
    responses = []
    for opdracht in opdrachten:
        response = OpdrachtResponse.model_validate(opdracht)
        response.node_koppelingen = [
            k for k in response.node_koppelingen if k.node_id in nodes
        ]
        if response.instrument_id not in nodes:
            response.instrument = None
        responses.append(response)
    return responses


async def opdracht_response(
    db: AsyncSession, perm_ctx: PermissionContext, opdracht: Opdracht
) -> OpdrachtResponse:
    """One opdracht the caller reads, redacted like :func:`opdracht_responses`."""
    return (await opdracht_responses(db, perm_ctx, [opdracht]))[0]


async def redact_lead_detail(
    db: AsyncSession, perm_ctx: PermissionContext, response: LeadDetailResponse
) -> LeadDetailResponse:
    """A lead the caller reads, with only the linked nodes they read."""
    nodes = await readable_ids(
        db, perm_ctx, "corpus_node", (ln.node_id for ln in response.linked_nodes)
    )
    response.linked_nodes = [ln for ln in response.linked_nodes if ln.node_id in nodes]
    return response
