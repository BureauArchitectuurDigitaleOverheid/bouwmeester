"""Do not read the chairman's closing list of debates that are over

When a part of a debate has ended, the worker looks once at the closing
words of the chairman for the list of toezeggingen, and keeps that it
looked in `beoordeeld_at` of the row of the end. Until now nothing set
that for a row of the end, so on the first round after this is deployed
every debate that is still followed would have its list read, and replies
would turn up under the end of debates of hours ago.

The rows of the end that are there count as looked at. Only a debate that
ends from here on has its list read.

Revision ID: b6e8f0a25c79
Revises: a5d7e9f14b68
Create Date: 2026-10-07

"""

from alembic import op

revision: str = "b6e8f0a25c79"
down_revision: str | None = "a5d7e9f14b68"
branch_labels: str | None = None
depends_on: str | None = None

MARK_ENDED_AS_LOOKED_AT = (
    "UPDATE debat_spreekbeurt SET beoordeeld_at = now()"
    " WHERE event_type = 'debate_end' AND beoordeeld_at IS NULL"
)


def upgrade() -> None:
    op.execute(MARK_ENDED_AS_LOOKED_AT)


def downgrade() -> None:
    # Which rows were marked here is not kept, and a row that counts as
    # looked at does no harm to the code from before.
    pass
