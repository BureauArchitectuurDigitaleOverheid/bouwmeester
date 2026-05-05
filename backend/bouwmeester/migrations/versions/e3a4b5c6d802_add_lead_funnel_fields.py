"""add lead funnel fields

Revision ID: e3a4b5c6d802
Revises: d2f5a1b8c947
Create Date: 2026-05-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e3a4b5c6d802"
down_revision: str | None = "d2f5a1b8c947"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "lead",
        sa.Column(
            "engagement_type",
            sa.String(),
            nullable=True,
            comment=(
                "intern_oppakken|voorbereiden_eigen_team|betrokken_houden|"
                "verkenning|nog_te_bepalen"
            ),
        ),
    )
    op.add_column("lead", sa.Column("score_strategisch", sa.Integer(), nullable=True))
    op.add_column("lead", sa.Column("score_politiek", sa.Integer(), nullable=True))
    op.add_column("lead", sa.Column("score_positie", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("lead", "score_positie")
    op.drop_column("lead", "score_politiek")
    op.drop_column("lead", "score_strategisch")
    op.drop_column("lead", "engagement_type")
