"""add lead search vector

Revision ID: b1e3f5a7c9d2
Revises: 74d499ccc116
Create Date: 2026-03-26 22:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1e3f5a7c9d2"
down_revision: str | None = "74d499ccc116"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # lead: title (A) + description (B) + organization (B)
    op.execute("""
        ALTER TABLE lead
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('dutch', coalesce(title, '')), 'A') ||
            setweight(to_tsvector('dutch', coalesce(description, '')), 'B') ||
            setweight(to_tsvector('dutch', coalesce(organization, '')), 'B')
        ) STORED
    """)
    op.execute("""
        CREATE INDEX ix_lead_search
        ON lead USING GIN (search_vector)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_lead_search")
    op.execute("ALTER TABLE lead DROP COLUMN IF EXISTS search_vector")
