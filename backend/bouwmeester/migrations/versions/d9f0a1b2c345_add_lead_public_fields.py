"""add public-publication fields to lead

Revision ID: d9f0a1b2c345
Revises: c8e9f01a2b34
Create Date: 2026-05-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d9f0a1b2c345"
down_revision: str | None = "c8e9f01a2b34"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "lead",
        sa.Column(
            "public_visible",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column("lead", sa.Column("public_title", sa.String(), nullable=True))
    op.add_column("lead", sa.Column("public_summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("lead", "public_summary")
    op.drop_column("lead", "public_title")
    op.drop_column("lead", "public_visible")
