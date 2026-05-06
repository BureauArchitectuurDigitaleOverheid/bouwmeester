"""add people:create permission

Revision ID: a1f3c8e7d402
Revises: d9f0a1b2c345
Create Date: 2026-05-06

Splits ``people:manage`` verder zodat editors / unit_managers / viewers
zelf nieuwe personen kunnen aanmaken (typisch via de CreatableSelect bij
het toevoegen van contactpersonen aan een lead). Voor verwijderen,
agent-toggle en API-key rotate blijft ``people:manage`` vereist.

Granted to viewer, editor, unit_manager, ministry_admin, super_admin —
identiek aan de ``people:update`` rolset.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1f3c8e7d402"
down_revision: str | None = "d9f0a1b2c345"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NEW_PERMISSION = ("people:create", "people")

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
