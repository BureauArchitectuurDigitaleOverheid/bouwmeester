"""add org:create permission for editors

Revision ID: da41cdbe6d18
Revises: 61a63e103355
Create Date: 2026-05-08 19:30:00.000000

Editors (Bewerker) need to add stakeholder org-eenheden from the lead
flow without becoming admins. We introduce a narrow ``org:create``
permission for that, separate from ``org:manage`` which still gates
the Beheer > Organisatie tabs in the frontend. Granted to editor,
unit_manager, ministry_admin, super_admin. The route layer accepts
either org:create or org:manage on the create endpoint; update/delete
keep their existing org:manage gate combined with scope or eigenaar
resource-permission checks.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "da41cdbe6d18"
down_revision: str | None = "61a63e103355"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NEW_PERMISSION = ("org:create", "org")
_ROLE_GRANTS = ["editor", "unit_manager", "ministry_admin", "super_admin"]


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO permission (id, category) VALUES (:pid, :cat) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"pid": _NEW_PERMISSION[0], "cat": _NEW_PERMISSION[1]},
    )
    for role_id in _ROLE_GRANTS:
        bind.execute(
            sa.text(
                "INSERT INTO role_permission (role_id, permission_id) "
                "VALUES (:rid, :pid) ON CONFLICT DO NOTHING"
            ),
            {"rid": role_id, "pid": _NEW_PERMISSION[0]},
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
