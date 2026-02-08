"""add person description field for agents

Revision ID: e89fa2717ecf
Revises: c451e5edf43d
Create Date: 2026-02-08 16:43:59.985518

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e89fa2717ecf"
down_revision: str | None = "c451e5edf43d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("person", sa.Column("description", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("person", "description")
