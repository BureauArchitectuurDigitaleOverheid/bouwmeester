"""add lead_update table

Revision ID: 61a63e103355
Revises: b3c5e7f8d2a1
Create Date: 2026-05-08 14:10:23.084133

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "61a63e103355"
down_revision: str | None = "b3c5e7f8d2a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lead_update",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("lead_id", sa.UUID(), nullable=False),
        sa.Column("titel", sa.String(), nullable=False),
        sa.Column("body_internal", sa.Text(), nullable=True),
        sa.Column("body_public", sa.Text(), nullable=True),
        sa.Column("mail_subject", sa.String(), nullable=True),
        sa.Column("mail_to", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("mail_cc", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("source_raw_text", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by_id", sa.UUID(), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["person.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["lead_id"], ["lead.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["published_by_id"], ["person.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_lead_update_lead_id"), "lead_update", ["lead_id"], unique=False
    )
    op.create_index(
        op.f("ix_lead_update_published_at"),
        "lead_update",
        ["published_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_lead_update_published_by_id"),
        "lead_update",
        ["published_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_lead_update_created_by_id"),
        "lead_update",
        ["created_by_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_lead_update_created_by_id"), table_name="lead_update")
    op.drop_index(op.f("ix_lead_update_published_by_id"), table_name="lead_update")
    op.drop_index(op.f("ix_lead_update_published_at"), table_name="lead_update")
    op.drop_index(op.f("ix_lead_update_lead_id"), table_name="lead_update")
    op.drop_table("lead_update")
