"""add rol to initiatief_eenheid

Revision ID: 7491883fe128
Revises: aec85cc29d54
Create Date: 2026-03-29 10:48:38.564073

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7491883fe128"
down_revision: str | None = "aec85cc29d54"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "initiatief_eenheid",
        sa.Column(
            "rol",
            sa.String(),
            server_default="contributor",
            nullable=False,
            comment="eigenaar|contributor|viewer",
        ),
    )


def downgrade() -> None:
    op.drop_column("initiatief_eenheid", "rol")
