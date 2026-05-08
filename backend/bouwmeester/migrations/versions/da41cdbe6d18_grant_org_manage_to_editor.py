"""grant org:manage to editor

Revision ID: da41cdbe6d18
Revises: b3c5e7f8d2a1
Create Date: 2026-05-08 19:30:00.000000

Lets editor-role users (Bewerker) create new organisatie-eenheden so
they can add stakeholder org units that fall outside their own
ministry. Update/delete on existing eenheden is still scoped via
check_org_scope; the create endpoint drops the parent scope-check in
the same change set so editors can hang new eenheden anywhere in the
tree. The aanmaker gets an implicit eigenaar resource-permission on
the new eenheid (handled in the route, not this migration).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "da41cdbe6d18"
down_revision: str | None = "61a63e103355"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_GRANT = {"role_id": "editor", "permission_id": "org:manage"}


def upgrade() -> None:
    role_permission_table = sa.table(
        "role_permission",
        sa.column("role_id", sa.String()),
        sa.column("permission_id", sa.String()),
    )
    op.bulk_insert(role_permission_table, [_GRANT])


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM role_permission WHERE role_id = :rid AND permission_id = :pid"
        ),
        {"rid": _GRANT["role_id"], "pid": _GRANT["permission_id"]},
    )
