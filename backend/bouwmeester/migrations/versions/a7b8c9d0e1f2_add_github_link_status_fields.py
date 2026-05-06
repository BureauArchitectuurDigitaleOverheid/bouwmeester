"""add github_link status fields

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-05-06 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "github_link",
        sa.Column(
            "state",
            sa.String(length=32),
            nullable=True,
            comment="open|closed|merged|draft|completed|failure|...",
        ),
    )
    op.add_column(
        "github_link",
        sa.Column(
            "state_extra",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "github_link",
        sa.Column("etag", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "github_link",
        sa.Column(
            "last_checked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "github_link",
        sa.Column(
            "last_changed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "github_link",
        sa.Column("check_error", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("github_link", "check_error")
    op.drop_column("github_link", "last_changed_at")
    op.drop_column("github_link", "last_checked_at")
    op.drop_column("github_link", "etag")
    op.drop_column("github_link", "state_extra")
    op.drop_column("github_link", "state")
