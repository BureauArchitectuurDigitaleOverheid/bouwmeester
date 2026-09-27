"""Record who added an email address to a person

The first login links to a contact by verified email and takes over what
the contact holds.  An address added by someone who does not decide about
the contact's placements proves nothing, so the first login through it
holds that access (``core.authority.hold_access_of_unproven_login``).
Existing rows stay NULL: nobody recorded who added them.

Revision ID: a4d2e8f1c7b3
Revises: 7c1e5a9d3b20
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a4d2e8f1c7b3"
down_revision: str | None = "7c1e5a9d3b20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "person_email",
        sa.Column("added_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("person_email", "added_by_id")
