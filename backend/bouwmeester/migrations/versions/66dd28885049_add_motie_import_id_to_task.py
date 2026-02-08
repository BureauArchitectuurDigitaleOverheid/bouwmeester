"""add motie_import_id to task

Revision ID: 66dd28885049
Revises: 2442ad1cfef7
Create Date: 2026-02-08 18:53:08.383712

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "66dd28885049"
down_revision: str | None = "2442ad1cfef7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("task", sa.Column("motie_import_id", sa.UUID(), nullable=True))
    op.create_index(
        op.f("ix_task_motie_import_id"),
        "task",
        ["motie_import_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_task_motie_import_id",
        "task",
        "motie_import",
        ["motie_import_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_task_motie_import_id", "task", type_="foreignkey")
    op.drop_index(op.f("ix_task_motie_import_id"), table_name="task")
    op.drop_column("task", "motie_import_id")
