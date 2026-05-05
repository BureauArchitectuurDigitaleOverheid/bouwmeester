"""add evaluatie activity fields to lead_activity

Revision ID: f4b5c6d7e913
Revises: e3a4b5c6d802
Create Date: 2026-05-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f4b5c6d7e913"
down_revision: str | None = "e3a4b5c6d802"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("lead_activity", sa.Column("uitkomst", sa.Text(), nullable=True))
    op.add_column("lead_activity", sa.Column("vervolgacties", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("lead_activity", "vervolgacties")
    op.drop_column("lead_activity", "uitkomst")
