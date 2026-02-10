"""add http_sessions table

Revision ID: 492a105cdce5
Revises: 94e112019e64
Create Date: 2026-02-10 11:22:41.398588

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "492a105cdce5"
down_revision: str | None = "94e112019e64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "http_sessions",
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index(
        op.f("ix_http_sessions_expires_at"),
        "http_sessions",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_http_sessions_expires_at"), table_name="http_sessions")
    op.drop_table("http_sessions")
