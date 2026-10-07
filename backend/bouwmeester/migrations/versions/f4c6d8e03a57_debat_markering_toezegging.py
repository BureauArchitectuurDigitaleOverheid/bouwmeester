"""Keep by when a toezegging was promised, and which question it answers

A toezegging of the bewindspersoon is a markering like a question and a
motie, with two things of its own. `termijn` is the moment that was named,
as it was said ("voor het kerstreces"): text, not a date, because nothing in
the debate says which year or which reces. `bij_volgnummer` is the number of
the question in the same debate that the toezegging answers, which the
reply shows as "bij vraag 12".

Both are NULL for every row that is there, and for every question and
motie from here on.

Revision ID: f4c6d8e03a57
Revises: e3b5c7d92f46
Create Date: 2026-10-07

"""

import sqlalchemy as sa
from alembic import op

revision: str = "f4c6d8e03a57"
down_revision: str | None = "e3b5c7d92f46"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("debat_markering", sa.Column("termijn", sa.Text(), nullable=True))
    op.add_column(
        "debat_markering", sa.Column("bij_volgnummer", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("debat_markering", "bij_volgnummer")
    op.drop_column("debat_markering", "termijn")
