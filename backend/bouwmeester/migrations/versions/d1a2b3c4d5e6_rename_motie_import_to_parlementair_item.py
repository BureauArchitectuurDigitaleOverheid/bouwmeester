"""rename motie_import to parlementair_item

Revision ID: d1a2b3c4d5e6
Revises: c43f045e002f
Create Date: 2026-02-09 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1a2b3c4d5e6"
down_revision: str | None = "c43f045e002f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Rename table ---
    op.rename_table("motie_import", "parlementair_item")

    # --- Add new columns ---
    op.add_column(
        "parlementair_item",
        sa.Column(
            "type",
            sa.String(),
            nullable=False,
            server_default="motie",
            comment="motie|kamervraag|toezegging|amendement|commissiedebat|schriftelijk_overleg|interpellatie",
        ),
    )
    op.add_column(
        "parlementair_item",
        sa.Column("extra_data", sa.JSON(), nullable=True),
    )
    op.add_column(
        "parlementair_item",
        sa.Column("deadline", sa.Date(), nullable=True),
    )
    op.add_column(
        "parlementair_item",
        sa.Column("ministerie", sa.String(), nullable=True),
    )

    # --- Rename FK column in suggested_edge ---
    op.alter_column(
        "suggested_edge",
        "motie_import_id",
        new_column_name="parlementair_item_id",
    )

    # --- Rename FK column in task ---
    op.alter_column(
        "task",
        "motie_import_id",
        new_column_name="parlementair_item_id",
    )

    # --- Update FK constraints ---
    # suggested_edge FK
    op.drop_constraint(
        "suggested_edge_motie_import_id_fkey",
        "suggested_edge",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "suggested_edge_parlementair_item_id_fkey",
        "suggested_edge",
        "parlementair_item",
        ["parlementair_item_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # task FK
    op.drop_constraint(
        "fk_task_motie_import_id",
        "task",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_task_parlementair_item_id",
        "task",
        "parlementair_item",
        ["parlementair_item_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # --- Rename indexes ---
    op.execute(
        "ALTER INDEX IF EXISTS ix_task_motie_import_id "
        "RENAME TO ix_task_parlementair_item_id"
    )


def downgrade() -> None:
    # --- Rename indexes back ---
    op.execute(
        "ALTER INDEX IF EXISTS ix_task_parlementair_item_id "
        "RENAME TO ix_task_motie_import_id"
    )

    # --- Restore FK constraints ---
    op.drop_constraint(
        "fk_task_parlementair_item_id",
        "task",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_task_motie_import_id",
        "task",
        "motie_import",
        ["parlementair_item_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint(
        "suggested_edge_parlementair_item_id_fkey",
        "suggested_edge",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "suggested_edge_motie_import_id_fkey",
        "suggested_edge",
        "motie_import",
        ["parlementair_item_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # --- Rename FK columns back ---
    op.alter_column(
        "task",
        "parlementair_item_id",
        new_column_name="motie_import_id",
    )
    op.alter_column(
        "suggested_edge",
        "parlementair_item_id",
        new_column_name="motie_import_id",
    )

    # --- Drop new columns ---
    op.drop_column("parlementair_item", "ministerie")
    op.drop_column("parlementair_item", "deadline")
    op.drop_column("parlementair_item", "extra_data")
    op.drop_column("parlementair_item", "type")

    # --- Rename table back ---
    op.rename_table("parlementair_item", "motie_import")
