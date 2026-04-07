"""add person naam indexes for duplicate detection

Revision ID: aa5f2d126436
Revises: 172298f378c4
Create Date: 2026-04-07 20:09:33.589427

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "aa5f2d126436"
down_revision: str | None = "172298f378c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Functional B-tree index on lowercased trimmed name for GROUP BY / exact
    # match queries in the duplicate detection endpoints.
    op.execute(
        "CREATE INDEX ix_person_naam_lower "
        "ON person (lower(trim(naam))) "
        "WHERE is_active = true"
    )

    # Trigram GIN index for regex word-boundary matching (~*) used by the
    # duplicate check on person creation.  Requires pg_trgm (already enabled).
    op.execute(
        "CREATE INDEX ix_person_naam_trgm "
        "ON person USING gin (naam gin_trgm_ops) "
        "WHERE is_active = true"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_person_naam_trgm")
    op.execute("DROP INDEX IF EXISTS ix_person_naam_lower")
