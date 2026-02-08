"""merge rol into functie remove afdeling

Revision ID: a091233f3214
Revises: 61c6590ad60c
Create Date: 2026-02-08 16:33:49.160258

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a091233f3214"
down_revision: str | None = "61c6590ad60c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Copy rol values into functie (where functie is currently empty)
    op.execute("UPDATE person SET functie = rol WHERE rol IS NOT NULL")
    op.drop_column("person", "afdeling")
    op.drop_column("person", "rol")


def downgrade() -> None:
    op.add_column(
        "person",
        sa.Column("rol", sa.VARCHAR(), autoincrement=False, nullable=True),
    )
    op.add_column(
        "person",
        sa.Column("afdeling", sa.VARCHAR(), autoincrement=False, nullable=True),
    )
    op.execute("UPDATE person SET rol = functie")
