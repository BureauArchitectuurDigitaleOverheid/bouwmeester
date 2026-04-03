"""add fcc metadata columns and backfill trigger

Revision ID: f664fc93dcd7
Revises: d91d47089680
Create Date: 2026-04-03 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f664fc93dcd7"
down_revision: str | None = "d91d47089680"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add FCC metadata columns to opdracht
    op.add_column(
        "opdracht",
        sa.Column("fcc_funnelfase", sa.String(), nullable=True),
    )
    op.add_column(
        "opdracht",
        sa.Column("fcc_afdeling", sa.String(), nullable=True),
    )
    op.add_column(
        "opdracht",
        sa.Column("fcc_portfolio", sa.String(), nullable=True),
    )
    op.add_column(
        "opdracht",
        sa.Column("fcc_labels", sa.String(), nullable=True),
    )

    # Indexes for filtering
    op.create_index("ix_opdracht_fcc_funnelfase", "opdracht", ["fcc_funnelfase"])
    op.create_index("ix_opdracht_fcc_afdeling", "opdracht", ["fcc_afdeling"])

    # Force re-sync of all existing FCC opdrachten so the new fields
    # get populated on the next sync cycle.
    op.execute("UPDATE opdracht SET fcc_modified_at = NULL WHERE fcc_id IS NOT NULL")


def downgrade() -> None:
    op.drop_index("ix_opdracht_fcc_afdeling", table_name="opdracht")
    op.drop_index("ix_opdracht_fcc_funnelfase", table_name="opdracht")
    op.drop_column("opdracht", "fcc_labels")
    op.drop_column("opdracht", "fcc_portfolio")
    op.drop_column("opdracht", "fcc_afdeling")
    op.drop_column("opdracht", "fcc_funnelfase")
