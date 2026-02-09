"""add parent_id to notification for threading

Revision ID: 95d48f56f750
Revises: d1a2b3c4d5e6
Create Date: 2026-02-09 08:39:15.413833

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "95d48f56f750"
down_revision: str | None = "d1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("notification", sa.Column("parent_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_notification_parent_id",
        "notification",
        "notification",
        ["parent_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_notification_parent_id", "notification", type_="foreignkey")
    op.drop_column("notification", "parent_id")
