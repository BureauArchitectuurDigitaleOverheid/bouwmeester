"""Make all datetime columns timezone-aware.

Revision ID: c5b6fca202ea
Revises: cf07d98c02ad
Create Date: 2026-02-09 12:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "c5b6fca202ea"
down_revision = "cf07d98c02ad"
branch_labels = None
depends_on = None

# All (table, column) pairs to convert from TIMESTAMP to TIMESTAMPTZ
COLUMNS = [
    ("task", "created_at"),
    ("task", "updated_at"),
    ("activity", "created_at"),
    ("notification", "created_at"),
    ("person", "created_at"),
    ("corpus_node", "created_at"),
    ("corpus_node", "updated_at"),
    ("corpus_node_status", "created_at"),
    ("corpus_node_title", "created_at"),
    ("edge", "created_at"),
    ("parlementair_item", "imported_at"),
    ("parlementair_item", "reviewed_at"),
    ("parlementair_item", "created_at"),
    ("suggested_edge", "reviewed_at"),
    ("suggested_edge", "created_at"),
    ("mention", "created_at"),
    ("organisatie_eenheid", "created_at"),
    ("organisatie_eenheid_naam", "created_at"),
    ("organisatie_eenheid_parent", "created_at"),
    ("organisatie_eenheid_manager", "created_at"),
    ("person_organisatie_eenheid", "created_at"),
    ("node_stakeholder", "created_at"),
    ("tag", "created_at"),
    ("node_tag", "created_at"),
    ("team", "created_at"),
]


def upgrade() -> None:
    for table, column in COLUMNS:
        op.execute(
            f"ALTER TABLE {table} "
            f"ALTER COLUMN {column} "
            f"TYPE TIMESTAMP WITH TIME ZONE "
            f"USING {column} AT TIME ZONE 'UTC'"
        )


def downgrade() -> None:
    for table, column in COLUMNS:
        op.execute(
            f"ALTER TABLE {table} "
            f"ALTER COLUMN {column} "
            f"TYPE TIMESTAMP WITHOUT TIME ZONE"
        )
