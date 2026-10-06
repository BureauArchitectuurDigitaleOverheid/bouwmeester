"""Remember which kind of turn an event of the timeline became part of

Debat Direct often gives someone who gets the floor two events seconds
apart: first as interrupter, then as speaker. That is one turn, and the kind
of the turn is that of the event that came last. The rows stay what they
are, the memory of the events seen; which turn a row went into is kept next
to it.

NULL is a row that is its own kind, which is every row from before this
column and nearly every row after it.

Revision ID: d1a2b4c86e35
Revises: c9f1a3b75d24
Create Date: 2026-10-06

"""

import sqlalchemy as sa
from alembic import op

revision: str = "d1a2b4c86e35"
down_revision: str | None = "c9f1a3b75d24"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "debat_spreekbeurt",
        sa.Column("beurt_soort", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("debat_spreekbeurt", "beurt_soort")
