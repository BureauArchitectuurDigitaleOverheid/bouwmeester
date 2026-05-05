"""add initiatief_update table for publication posts

Revision ID: b6d7e8f90135
Revises: a5c6d7e8f024
Create Date: 2026-05-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b6d7e8f90135"
down_revision: str | None = "a5c6d7e8f024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "initiatief_update",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("initiatief_id", sa.UUID(), nullable=False),
        sa.Column("titel", sa.String(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["initiatief_id"], ["initiatief.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["published_by_id"], ["person.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_initiatief_update_initiatief_id"),
        "initiatief_update",
        ["initiatief_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_initiatief_update_published_at"),
        "initiatief_update",
        ["published_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_initiatief_update_published_at"),
        table_name="initiatief_update",
    )
    op.drop_index(
        op.f("ix_initiatief_update_initiatief_id"),
        table_name="initiatief_update",
    )
    op.drop_table("initiatief_update")
