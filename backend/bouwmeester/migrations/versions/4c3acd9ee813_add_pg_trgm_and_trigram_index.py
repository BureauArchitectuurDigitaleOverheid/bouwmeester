"""add pg_trgm extension and trigram index on corpus_node.title

Revision ID: 4c3acd9ee813
Revises: c4a1f2e83b01
Create Date: 2026-02-17 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4c3acd9ee813"
down_revision: str | None = "c4a1f2e83b01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_corpus_node_title_trgm "
        "ON corpus_node USING gin (title gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_corpus_node_title_trgm")
