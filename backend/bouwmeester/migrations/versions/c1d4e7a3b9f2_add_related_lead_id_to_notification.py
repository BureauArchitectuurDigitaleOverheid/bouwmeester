"""add related_lead_id to notification

Revision ID: c1d4e7a3b9f2
Revises: aa5f2d126436
Create Date: 2026-05-04 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1d4e7a3b9f2"
down_revision: str | None = "aa5f2d126436"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notification",
        sa.Column("related_lead_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "notification_related_lead_id_fkey",
        "notification",
        "lead",
        ["related_lead_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_notification_related_lead_id",
        "notification",
        ["related_lead_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_notification_related_lead_id", table_name="notification")
    op.drop_constraint(
        "notification_related_lead_id_fkey", "notification", type_="foreignkey"
    )
    op.drop_column("notification", "related_lead_id")
