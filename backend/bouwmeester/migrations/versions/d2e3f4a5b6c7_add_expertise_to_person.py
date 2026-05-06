"""add expertise to person

Revision ID: d2e3f4a5b6c7
Revises: a1f3c8e7d402
Create Date: 2026-05-06 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2e3f4a5b6c7"
down_revision: str | None = "a1f3c8e7d402"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("person", sa.Column("expertise", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("person", "expertise")
