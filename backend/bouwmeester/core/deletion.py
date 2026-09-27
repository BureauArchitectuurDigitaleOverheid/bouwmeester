"""One rule for deleting a record and everything that hangs on it.

Deleting X is allowed only if the caller may delete X *and* every record the
delete would remove or detach (through ORM cascades, ``ON DELETE CASCADE`` /
``SET NULL`` foreign keys, or a polymorphic reference without a foreign key)
is accounted for:

- a record that is part of X goes with it (a node's title history, a lead's
  activities, the resource roles on X);
- an independent record (a task, an opdracht, a lead) is removed only when
  the caller may delete that record too; otherwise the delete is refused
  with 409 and a count of what still hangs there;
- a link row that belongs to another record (a lead's link to a node) is
  removed only when the caller may update that other record, else 409;
- a ``SET NULL`` is allowed only where the emptied column does not decide
  who may see or change the record (audit log, notifications, history
  pointers).  Nothing is left behind in a broader scope.

Usage, from a DELETE route whose own permission is already checked::

    await delete_guarded(db, perm_ctx, "corpus_node", node_id)

Every foreign key into a table the walk can reach needs an entry in
``_FK_RULES`` (``tests/test_deletion.py`` and the walk itself fail
otherwise).  Polymorphic references without a foreign key (``_SCOPED``)
go with the record they point at.
"""

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Table, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.authz import can, prefetch
from bouwmeester.core.database import Base
from bouwmeester.core.permissions import PermissionContext
from bouwmeester.core.storage import delete_blob
from bouwmeester.models.bron_bijlage import BronBijlage
from bouwmeester.models.github_link import GitHubLink
from bouwmeester.models.lead_attachment import LeadAttachment
from bouwmeester.models.mattermost_channel_link import MattermostChannelLink
from bouwmeester.models.mattermost_post_link import MattermostPostLink
from bouwmeester.models.mention import Mention
from bouwmeester.models.parlementair_abonnement import ParlementairAbonnement
from bouwmeester.models.parlementair_item import ParlementairItem, SuggestedEdge
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.signaalcontext import Signaalcontext
from bouwmeester.models.stakeholder_assessment import StakeholderAssessment


@dataclass(frozen=True)
class Part:
    """Goes with its parent: no check of its own."""


@dataclass(frozen=True)
class Owned:
    """An independent record: removed only if the caller may delete it."""

    permission: str
    resource_type: str


@dataclass(frozen=True)
class Link:
    """A row that belongs to the record in *other_column*: removing it is a
    change to that record, so the caller must be allowed to make it."""

    other_column: str
    permission: str
    resource_type: str


@dataclass(frozen=True)
class Detach:
    """``SET NULL`` on a column that decides nobody's access."""


_PART = Part()
_DETACH = Detach()

_NODE_SUBTYPES = (
    "dossier",
    "doel",
    "instrument",
    "beleidskader",
    "maatregel",
    "politieke_input",
    "probleem",
    "effect",
    "beleidsoptie",
    "bron",
)

# (child table, foreign key column) -> handling.  See the module docstring.
_FK_RULES: dict[tuple[str, str], Part | Owned | Link | Detach] = {
    **{(t, "id"): _PART for t in _NODE_SUBTYPES},
    ("corpus_node_title", "node_id"): _PART,
    ("corpus_node_status", "node_id"): _PART,
    ("node_tag", "node_id"): _PART,
    # An edge goes with either end (authz: deleting it is node:delete on either).
    ("edge", "from_node_id"): _PART,
    ("edge", "to_node_id"): _PART,
    ("shared_access", "source_node_id"): _PART,
    ("suggested_edge", "target_node_id"): _PART,
    ("task", "node_id"): Owned("task:delete", "task"),
    ("opdracht", "instrument_id"): Owned("opdracht:delete", "opdracht"),
    ("opdracht_node", "node_id"): Link("opdracht_id", "opdracht:update", "opdracht"),
    ("lead_node", "node_id"): Link("lead_id", "lead:update", "lead"),
    # The item's suggested edges go with the node (``_extra_parts``), so
    # nothing is left to review under the broader "no node yet" mandate.
    ("parlementair_item", "corpus_node_id"): _DETACH,
    ("activity", "node_id"): _DETACH,
    ("activity", "task_id"): _DETACH,
    ("activity", "edge_id"): _DETACH,
    ("notification", "related_node_id"): _DETACH,
    ("notification", "related_task_id"): _DETACH,
    ("notification", "related_lead_id"): _DETACH,
    ("bron_bijlage", "bron_id"): _PART,
    ("task", "parent_id"): Owned("task:delete", "task"),
    # A task lives on its node and eenheid, not on the opdracht.
    ("task", "opdracht_id"): _DETACH,
    ("fcc_sync_log", "opdracht_id"): _DETACH,
    ("opdracht_node", "opdracht_id"): _PART,
    # The ORM relationship is passive_deletes="all": it never nulls this.
    ("lead", "initiatief_id"): Owned("lead:delete", "lead"),
    ("initiatief_update", "initiatief_id"): _PART,
    ("lead_column", "initiatief_id"): _PART,
    ("suggested_lead", "initiatief_id"): _PART,
    ("lead_activity", "lead_id"): _PART,
    ("lead_attachment", "lead_id"): _PART,
    ("lead_node", "lead_id"): _PART,
    ("lead_tag", "lead_id"): _PART,
    ("lead_update", "lead_id"): _PART,
    ("suggested_lead", "approved_lead_id"): _DETACH,
    ("suggested_lead", "match_existing_lead_id"): _DETACH,
    ("suggested_edge", "edge_id"): _DETACH,
    ("mattermost_post_link", "lead_activity_id"): _DETACH,
    ("mattermost_post_link", "suggested_lead_id"): _DETACH,
    ("parlementair_treffer", "abonnement_id"): _PART,
    # Grant tables from before resource_permission: still in the schema,
    # no longer mapped or written.  Their rows go with their parent.
    ("initiatief_member", "initiatief_id"): _PART,
    ("lead_contact", "lead_id"): _PART,
    ("node_stakeholder", "node_id"): _PART,
}


