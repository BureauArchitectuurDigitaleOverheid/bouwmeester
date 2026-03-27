"""replace lead tags json with lead_tag table

Revision ID: 91c8f24a28fc
Revises: 16ecb93b7508
Create Date: 2026-03-27 08:20:11.151264

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "91c8f24a28fc"
down_revision: str | None = "16ecb93b7508"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lead_tag",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("lead_id", sa.UUID(), nullable=False),
        sa.Column("tag_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["lead_id"], ["lead.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tag.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lead_id", "tag_id", name="uq_lead_tag"),
    )
    op.create_index(op.f("ix_lead_tag_lead_id"), "lead_tag", ["lead_id"], unique=False)
    op.create_index(op.f("ix_lead_tag_tag_id"), "lead_tag", ["tag_id"], unique=False)
    op.drop_column("lead", "tags")


def downgrade() -> None:
    op.add_column(
        "lead",
        sa.Column(
            "tags",
            postgresql.JSON(astext_type=sa.Text()),
            server_default=sa.text("'[]'::json"),
            autoincrement=False,
            nullable=False,
        ),
    )
    op.drop_index(op.f("ix_lead_tag_tag_id"), table_name="lead_tag")
    op.drop_index(op.f("ix_lead_tag_lead_id"), table_name="lead_tag")
    op.drop_table("lead_tag")
