"""The rules for creating a task or changing what it links to.

One place for ``POST /tasks``, ``PUT /tasks/{id}``, the chat's
``create_task`` tool and the follow-up tasks of a parliamentary review, so
they cannot drift apart.  Each function raises like ``core.authz.require``
(401, 403, or 404 for a refused read).
"""

from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.authz import require
from bouwmeester.core.permissions import PermissionContext
from bouwmeester.services.agent_rules import require_may_assign

# (body field, permission, resource type): each record a task links to must
# be one the caller may use.  The node, the opdracht and the parlementair
# item must be visible; a parent task is changed by adding a subtask, so it
# needs task:update.
_LINKS: tuple[tuple[str, str, str], ...] = (
    ("node_id", "node:read", "corpus_node"),
    ("opdracht_id", "opdracht:read", "opdracht"),
    ("parent_id", "task:update", "task"),
    ("parlementair_item_id", "parlementair:read", "parlementair_item"),
)


def _sent(data: BaseModel) -> dict[str, UUID]:
    """The link fields sent in the body with a value."""
    return {
        field: getattr(data, field)
        for field, _, _ in _LINKS
        if field in data.model_fields_set and getattr(data, field) is not None
    }


async def require_task_links(
    db: AsyncSession, perm_ctx: PermissionContext, data: BaseModel
) -> None:
    """Every record a task body links to must be one the caller may use.

    Only fields sent in the body are checked (a ``TaskCreate`` or
    ``TaskUpdate``).
    """
    sent = _sent(data)
    for field, permission, resource_type in _LINKS:
        if field in sent:
            await require(db, perm_ctx, permission, resource_type, sent[field])


async def require_task_create(
    db: AsyncSession, perm_ctx: PermissionContext, data: BaseModel
) -> None:
    """May the caller create this task: its links, its place, its assignee.

    A task belongs to its eenheid, or to its node when it has none.
    """
    await require_task_links(db, perm_ctx, data)
    await require(db, perm_ctx, "task:create", "task", place=data)
    await require_may_assign(db, perm_ctx, data)