_INITIATIEF_OR_LEAD = {"initiatief": "initiatief", "lead": "lead"}
_MENTION_TYPES = {"corpus_node": "node", "task": "task"}

# Polymorphic references without a foreign key: (model, type column, id
# column, {deleted table: value in the type column}).
_SCOPED: tuple[tuple[Any, Any, Any, dict[str, str]], ...] = (
    (
        ResourcePermission,
        ResourcePermission.resource_type,
        ResourcePermission.resource_id,
        {t: t for t in ("corpus_node", "task", "opdracht", "initiatief", "lead")},
    ),
    (
        StakeholderAssessment,
        StakeholderAssessment.scope_type,
        StakeholderAssessment.scope_id,
        {"corpus_node": "corpus_node", "initiatief": "initiatief"},
    ),
    *(
        (model, model.scope_type, model.scope_id, _INITIATIEF_OR_LEAD)
        for model in (
            MattermostChannelLink,
            MattermostPostLink,
            ParlementairAbonnement,
            GitHubLink,
            Signaalcontext,
        )
    ),
    (Mention, Mention.source_type, Mention.source_id, _MENTION_TYPES),
    (Mention, Mention.mention_type, Mention.target_id, _MENTION_TYPES),
)


def _extra_parts(table: str, ids: set[UUID]) -> list[tuple[Table, Any]]:
    """Parts reached through something other than a foreign key to *table*."""
    if table == "corpus_node":
        # The suggested edges of a parlementair item are proposals for edges
        # of the item's node: they go with the node like its edges do.
        return [
            (
                SuggestedEdge.__table__,
                select(SuggestedEdge.id)
                .join(
                    ParlementairItem,
                    ParlementairItem.id == SuggestedEdge.parlementair_item_id,
                )
                .where(ParlementairItem.corpus_node_id.in_(ids)),
            )
        ]
    return []


# Dutch labels for the 409 message, (singular, plural).
_LABELS: dict[str, tuple[str, str]] = {
    "task": ("taak", "taken"),
    "opdracht": ("opdracht", "opdrachten"),
    "lead": ("lead", "leads"),
}


def _tables() -> dict[str, Table]:
    return {t.name: t for t in Base.metadata.sorted_tables}


def referencing_fks(table_name: str) -> list[tuple[Table, Any]]:
    """Every (child table, foreign key column) that points at *table_name*."""
    return [
        (t, fk.parent)
        for t in Base.metadata.sorted_tables
        for fk in t.foreign_keys
        if fk.column.table.name == table_name
    ]


def _pk(table: Table) -> Any | None:
    cols = list(table.primary_key.columns)
    return cols[0] if len(cols) == 1 else None


def reachable_tables(roots: tuple[str, ...]) -> set[str]:
    """The tables whose rows a delete of *roots* can remove, by the rules."""
    seen: set[str] = set()
    todo = list(roots) + [m.__tablename__ for m, *_ in _SCOPED]
    todo.append(SuggestedEdge.__tablename__)
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        for child, col in referencing_fks(name):
            rule = _FK_RULES.get((child.name, col.name))
            if isinstance(rule, Part | Owned):
                todo.append(child.name)
    return seen


@dataclass
class _Plan:
    removed: dict[str, set[UUID]] = field(default_factory=dict)
    # (resource type, permission) -> ids that must pass the check
    checks: dict[tuple[str, str], set[UUID]] = field(default_factory=dict)


