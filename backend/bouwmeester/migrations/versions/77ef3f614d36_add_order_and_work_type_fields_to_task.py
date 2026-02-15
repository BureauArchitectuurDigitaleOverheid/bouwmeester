"""add order and work_type fields to task

Revision ID: 77ef3f614d36
Revises: 1cbc1f263552
Create Date: 2026-02-15 15:13:26.021984

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "77ef3f614d36"
down_revision: str | None = "1cbc1f263552"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("task", sa.Column("order", sa.Integer(), nullable=True))
    op.add_column("task", sa.Column("work_type", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("task", "work_type")
    op.drop_column("task", "order")
