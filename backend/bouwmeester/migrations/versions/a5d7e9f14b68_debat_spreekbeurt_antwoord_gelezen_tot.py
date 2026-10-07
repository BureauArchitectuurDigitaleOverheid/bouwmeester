"""Remember how far an answer of the bewindspersoon was read

An answer of the bewindspersoon is read for toezeggingen in windows of about
4,000 characters, a model call each, one or two per round. This column says
how many characters of the turn were read and stored, so the next round
goes on there: a window that was read is not sent again, and one that fails
is tried again by itself.

NULL for every row that is there: nothing was read in windows before.

Revision ID: a5d7e9f14b68
Revises: f4c6d8e03a57
Create Date: 2026-10-07

"""

import sqlalchemy as sa
from alembic import op

revision: str = "a5d7e9f14b68"
down_revision: str | None = "f4c6d8e03a57"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "debat_spreekbeurt",
        sa.Column("antwoord_gelezen_tot", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("debat_spreekbeurt", "antwoord_gelezen_tot")
