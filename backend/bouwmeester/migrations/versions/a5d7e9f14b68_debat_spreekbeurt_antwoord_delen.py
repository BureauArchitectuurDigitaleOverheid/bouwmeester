"""Remember how far a long answer of the bewindspersoon was read

An answer over 12,000 characters is read for toezeggingen in parts, a model
call each. All parts within the time one turn gets did not fit: a slow
model made the whole turn fail, the retry began at the first part again,
and after a few tries the turn was given up on with nothing stored. Now a
round reads one part and stores what it holds, and this column says which
part is next.

0 for every row that is there: nothing was read in parts before.

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
        sa.Column(
            "antwoord_delen_gelezen",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("debat_spreekbeurt", "antwoord_delen_gelezen")
