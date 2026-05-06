"""Regression guard: every foreign-key column should have an index.

PostgreSQL does not auto-index FKs.  Without an index, any DELETE on the
referenced table forces a sequential scan of the referring table to
honour the ON DELETE rule, and any join that filters on the FK column is
similarly slow.  The fix is cheap (one B-tree per FK) but easy to
forget on new migrations — this test fails the build when an FK column
slips through without a matching index.

The check runs against the live database (so raw-SQL ``op.execute`` index
migrations are captured) and asks: for every FK column, is there an
index whose first column is that FK column?  PK columns and unique
constraints satisfy the requirement implicitly because Postgres backs
both with a B-tree.

If a FK genuinely doesn't need an index, add it to ``_FK_WHITELIST``
with a justification.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# (table, column) pairs where skipping the FK index is intentional.
# Each entry must include a comment with the reason.
#
# Most entries below are "known debt" rather than principled exclusions:
# they're FKs that aren't on a hot query path today (write-only audit
# trails, manager/decider attribution columns, etc.) but should still
# get an index before the referencing tables grow.  Address in a
# follow-up housekeeping PR — empty this list when done.
_FK_WHITELIST: dict[tuple[str, str], str] = {
    # Audit / attribution columns — only read for display, not for filtering.
    ("org_placement_request", "decided_by"): "audit-only column",
    ("person_role", "granted_by_id"): "audit-only column",
    ("shared_access", "shared_by_id"): "audit-only column",
    ("suggested_lead", "reviewed_by_id"): "audit-only column",
    ("mattermost_channel_link", "created_by_id"): "audit-only column",
    # Outcome / link-back columns from suggested_lead — only read after a
    # lead has been approved/matched, never as a filter predicate.
    ("suggested_lead", "approved_lead_id"): "outcome link, read by id only",
    ("suggested_lead", "match_existing_lead_id"): "outcome link, read by id only",
    # Mattermost-post-link columns — small table, joined by post_id (PK)
    # rather than by these FKs.
    ("mattermost_post_link", "lead_activity_id"): "joined via post_id (PK)",
    ("mattermost_post_link", "person_id"): "joined via post_id (PK)",
    ("mattermost_post_link", "suggested_lead_id"): "joined via post_id (PK)",
    # Static reference data, ~30 rows — seq-scan is faster than index.
    ("role_permission", "permission_id"): "small static reference table",
}


_FK_INVENTORY_QUERY = text("""
    SELECT
        c.conrelid::regclass::text AS table_name,
        a.attname AS column_name,
        EXISTS (
            SELECT 1
            FROM pg_index i
            JOIN pg_attribute ia
              ON ia.attrelid = i.indrelid
             AND ia.attnum = i.indkey[0]
            WHERE i.indrelid = c.conrelid
              AND ia.attname = a.attname
        ) AS has_leading_index
    FROM pg_constraint c
    JOIN pg_attribute a
      ON a.attrelid = c.conrelid
     AND a.attnum = ANY(c.conkey)
    WHERE c.contype = 'f'
      AND array_length(c.conkey, 1) = 1
      AND c.connamespace = 'public'::regnamespace
    ORDER BY table_name, column_name
""")


@pytest.mark.asyncio
async def test_every_fk_has_an_index(db_session: AsyncSession):
    """Fail if any FK column lacks a leading-column index.

    Indexes whose leading column matches the FK satisfy the requirement.
    PK columns and unique constraints implicitly count because Postgres
    backs both with a B-tree.
    """
    result = await db_session.execute(_FK_INVENTORY_QUERY)
    offenders: list[str] = []

    for table_name, column_name, has_leading_index in result.all():
        if (table_name, column_name) in _FK_WHITELIST:
            continue
        if not has_leading_index:
            offenders.append(f"{table_name}.{column_name}")

    assert not offenders, (
        "These foreign-key columns are not indexed.  Add ``index=True`` "
        "on the column (or an explicit ``Index(...)`` in ``__table_args__``) "
        "and create a migration with ``op.create_index(..., if_not_exists=True)``.\n"
        "If the index is genuinely unnecessary, whitelist in _FK_WHITELIST with "
        "a justification.\n\n"
        "Missing FK indexes:\n" + "\n".join(f"  - {col}" for col in offenders)
    )


@pytest.mark.asyncio
async def test_whitelist_entries_still_apply(db_session: AsyncSession):
    """Fail if a whitelist entry has been fixed or no longer exists.

    Forces cleanup when the underlying schema changes, so the whitelist
    can't accumulate stale exemptions.
    """
    if not _FK_WHITELIST:
        return

    result = await db_session.execute(_FK_INVENTORY_QUERY)
    rows = {(t, c): has_idx for t, c, has_idx in result.all()}

    obsolete: list[str] = []
    fixed: list[str] = []

    for key in _FK_WHITELIST:
        if key not in rows:
            obsolete.append(f"{key[0]}.{key[1]} — FK no longer exists")
            continue
        if rows[key]:
            fixed.append(f"{key[0]}.{key[1]}")

    assert not obsolete, (
        "Whitelist entries reference removed FKs. Clean up _FK_WHITELIST:\n"
        + "\n".join(f"  - {e}" for e in obsolete)
    )
    assert not fixed, (
        "These whitelist entries are now indexed — remove them from "
        "_FK_WHITELIST:\n" + "\n".join(f"  - {e}" for e in fixed)
    )
