"""The counts under messages that are out of date, as a queue

The count under the message of a turn ("2 vragen, 1 open") is written by
the timeline from now on, for every markering without `statusregel_at`.
Three things for that:

* How often writing a message failed and from when it is tried again, so
  that a message that cannot be written is tried a few times in an hour
  and then left. Nullable and without a default: no rewrite of the table.
* An index on the rows that are out of date. Every round of the timeline
  asks for them, every ten seconds, and they are a handful among all
  markeringen there ever were.
* The rows that are out of date now and older than an hour are marked as
  written. Nobody wrote them in all that time, their debates are over, and
  without this the first round after the deploy would start on every
  message that was ever left behind. Their counts stay what they are until
  someone reacts; the hour is how long a message is tried for.

Revision ID: d8a0b2c47e9b
Revises: c7f9a1b36d8a
Create Date: 2026-10-07

"""

import sqlalchemy as sa
from alembic import op

revision: str = "d8a0b2c47e9b"
down_revision: str | None = "c7f9a1b36d8a"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "debat_markering",
        sa.Column("statusregel_pogingen", sa.Integer(), nullable=True),
    )
    op.add_column(
        "debat_markering",
        sa.Column("statusregel_niet_voor", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE debat_markering SET statusregel_at = now()"
        " WHERE statusregel_at IS NULL AND created_at < now() - interval '1 hour'"
    )
    op.create_index(
        "ix_debat_markering_statusregel_open",
        "debat_markering",
        ["beurt_post_id"],
        postgresql_where=sa.text(
            "statusregel_at IS NULL AND thread_post_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_debat_markering_statusregel_open", table_name="debat_markering")
    op.drop_column("debat_markering", "statusregel_niet_voor")
    op.drop_column("debat_markering", "statusregel_pogingen")
