"""add edge_schema_rule table

Revision ID: 7ad2814283b1
Revises: bd2d26333bb6
Create Date: 2026-02-15 11:14:42.766755

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7ad2814283b1"
down_revision: str | None = "bd2d26333bb6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "edge_schema_rule",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("from_node_type", sa.String(length=50), nullable=False),
        sa.Column("to_node_type", sa.String(length=50), nullable=False),
        sa.Column("edge_type_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["edge_type_id"], ["edge_type.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "from_node_type",
            "to_node_type",
            "edge_type_id",
            name="uq_edge_schema_rule",
        ),
    )
    op.create_index(
        op.f("ix_edge_schema_rule_edge_type_id"),
        "edge_schema_rule",
        ["edge_type_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_edge_schema_rule_from_node_type"),
        "edge_schema_rule",
        ["from_node_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_edge_schema_rule_to_node_type"),
        "edge_schema_rule",
        ["to_node_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_edge_schema_rule_to_node_type"),
        table_name="edge_schema_rule",
    )
    op.drop_index(
        op.f("ix_edge_schema_rule_from_node_type"),
        table_name="edge_schema_rule",
    )
    op.drop_index(
        op.f("ix_edge_schema_rule_edge_type_id"),
        table_name="edge_schema_rule",
    )
    op.drop_table("edge_schema_rule")
