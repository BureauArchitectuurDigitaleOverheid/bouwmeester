"""add thread_id to notification

Revision ID: cf07d98c02ad
Revises: 3daf59d7130d
Create Date: 2026-02-09 12:39:50.432573

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cf07d98c02ad"
down_revision: str | None = "3daf59d7130d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("notification", sa.Column("thread_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_notification_thread_id",
        "notification",
        "notification",
        ["thread_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_notification_thread_id", "notification", type_="foreignkey")
    op.drop_column("notification", "thread_id")
