"""add ai source fields to resource_permission

Revision ID: 172298f378c4
Revises: f664fc93dcd7
Create Date: 2026-04-06 16:40:16.287966

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "172298f378c4"
down_revision: str | None = "f664fc93dcd7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "resource_permission",
        sa.Column(
            "source",
            sa.String(),
            nullable=True,
            server_default="manual",
            comment="manual|ai",
        ),
    )
    op.add_column(
        "resource_permission",
        sa.Column("ai_confidence", sa.Numeric(precision=3, scale=2), nullable=True),
    )
    op.add_column(
        "resource_permission",
        sa.Column("ai_reason", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "ck_resource_permission_source",
        "resource_permission",
        "source IN ('manual', 'ai')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_resource_permission_source", "resource_permission", type_="check"
    )
    op.drop_column("resource_permission", "ai_reason")
    op.drop_column("resource_permission", "ai_confidence")
    op.drop_column("resource_permission", "source")
