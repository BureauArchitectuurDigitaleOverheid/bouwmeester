"""add last_seen_at to person

Revision ID: bd2d26333bb6
Revises: 76f60edf7c9c
Create Date: 2026-02-15 10:10:28.868952

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bd2d26333bb6"
down_revision: str | None = "76f60edf7c9c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "person",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_person_last_seen_at", "person", ["last_seen_at"])


def downgrade() -> None:
    op.drop_index("ix_person_last_seen_at", table_name="person")
    op.drop_column("person", "last_seen_at")
