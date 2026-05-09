"""Merge twee OrganisatieEenheid-rijen door alle FK's te rewriten.

The reconciliation merge endpoint used to migrate only three FK columns
(person_organisatie_eenheid, lead, opdracht.opdrachtnemer_eenheid_id) and
then delete the source row. That fails on rows with children (parent_id
RESTRICT) or any FK that wasn't explicitly listed — the BZK row in prod
has sub-DGs, members, eenheid_modules, resource_permissions, etc.

This helper introspects pg_catalog to find every FK column referencing
organisatie_eenheid.id and rewrites them in one transaction. New FK
columns added to other models are picked up automatically.

Dedup-logic for tables with unique constraints (eenheid_module on
organisatie_eenheid_id+module_key, org_naam on eenheid_id+naam,
org_email_domein on organisatie_eenheid_id+domein): pre-delete rows on
the source that would conflict with rows already on the target.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FkRef:
    table: str
    column: str


# Tables with composite unique constraints involving the FK column.
# Maps (table, fk_column) -> list of other columns in the unique constraint.
# Before rewriting source rows to target, we delete source rows whose
# (target_id, other_cols) tuple already exists on target — otherwise
# the rewrite would violate the unique constraint.
_DEDUP_RULES: dict[tuple[str, str], list[str]] = {
    ("eenheid_module", "organisatie_eenheid_id"): ["module"],
    ("organisatie_email_domein", "organisatie_eenheid_id"): ["domein"],
    ("person_organisatie_eenheid", "organisatie_eenheid_id"): ["person_id"],
}

# Tables with a partial unique constraint (WHERE geldig_tot IS NULL).
# At most one active row per eenheid. When merging, close the source's
# active row before rewriting so target's active row stays the canonical one.
_PARTIAL_UNIQUE_TABLES: list[tuple[str, str]] = [
    ("organisatie_eenheid_naam", "eenheid_id"),
    ("organisatie_eenheid_parent", "eenheid_id"),
]


async def _discover_fk_columns(session: AsyncSession) -> list[FkRef]:
    """Return every (table, column) FK that references organisatie_eenheid.id."""
    rows = (
        await session.execute(
            text(
                """
                SELECT
                    cl.relname AS table_name,
                    att.attname AS column_name
                FROM pg_constraint con
                JOIN pg_class cl ON cl.oid = con.conrelid
                JOIN pg_class refcl ON refcl.oid = con.confrelid
                JOIN pg_attribute att ON att.attrelid = con.conrelid
                  AND att.attnum = ANY(con.conkey)
                WHERE con.contype = 'f'
                  AND refcl.relname = 'organisatie_eenheid'
                ORDER BY cl.relname, att.attname
                """
            )
        )
    ).all()
    return [FkRef(table=r.table_name, column=r.column_name) for r in rows]


async def _dedupe_before_rewrite(
    session: AsyncSession,
    fk: FkRef,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
) -> int:
    """Delete source-rows whose composite key already exists on target.

    Returns the number of rows deleted. Without this step the UPDATE
    further down would violate a unique constraint.
    """
    other_cols = _DEDUP_RULES.get((fk.table, fk.column))
    if not other_cols:
        return 0
    on_clauses = " AND ".join(f"src.{c} = tgt.{c}" for c in other_cols)
    sql = text(
        f"DELETE FROM {fk.table} src "  # noqa: S608 — table/cols from whitelist
        f"WHERE src.{fk.column} = :source_id "
        f"AND EXISTS ("
        f"  SELECT 1 FROM {fk.table} tgt "
        f"  WHERE tgt.{fk.column} = :target_id AND {on_clauses}"
        f")"
    )
    result = await session.execute(
        sql, {"source_id": source_id, "target_id": target_id}
    )
    n = result.rowcount or 0
    if n:
        log.info(
            "Merge dedup: %d %s row(s) on source had a target-twin, deleted",
            n,
            fk.table,
        )
    return n


async def _close_source_active_row(
    session: AsyncSession,
    table: str,
    fk_col: str,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
) -> int:
    """Close source's active row if target already has an active row.

    Both organisatie_eenheid_naam and organisatie_eenheid_parent enforce
    'one active row per eenheid' via a partial unique index. Naive UPDATE
    of fk_col would put two active rows on target. Solution: end the
    source's active row first (geldig_tot=today). The historical
    geldig_tot rows on source can then be rewritten safely.
    """
    target_has_active = (
        await session.execute(
            text(
                f"SELECT 1 FROM {table} "  # noqa: S608
                f"WHERE {fk_col} = :target_id AND geldig_tot IS NULL LIMIT 1"
            ),
            {"target_id": target_id},
        )
    ).first()
    if not target_has_active:
        return 0
    result = await session.execute(
        text(
            f"UPDATE {table} SET geldig_tot = CURRENT_DATE "  # noqa: S608
            f"WHERE {fk_col} = :source_id AND geldig_tot IS NULL"
        ),
        {"source_id": source_id},
    )
    return result.rowcount or 0


async def _dedupe_resource_permission(
    session: AsyncSession, source_id: uuid.UUID, target_id: uuid.UUID
) -> int:
    """resource_permission has a polymorphic FK and a separate FK column.

    There are two angles here:
      1. resource_permission.organisatie_eenheid_id (the FK column) — if this
         is set, the row is *attached to* an eenheid via permission-context.
         Unique on (resource_type, resource_id, person_id) does NOT involve
         this column directly.
      2. resource_permission.resource_id — when resource_type='organisatie_eenheid'
         this points at an eenheid too. Rewrite that as well.
    """
    n = 0
    # Angle 1: dedupe on (resource_type, resource_id, person_id) when both
    # source and target have a permission for the same resource+person.
    result = await session.execute(
        text(
            "DELETE FROM resource_permission src "
            "WHERE src.organisatie_eenheid_id = :source_id "
            "AND EXISTS ("
            "  SELECT 1 FROM resource_permission tgt "
            "  WHERE tgt.organisatie_eenheid_id = :target_id "
            "  AND tgt.resource_type = src.resource_type "
            "  AND tgt.resource_id = src.resource_id "
            "  AND tgt.person_id IS NOT DISTINCT FROM src.person_id"
            ")"
        ),
        {"source_id": source_id, "target_id": target_id},
    )
    n += result.rowcount or 0

    # Angle 2: rewrite resource_id where resource_type='organisatie_eenheid'.
    # This is not picked up by the FK-introspection (no FK constraint).
    await session.execute(
        text(
            "UPDATE resource_permission SET resource_id = :target_id "
            "WHERE resource_type = 'organisatie_eenheid' "
            "AND resource_id = :source_id"
        ),
        {"source_id": source_id, "target_id": target_id},
    )
    return n


async def _columns_exist(session: AsyncSession, table: str, columns: list[str]) -> bool:
    """Return True if the table has all named columns in the public schema."""
    rows = (
        await session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :t "
                "AND column_name = ANY(:cols)"
            ),
            {"t": table, "cols": columns},
        )
    ).all()
    return len(rows) == len(columns)


async def _rewrite_polymorphic_resource_ids(
    session: AsyncSession, source_id: uuid.UUID, target_id: uuid.UUID
) -> None:
    """Tables with polymorphic (resource_type, resource_id) columns.

    These have no FK to organisatie_eenheid but logically reference it.
    Verify columns exist in the schema first — calling UPDATE on a
    non-existent column aborts the postgres transaction even when wrapped
    in try/except (asyncpg behavior).
    """
    polymorphic_targets = [
        ("stakeholder_assessment", "scope_type", "scope_id", "organisatie_eenheid"),
        ("activity", "resource_type", "resource_id", "organisatie_eenheid"),
        ("notification", "resource_type", "resource_id", "organisatie_eenheid"),
    ]
    for table, type_col, id_col, type_value in polymorphic_targets:
        if not await _columns_exist(session, table, [type_col, id_col]):
            continue
        await session.execute(
            text(
                f"UPDATE {table} SET {id_col} = :target_id "  # noqa: S608
                f"WHERE {type_col} = :type_value "
                f"AND {id_col} = :source_id"
            ),
            {
                "source_id": source_id,
                "target_id": target_id,
                "type_value": type_value,
            },
        )


async def merge_organisatie_eenheden(
    session: AsyncSession, source_id: uuid.UUID, target_id: uuid.UUID
) -> dict[str, int]:
    """Move every reference from source to target, then delete source.

    Returns a dict {table: rows_rewritten} for telemetry. Caller is
    responsible for committing — this function only flushes.
    """
    if source_id == target_id:
        raise ValueError("source en target zijn dezelfde rij")

    fks = await _discover_fk_columns(session)
    log.info("Merge %s -> %s: %d FK columns gevonden", source_id, target_id, len(fks))

    rewritten: dict[str, int] = {}
    for fk in fks:
        # Skip the self-FK on organisatie_eenheid.parent_id when source itself
        # is one of those rows — handled separately to avoid setting parent
        # to a row that is about to be deleted, or to itself.
        if fk.table == "organisatie_eenheid" and fk.column == "parent_id":
            # Children of source -> target. After this, source has no children
            # so the RESTRICT FK won't block the delete.
            result = await session.execute(
                text(
                    "UPDATE organisatie_eenheid SET parent_id = :target_id "
                    "WHERE parent_id = :source_id AND id <> :source_id"
                ),
                {"source_id": source_id, "target_id": target_id},
            )
            n = result.rowcount or 0
            if n:
                rewritten[f"{fk.table}.{fk.column}"] = n
                log.info("  parent_id: %d children verhuisd", n)
            continue

        if fk.table == "resource_permission" and fk.column == "organisatie_eenheid_id":
            await _dedupe_resource_permission(session, source_id, target_id)
            result = await session.execute(
                text(
                    "UPDATE resource_permission "
                    "SET organisatie_eenheid_id = :target_id "
                    "WHERE organisatie_eenheid_id = :source_id"
                ),
                {"source_id": source_id, "target_id": target_id},
            )
            n = result.rowcount or 0
            if n:
                rewritten[f"{fk.table}.{fk.column}"] = n
            continue

        if (fk.table, fk.column) in _PARTIAL_UNIQUE_TABLES:
            await _close_source_active_row(
                session, fk.table, fk.column, source_id, target_id
            )

        await _dedupe_before_rewrite(session, fk, source_id, target_id)

        result = await session.execute(
            text(
                f"UPDATE {fk.table} SET {fk.column} = :target_id "  # noqa: S608
                f"WHERE {fk.column} = :source_id"
            ),
            {"source_id": source_id, "target_id": target_id},
        )
        n = result.rowcount or 0
        if n:
            rewritten[f"{fk.table}.{fk.column}"] = n

    await _rewrite_polymorphic_resource_ids(session, source_id, target_id)

    # Now safe to delete the source row — all FKs point at target.
    await session.execute(
        text("DELETE FROM organisatie_eenheid WHERE id = :source_id"),
        {"source_id": source_id},
    )
    await session.flush()

    log.info("Merge %s -> %s klaar: %s", source_id, target_id, rewritten)
    return rewritten
