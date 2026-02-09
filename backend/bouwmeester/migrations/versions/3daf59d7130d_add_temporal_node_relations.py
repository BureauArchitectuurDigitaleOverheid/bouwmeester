"""add temporal node relations title status

Revision ID: 3daf59d7130d
Revises: 4a36da453fd2
Create Date: 2026-02-09 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3daf59d7130d"
down_revision: str | None = "4a36da453fd2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- New temporal tables ---

    op.create_table(
        "corpus_node_title",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("node_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("geldig_van", sa.Date(), nullable=False),
        sa.Column("geldig_tot", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["node_id"],
            ["corpus_node.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_corpus_node_title_node_id",
        "corpus_node_title",
        ["node_id"],
    )
    op.create_index(
        "ix_node_title_active",
        "corpus_node_title",
        ["node_id"],
        unique=True,
        postgresql_where=sa.text("geldig_tot IS NULL"),
    )

    op.create_table(
        "corpus_node_status",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("node_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("geldig_van", sa.Date(), nullable=False),
        sa.Column("geldig_tot", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["node_id"],
            ["corpus_node.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_corpus_node_status_node_id",
        "corpus_node_status",
        ["node_id"],
    )
    op.create_index(
        "ix_node_status_active",
        "corpus_node_status",
        ["node_id"],
        unique=True,
        postgresql_where=sa.text("geldig_tot IS NULL"),
    )

    # --- Add geldig_van/geldig_tot to anchor table ---

    op.add_column(
        "corpus_node",
        sa.Column(
            "geldig_van",
            sa.Date(),
            server_default=sa.text("CURRENT_DATE"),
            nullable=False,
        ),
    )
    op.add_column(
        "corpus_node",
        sa.Column("geldig_tot", sa.Date(), nullable=True),
    )

    # --- Data migration: copy existing fields into temporal tables ---

    op.execute(
        """
        INSERT INTO corpus_node_title (node_id, title, geldig_van)
        SELECT id, title, created_at::date
        FROM corpus_node
        """
    )
    op.execute(
        """
        INSERT INTO corpus_node_status (node_id, status, geldig_van)
        SELECT id, status, created_at::date
        FROM corpus_node
        """
    )


def downgrade() -> None:
    # Drop temporal tables
    op.drop_index("ix_node_status_active", table_name="corpus_node_status")
    op.drop_index(
        "ix_corpus_node_status_node_id",
        table_name="corpus_node_status",
    )
    op.drop_table("corpus_node_status")

    op.drop_index("ix_node_title_active", table_name="corpus_node_title")
    op.drop_index(
        "ix_corpus_node_title_node_id",
        table_name="corpus_node_title",
    )
    op.drop_table("corpus_node_title")

    # Remove geldig columns from anchor
    op.drop_column("corpus_node", "geldig_tot")
    op.drop_column("corpus_node", "geldig_van")
