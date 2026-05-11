"""Merge twee OrganisatieEenheid-rijen door alle FK's te rewriten.

Vindt via pg_catalog elke FK-kolom die naar organisatie_eenheid.id wijst en
rewrite die in één transactie. Nieuwe FK-kolommen in toekomstige models
worden automatisch opgepakt.

Drie soorten unique-handling, want naïef UPDATE faalt op:

  * Composite unique (eenheid_module.uq op (OE_id, module)): pre-delete
    source-rijen waarvan (target_id, other_cols) al op target bestaat.
  * Partial unique 'één actief per FK' (org_naam, org_parent met
    WHERE geldig_tot IS NULL): sluit source's actieve rij af voordat
    de UPDATE een tweede actieve op target zou creëren.
  * Partial unique 'één actief per (FK, group)' (person_organisatie met
    WHERE eind_datum IS NULL): per group_col (person_id): sluit source's
    actieve rij af alleen waar target ook een actief heeft. Historische
    rijen blijven met hun eigen eind_datum, krijgen alleen OE_id rewrite.

Buiten de FK-graph zitten nog twee polymorphic-tabellen die logisch ook
naar organisatie_eenheid kunnen wijzen via (resource_type, resource_id):
resource_permission (wordt apart afgehandeld omdat het beide angles in
één rij heeft) en activity/notification/stakeholder_assessment (kolommen-
bestaan-check eerst — asyncpg aborteert anders de transactie).
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


# Tables with a regular composite UNIQUE constraint over the FK column.
# Maps (table, fk_column) -> list of other columns in the unique tuple.
# Pre-rewrite we delete source rows whose (target_id, other_cols) tuple
# already exists on target — otherwise the UPDATE would violate the unique.
# Only use for non-partial uniques. Partial uniques go through
# _PARTIAL_PER_GROUP_TABLES, NOT here, because partial uniques don't restrict
# historical (eind_datum/geldig_tot non-null) rows that we want to keep.
# eenheid_module: uq_eenheid_module on (organisatie_eenheid_id, module)
_DEDUP_RULES: dict[tuple[str, str], list[str]] = {
    ("eenheid_module", "organisatie_eenheid_id"): ["module"],
}

# Tables with a partial unique 'one active row per <fk>' (WHERE geldig_tot
# IS NULL). When merging, close source's active row if target already has
# one. Historical rows on source are rewritten unchanged.
_PARTIAL_UNIQUE_BY_FK: list[tuple[str, str]] = [
    ("organisatie_eenheid_naam", "eenheid_id"),
    ("organisatie_eenheid_parent", "eenheid_id"),
]

# Tables with a partial unique 'one active row per (fk, group_col)'
# (WHERE eind_datum IS NULL). E.g. person_organisatie_eenheid:
# uq_active_placement on (person_id, organisatie_eenheid_id) WHERE
# eind_datum IS NULL. Per group_col-value on source: if target has an
# active row for that group, close source's active row instead of
# letting two collide. Historical rows are rewritten as-is.
_PARTIAL_UNIQUE_PER_GROUP: list[tuple[str, str, str, str]] = [
    # (table, fk_col, group_col, eind_col)
    ("person_organisatie_eenheid", "organisatie_eenheid_id", "person_id", "eind_datum"),
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


async def _close_source_active_per_group(
    session: AsyncSession,
    table: str,
    fk_col: str,
    group_col: str,
    eind_col: str,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
) -> int:
    """Close source's active row PER group_col-value if target has one.

    For person_organisatie_eenheid: partial unique (person_id, OE_id) WHERE
    eind_datum IS NULL. Per person: if target already has an active placement
    AND source has an active placement, close the source's eind_datum to
    today so they don't collide on rewrite. Historical placements on source
    (eind_datum already set) are kept and just get their OE_id rewritten.
    """
    sql = text(
        f"UPDATE {table} SET {eind_col} = CURRENT_DATE "  # noqa: S608
        f"WHERE {fk_col} = :source_id "
        f"AND {eind_col} IS NULL "
        f"AND EXISTS ("
        f"  SELECT 1 FROM {table} tgt "
        f"  WHERE tgt.{fk_col} = :target_id "
        f"  AND tgt.{eind_col} IS NULL "
        f"  AND tgt.{group_col} = {table}.{group_col}"
        f")"
    )
    result = await session.execute(
        sql, {"source_id": source_id, "target_id": target_id}
    )
    return result.rowcount or 0


async def _dedupe_and_rewrite_resource_permission(
    session: AsyncSession, source_id: uuid.UUID, target_id: uuid.UUID
) -> int:
    """resource_permission heeft twee verschillende referentie-vormen.

    Echte unique: (person_id, organisatie_eenheid_id, resource_type,
    resource_id, rol). Mijn dedup moet álle vijf velden meetellen, inclusief
    rol — anders verlies ik permissions waar source en target verschillende
    rollen hebben op dezelfde resource.

    Twee plekken waar OE-id kan zitten:
      A. organisatie_eenheid_id (FK column) — 'wie krijgt deze permissie'
      B. resource_id when resource_type='organisatie_eenheid' — 'op welke
         resource is de permissie van toepassing'

    Dedup voor beide angles vóór UPDATE, anders krijg je unique-violations.
    Returns: aantal dedupes (informatief).
    """
    n = 0
    # Angle A: source.organisatie_eenheid_id = source_id wordt target_id.
    # Dedupe op (person_id, target_id, resource_type, resource_id, rol).
    result = await session.execute(
        text(
            "DELETE FROM resource_permission src "
            "WHERE src.organisatie_eenheid_id = :source_id "
            "AND EXISTS ("
            "  SELECT 1 FROM resource_permission tgt "
            "  WHERE tgt.organisatie_eenheid_id = :target_id "
            "  AND tgt.resource_type = src.resource_type "
            "  AND tgt.resource_id = src.resource_id "
            "  AND tgt.rol = src.rol "
            "  AND tgt.person_id IS NOT DISTINCT FROM src.person_id"
            ")"
        ),
        {"source_id": source_id, "target_id": target_id},
    )
    n += result.rowcount or 0
    await session.execute(
        text(
            "UPDATE resource_permission SET organisatie_eenheid_id = :target_id "
            "WHERE organisatie_eenheid_id = :source_id"
        ),
        {"source_id": source_id, "target_id": target_id},
    )

    # Angle B: source.resource_id (where resource_type='organisatie_eenheid')
    # wordt target_id. Dedupe op (person_id, organisatie_eenheid_id,
    # 'organisatie_eenheid', target_id, rol).
    result = await session.execute(
        text(
            "DELETE FROM resource_permission src "
            "WHERE src.resource_type = 'organisatie_eenheid' "
            "AND src.resource_id = :source_id "
            "AND EXISTS ("
            "  SELECT 1 FROM resource_permission tgt "
            "  WHERE tgt.resource_type = 'organisatie_eenheid' "
            "  AND tgt.resource_id = :target_id "
            "  AND tgt.rol = src.rol "
            "  AND tgt.person_id IS NOT DISTINCT FROM src.person_id "
            "  AND tgt.organisatie_eenheid_id "
            "      IS NOT DISTINCT FROM src.organisatie_eenheid_id"
            ")"
        ),
        {"source_id": source_id, "target_id": target_id},
    )
    n += result.rowcount or 0
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
            # Behandelt zowel organisatie_eenheid_id (de FK-kolom) als
            # resource_id waar resource_type='organisatie_eenheid'. Inclusief
            # rol in de unique-check zodat rollen niet verloren gaan.
            n = await _dedupe_and_rewrite_resource_permission(
                session, source_id, target_id
            )
            if n:
                rewritten[f"{fk.table}.{fk.column}"] = n
            continue

        if (fk.table, fk.column) in _PARTIAL_UNIQUE_BY_FK:
            await _close_source_active_row(
                session, fk.table, fk.column, source_id, target_id
            )

        for ptable, pfk, pgroup, peind in _PARTIAL_UNIQUE_PER_GROUP:
            if fk.table == ptable and fk.column == pfk:
                await _close_source_active_per_group(
                    session, ptable, pfk, pgroup, peind, source_id, target_id
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
