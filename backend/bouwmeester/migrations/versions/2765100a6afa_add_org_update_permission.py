"""Add org:update: edit an eenheid's attributes, scoped to the eenheid

Editing an eenheid (naam, beschrijving, contact details) had no permission
of its own: the route accepted org:manage or managing the eenheid's members
as a workaround.  org:update is that permission.  Held on an eenheid it
applies to everything below it, like every scoped role.

Granted to unit_manager and ministry_admin, and to super_admin, which is
seeded with every permission.  platform_admin is left out on purpose: it
operates the platform and holds no org:manage either.

Revision ID: 2765100a6afa
Revises: d1a6f3b8c925
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2765100a6afa"
down_revision: str | None = "d1a6f3b8c925"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PERMISSION = ("org:update", "org")
_ROLE_GRANTS = ["unit_manager", "ministry_admin", "super_admin"]


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO permission (id, category) VALUES (:pid, :cat) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"pid": _PERMISSION[0], "cat": _PERMISSION[1]},
    )
    for role_id in _ROLE_GRANTS:
        bind.execute(
            sa.text(
                "INSERT INTO role_permission (role_id, permission_id) "
                "VALUES (:rid, :pid) ON CONFLICT DO NOTHING"
            ),
            {"rid": role_id, "pid": _PERMISSION[0]},
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM role_permission WHERE permission_id = :pid"),
        {"pid": _PERMISSION[0]},
    )
    bind.execute(
        sa.text("DELETE FROM permission WHERE id = :pid"),
        {"pid": _PERMISSION[0]},
    )
