"""add dienstverband to org_placement_request

Revision ID: f920a0de4559
Revises: a1c2d3e4f5g6
Create Date: 2026-03-28 12:17:17.815335

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f920a0de4559"
down_revision: str | None = "a1c2d3e4f5g6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "org_placement_request",
        sa.Column(
            "dienstverband",
            sa.String(),
            server_default="in_dienst",
            nullable=False,
            comment="in_dienst|ingehuurd|extern",
        ),
    )


def downgrade() -> None:
    op.drop_column("org_placement_request", "dienstverband")
