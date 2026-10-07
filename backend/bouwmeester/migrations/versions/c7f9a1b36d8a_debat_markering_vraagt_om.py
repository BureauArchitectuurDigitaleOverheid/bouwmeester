"""What a question asks for on paper

A member who asks for a letter, an overview or a report asks a question
that is answered with paper. `vraagt_om` says what, on the row of the
question. By when it is asked goes into `termijn`, which is there.

Nullable and without a default: adding it does not rewrite the table, and
the questions that are there asked for nothing as far as anyone looked.

Revision ID: c7f9a1b36d8a
Revises: b6e8f0a25c79
Create Date: 2026-10-07

"""

import sqlalchemy as sa
from alembic import op

revision: str = "c7f9a1b36d8a"
down_revision: str | None = "b6e8f0a25c79"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "debat_markering", sa.Column("vraagt_om", sa.String(64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("debat_markering", "vraagt_om")
