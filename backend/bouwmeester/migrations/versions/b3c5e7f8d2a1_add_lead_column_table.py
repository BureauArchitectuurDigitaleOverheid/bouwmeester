"""add lead_column table and seed defaults

Revision ID: b3c5e7f8d2a1
Revises: a8c2f4b1e9d3
Create Date: 2026-05-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3c5e7f8d2a1"
down_revision: str | None = "a8c2f4b1e9d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_DEFAULT_COLUMNS: list[dict] = [
    {
        "slug": "inbox",
        "name": "Inbox",
        "color": "bg-indigo-100 text-indigo-800",
        "is_active_stage": False,
        "is_public_visible": False,
    },
    {
        "slug": "verkennen",
        "name": "Verkennen",
        "color": "bg-blue-100 text-blue-800",
        "is_active_stage": True,
        "is_public_visible": False,
    },
    {
        "slug": "eerste_gesprek",
        "name": "Eerste gesprek",
        "color": "bg-yellow-100 text-yellow-800",
        "is_active_stage": True,
        "is_public_visible": True,
    },
    {
        "slug": "interne_check",
        "name": "Interne check",
        "color": "bg-orange-100 text-orange-800",
        "is_active_stage": True,
        "is_public_visible": True,
    },
    {
        "slug": "follow_up",
        "name": "Follow-up",
        "color": "bg-purple-100 text-purple-800",
        "is_active_stage": True,
        "is_public_visible": True,
    },
    {
        "slug": "in_the_pocket",
        "name": "In the pocket",
        "color": "bg-green-100 text-green-800",
        "is_active_stage": False,
        "is_public_visible": True,
    },
    {
        "slug": "koelkast",
        "name": "Koelkast",
        "color": "bg-gray-100 text-gray-800",
        "is_active_stage": False,
        "is_public_visible": False,
    },
]


def upgrade() -> None:
    # Composite index op lead.(initiatief_id, stage). Versnelt de
    # per-initiatief stage-filter (kanban-board, metrics, GROUP BY stage,
    # en de "non-active stage" subquery in de overdue/stale filters).
    op.create_index(
        "ix_lead_initiatief_stage",
        "lead",
        ["initiatief_id", "stage"],
        unique=False,
    )

    op.create_table(
        "lead_column",
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("initiatief_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "color",
            sa.String(),
            nullable=False,
            server_default="bg-gray-100 text-gray-800",
        ),
        sa.Column(
            "is_active_stage",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "is_public_visible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["initiatief_id"], ["initiatief.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "initiatief_id", "slug", name="uq_lead_column_initiatief_slug"
        ),
        sa.UniqueConstraint(
            "initiatief_id", "name", name="uq_lead_column_initiatief_name"
        ),
    )
    op.create_index(
        op.f("ix_lead_column_initiatief_id"),
        "lead_column",
        ["initiatief_id"],
        unique=False,
    )
    op.create_index(
        "ix_lead_column_initiatief_sort",
        "lead_column",
        ["initiatief_id", "sort_order"],
        unique=False,
    )

    # Seed every existing initiatief with the 7 default columns. Idempotent
    # via ON CONFLICT — safe to re-run after a partial migration.
    bind = op.get_bind()
    initiatief_ids = bind.execute(sa.text("SELECT id FROM initiatief")).all()
    insert_stmt = sa.text(
        """
        INSERT INTO lead_column
            (initiatief_id, name, slug, sort_order, color,
             is_active_stage, is_public_visible)
        VALUES
            (:initiatief_id, :name, :slug, :sort_order, :color,
             :is_active_stage, :is_public_visible)
        ON CONFLICT (initiatief_id, slug) DO NOTHING
        """
    )
    for (initiatief_id,) in initiatief_ids:
        for idx, default in enumerate(_DEFAULT_COLUMNS):
            bind.execute(
                insert_stmt,
                {
                    "initiatief_id": initiatief_id,
                    "name": default["name"],
                    "slug": default["slug"],
                    "sort_order": idx,
                    "color": default["color"],
                    "is_active_stage": default["is_active_stage"],
                    "is_public_visible": default["is_public_visible"],
                },
            )


def downgrade() -> None:
    op.drop_index("ix_lead_column_initiatief_sort", table_name="lead_column")
    op.drop_index(op.f("ix_lead_column_initiatief_id"), table_name="lead_column")
    op.drop_table("lead_column")
    op.drop_index("ix_lead_initiatief_stage", table_name="lead")
