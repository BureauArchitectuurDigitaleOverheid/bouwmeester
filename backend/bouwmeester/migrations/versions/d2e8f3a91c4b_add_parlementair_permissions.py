"""add parlementair permissions

Revision ID: d2e8f3a91c4b
Revises: c1d4e7a3b9f2
Create Date: 2026-05-04 14:00:00.000000

Adds three new permissions for the parlementair module so the API routes
can be gated:

- ``parlementair:read``    — view imports, get details, view review queue
- ``parlementair:review``  — reject/reopen/complete review, mutate edges
- ``parlementair:import``  — trigger or reprocess imports (LLM-heavy)

The permissions are granted to existing roles via the role_permission
junction table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2e8f3a91c4b"
down_revision: str | None = "c1d4e7a3b9f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NEW_PERMISSIONS = [
    ("parlementair:read", "parlementair"),
    ("parlementair:review", "parlementair"),
    ("parlementair:import", "parlementair"),
]


_ROLE_GRANTS = {
    "super_admin": [p[0] for p in _NEW_PERMISSIONS],
    # platform_admin is infra-only (geen content-permissies in c44e4533e993)
    # — bewust geen parlementair:read of :review.  :import zou analoog aan
    # import_export:import zijn, maar ook dat overlaten aan ministry_admin
    # houdt de rol consistent infra-only.
    "ministry_admin": [
        "parlementair:read",
        "parlementair:review",
        "parlementair:import",
    ],
    "unit_manager": [
        "parlementair:read",
        "parlementair:review",
        "parlementair:import",
    ],
    "editor": ["parlementair:read", "parlementair:review"],
    "viewer": ["parlementair:read"],
}


def upgrade() -> None:
    permission_table = sa.table(
        "permission",
        sa.column("id", sa.String()),
        sa.column("category", sa.String()),
    )
    op.bulk_insert(
        permission_table,
        [{"id": pid, "category": cat} for pid, cat in _NEW_PERMISSIONS],
    )

    role_permission_table = sa.table(
        "role_permission",
        sa.column("role_id", sa.String()),
        sa.column("permission_id", sa.String()),
    )
    rows = [
        {"role_id": role_id, "permission_id": perm_id}
        for role_id, perms in _ROLE_GRANTS.items()
        for perm_id in perms
    ]
    op.bulk_insert(role_permission_table, rows)


def downgrade() -> None:
    perm_ids = [p[0] for p in _NEW_PERMISSIONS]
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM role_permission WHERE permission_id = ANY(:ids)"),
        {"ids": perm_ids},
    )
    bind.execute(
        sa.text("DELETE FROM permission WHERE id = ANY(:ids)"),
        {"ids": perm_ids},
    )
