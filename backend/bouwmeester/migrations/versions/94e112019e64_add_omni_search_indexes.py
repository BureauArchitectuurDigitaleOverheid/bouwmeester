"""add omni search indexes

Revision ID: 94e112019e64
Revises: c5b6fca202ea
Create Date: 2026-02-09 17:32:29.636637
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "94e112019e64"
down_revision: str | None = "c5b6fca202ea"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # corpus_node: title (A) + description (B)
    op.execute("""
        ALTER TABLE corpus_node
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('dutch', coalesce(title, '')), 'A') ||
            setweight(to_tsvector('dutch', coalesce(description, '')), 'B')
        ) STORED
    """)
    op.execute("""
        CREATE INDEX ix_corpus_node_search
        ON corpus_node USING GIN (search_vector)
    """)

    # task: title (A) + description (B)
    op.execute("""
        ALTER TABLE task
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('dutch', coalesce(title, '')), 'A') ||
            setweight(to_tsvector('dutch', coalesce(description, '')), 'B')
        ) STORED
    """)
    op.execute("""
        CREATE INDEX ix_task_search
        ON task USING GIN (search_vector)
    """)

    # person: naam (A) + functie (B) + email (C)
    op.execute("""
        ALTER TABLE person
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('dutch', coalesce(naam, '')), 'A') ||
            setweight(to_tsvector('dutch', coalesce(functie, '')), 'B') ||
            setweight(to_tsvector('dutch', coalesce(email, '')), 'C')
        ) STORED
    """)
    op.execute("""
        CREATE INDEX ix_person_search
        ON person USING GIN (search_vector)
    """)

    # organisatie_eenheid: naam (A) + beschrijving (B)
    op.execute("""
        ALTER TABLE organisatie_eenheid
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('dutch', coalesce(naam, '')), 'A') ||
            setweight(to_tsvector('dutch', coalesce(beschrijving, '')), 'B')
        ) STORED
    """)
    op.execute("""
        CREATE INDEX ix_org_eenheid_search
        ON organisatie_eenheid USING GIN (search_vector)
    """)

    # parlementair_item: titel (A) + onderwerp (A) + llm_samenvatting (B)
    op.execute("""
        ALTER TABLE parlementair_item
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('dutch', coalesce(titel, '')), 'A') ||
            setweight(to_tsvector('dutch', coalesce(onderwerp, '')), 'A') ||
            setweight(to_tsvector('dutch', coalesce(llm_samenvatting, '')), 'B')
        ) STORED
    """)
    op.execute("""
        CREATE INDEX ix_parlementair_search
        ON parlementair_item USING GIN (search_vector)
    """)

    # tag: name (A) + description (B)
    op.execute("""
        ALTER TABLE tag
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('dutch', coalesce(name, '')), 'A') ||
            setweight(to_tsvector('dutch', coalesce(description, '')), 'B')
        ) STORED
    """)
    op.execute("""
        CREATE INDEX ix_tag_search
        ON tag USING GIN (search_vector)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tag_search")
    op.execute("ALTER TABLE tag DROP COLUMN IF EXISTS search_vector")

    op.execute("DROP INDEX IF EXISTS ix_parlementair_search")
    op.execute("ALTER TABLE parlementair_item DROP COLUMN IF EXISTS search_vector")

    op.execute("DROP INDEX IF EXISTS ix_org_eenheid_search")
    op.execute("ALTER TABLE organisatie_eenheid DROP COLUMN IF EXISTS search_vector")

    op.execute("DROP INDEX IF EXISTS ix_person_search")
    op.execute("ALTER TABLE person DROP COLUMN IF EXISTS search_vector")

    op.execute("DROP INDEX IF EXISTS ix_task_search")
    op.execute("ALTER TABLE task DROP COLUMN IF EXISTS search_vector")

    op.execute("DROP INDEX IF EXISTS ix_corpus_node_search")
    op.execute("ALTER TABLE corpus_node DROP COLUMN IF EXISTS search_vector")
