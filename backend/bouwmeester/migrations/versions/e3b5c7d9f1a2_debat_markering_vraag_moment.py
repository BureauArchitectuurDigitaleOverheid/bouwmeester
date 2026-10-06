"""Keep when in a turn a question was asked

A markering had the start of its turn as its moment. For a speech of ten
minutes that is far from the question, and the subtitle lines say when each
sentence was spoken. The moment of the line the quote begins in is kept
here, so the thread links to the question and a thread that is posted again
links to the same moment.

NULL is a question whose moment is not known: every row from before this
column, and a turn whose text has no lines. Those keep the start of the turn.

Revision ID: e3b5c7d9f1a2
Revises: d1a2b4c86e35
Create Date: 2026-10-06

"""

import sqlalchemy as sa
from alembic import op

revision: str = "e3b5c7d9f1a2"
down_revision: str | None = "d1a2b4c86e35"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "debat_markering",
        sa.Column("vraag_moment", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("debat_markering", "vraag_moment")
