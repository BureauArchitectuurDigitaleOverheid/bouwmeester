"""add access_request table

Revision ID: 408967f9dc7c
Revises: bcfeec6929b2
Create Date: 2026-02-12 19:11:41.575168

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "408967f9dc7c"
down_revision: str | None = "bcfeec6929b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "access_request",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("naam", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("reviewed_by_id", sa.UUID(), nullable=True),
        sa.Column("deny_reason", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["reviewed_by_id"],
            ["person.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_access_request_email", "access_request", ["email"])
    op.create_index(
        "uq_access_request_pending_email",
        "access_request",
        ["email"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("uq_access_request_pending_email", table_name="access_request")
    op.drop_index("ix_access_request_email", table_name="access_request")
    op.drop_table("access_request")
