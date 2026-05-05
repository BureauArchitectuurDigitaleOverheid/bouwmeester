"""add people:update permission

Revision ID: e3a91c4bd2f7
Revises: c1d4e7a3b9f2
Create Date: 2026-05-05 06:00:00.000000

Splits the people:manage permission so non-admin users can edit basic
fields (naam, functie, emails, phones, org placements) without being
able to delete people, manage agents, or rotate API keys. The route
``PUT /api/people/{id}`` and the email/phone/placement mutations now
require people:update; sensitive mutations (delete, agent toggle, API
key rotate) keep their existing people:manage / AdminUser gates.

Granted to viewer, editor, unit_manager, ministry_admin, super_admin.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e3a91c4bd2f7"
down_revision: str | None = "c1d4e7a3b9f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NEW_PERMISSION = ("people:update", "people")

_ROLE_GRANTS = [
    "viewer",
    "editor",
    "unit_manager",
    "ministry_admin",
    "super_admin",
]


def upgrade() -> None:
    permission_table = sa.table(
        "permission",
        sa.column("id", sa.String()),
        sa.column("category", sa.String()),
    )
    op.bulk_insert(
        permission_table,
        [{"id": _NEW_PERMISSION[0], "category": _NEW_PERMISSION[1]}],
    )

    role_permission_table = sa.table(
        "role_permission",
        sa.column("role_id", sa.String()),
        sa.column("permission_id", sa.String()),
    )
    op.bulk_insert(
        role_permission_table,
        [{"role_id": rid, "permission_id": _NEW_PERMISSION[0]} for rid in _ROLE_GRANTS],
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM role_permission WHERE permission_id = :pid"),
        {"pid": _NEW_PERMISSION[0]},
    )
    bind.execute(
        sa.text("DELETE FROM permission WHERE id = :pid"),
        {"pid": _NEW_PERMISSION[0]},
    )
