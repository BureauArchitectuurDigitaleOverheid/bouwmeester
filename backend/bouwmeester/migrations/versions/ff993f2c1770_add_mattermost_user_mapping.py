"""add mattermost user mapping

Revision ID: ff993f2c1770
Revises: 77ef3f614d36
Create Date: 2026-02-15 14:45:47.558733

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ff993f2c1770"
down_revision: str | None = "77ef3f614d36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mattermost_user",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("person_id", sa.UUID(), nullable=False),
        sa.Column(
            "mattermost_user_id",
            sa.String(length=26),
            nullable=False,
        ),
        sa.Column(
            "mattermost_username",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mattermost_user_id"),
        sa.UniqueConstraint("person_id"),
    )
    op.create_table(
        "mattermost_link_code",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("person_id", sa.UUID(), nullable=False),
        sa.Column(
            "code",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )


def downgrade() -> None:
    op.drop_table("mattermost_link_code")
    op.drop_table("mattermost_user")