async def _walk(db: AsyncSession, plan: _Plan, table: Table, ids: set[UUID]) -> None:
    ids = ids - plan.removed.setdefault(table.name, set())
    if not ids:
        return
    plan.removed[table.name] |= ids

    children: list[tuple[Table, Any]] = []
    for child, col in referencing_fks(table.name):
        rule = _FK_RULES.get((child.name, col.name))
        if rule is None:
            raise RuntimeError(
                f"core.deletion: no rule for {child.name}.{col.name} -> "
                f"{table.name}; add one to _FK_RULES"
            )
        if isinstance(rule, Detach):
            continue
        if isinstance(rule, Link):
            other = child.c[rule.other_column]
            rows = await db.scalars(select(other).where(col.in_(ids)).distinct())
            key = (rule.resource_type, rule.permission)
            plan.checks.setdefault(key, set()).update(rows)
            continue
        pk = _pk(child)
        if pk is None:
            # A row without an id of its own: nothing can hang on it.
            continue
        if isinstance(rule, Owned):
            rows = set(await db.scalars(select(pk).where(col.in_(ids))))
            key = (rule.resource_type, rule.permission)
            plan.checks.setdefault(key, set()).update(rows)
        children.append((child, select(pk).where(col.in_(ids))))

    children.extend(_extra_parts(table.name, ids))
    for model, type_col, id_col, values in _SCOPED:
        if table.name in values:
            children.append(
                (
                    model.__table__,
                    select(model.__table__.c.id).where(
                        type_col == values[table.name], id_col.in_(ids)
                    ),
                )
            )

    for child, stmt in children:
        await _walk(db, plan, child, set(await db.scalars(stmt)))


async def _refusals(
    db: AsyncSession, perm_ctx: PermissionContext, plan: _Plan
) -> dict[str, int]:
    refused: dict[str, int] = {}
    for (resource_type, permission), ids in plan.checks.items():
        # A record removed anyway through another path needs no update right.
        if permission.endswith(":update"):
            ids = ids - plan.removed.get(resource_type, set())
        if not ids:
            continue
        await prefetch(db, perm_ctx, resource_type, list(ids))
        for rid in ids:
            if not await can(db, perm_ctx, permission, resource_type, rid):
                refused[resource_type] = refused.get(resource_type, 0) + 1
    return refused


def _describe(refused: dict[str, int]) -> str:
    parts = []
    for resource_type, n in sorted(refused.items()):
        singular, plural = _LABELS.get(resource_type, (resource_type, resource_type))
        parts.append(f"{n} {singular if n == 1 else plural}")
    return " en ".join([", ".join(parts[:-1]), parts[-1]] if len(parts) > 1 else parts)


async def remove_scoped(db: AsyncSession, removed: dict[str, set[UUID]]) -> None:
    """Remove the polymorphic rows (``_SCOPED``) of records that go.

    *removed* maps a table name to the ids that are deleted.  For a delete
    that bypasses :func:`delete_guarded` because its records move elsewhere
    first (merging leads), so nothing is left pointing at the removed one.
    """
    for model, type_col, id_col, values in _SCOPED:
        for name, value in values.items():
            ids = removed.get(name)
            if ids:
                await db.execute(
                    delete(model).where(type_col == value, id_col.in_(ids))
                )


async def delete_guarded(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    resource_type: str,
    resource_id: UUID,
) -> None:
    """Delete a record under the rule above, or raise 409.

    The caller's right to delete the record itself is checked by the route.
    Stored files of removed bijlagen are deleted after the rows are gone.
    """
    table = _tables()[resource_type]
    plan = _Plan()
    await _walk(db, plan, table, {resource_id})
    refused = await _refusals(db, perm_ctx, plan)
    if refused:
        raise HTTPException(
            status_code=409,
            detail="Kan niet verwijderen: hieraan hangen nog "
            + _describe(refused)
            + " waar je geen rechten op hebt. Verplaats of verwijder die eerst.",
        )
    blob_keys = await _blob_keys(db, plan.removed)

    # Rows without a foreign key to what goes are removed explicitly.  The
    # rest goes through the ORM and the database cascades the plan was built
    # from.
    await remove_scoped(db, plan.removed)
    extra = plan.removed.get(SuggestedEdge.__tablename__)
    if extra:
        await db.execute(delete(SuggestedEdge).where(SuggestedEdge.id.in_(extra)))

    obj = await db.get(_model_for(table), resource_id)
    if obj is not None:
        await db.delete(obj)
    await db.flush()
    for key in blob_keys:
        await delete_blob(key)


async def _blob_keys(db: AsyncSession, removed: dict[str, set[UUID]]) -> list[str]:
    """The stored files behind the bijlagen this delete removes."""
    keys: list[str] = []
    for model in (BronBijlage, LeadAttachment):
        ids = removed.get(model.__tablename__)
        if ids:
            rows = await db.scalars(select(model.pad).where(model.id.in_(ids)))
            keys.extend(k for k in rows if k)
    return keys


def _model_for(table: Table) -> Any:
    for mapper in Base.registry.mappers:
        if mapper.local_table is table:
            return mapper.class_
    raise LookupError(table.name)


__all__ = [
    "delete_guarded",
    "reachable_tables",
    "referencing_fks",
    "remove_scoped",
]
