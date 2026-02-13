"""fix search tiptap indexing

Revision ID: a7f3b2c1d9e8
Revises: e1bfb6704ba8
Create Date: 2026-02-13 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7f3b2c1d9e8"
down_revision: str | None = "e1bfb6704ba8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create a PL/pgSQL function that extracts plain text from TipTap JSON.
    # Uses a recursive CTE to walk the content tree and extract text nodes
    # and mention labels. Returns input as-is if it's not valid TipTap JSON.
    op.execute("""
        CREATE OR REPLACE FUNCTION tiptap_to_plain(val text)
        RETURNS text
        LANGUAGE plpgsql
        IMMUTABLE
        AS $$
        DECLARE
            doc jsonb;
            result text;
        BEGIN
            IF val IS NULL OR val = '' THEN
                RETURN coalesce(val, '');
            END IF;

            BEGIN
                doc := val::jsonb;
            EXCEPTION WHEN OTHERS THEN
                RETURN val;
            END;

            IF doc->>'type' != 'doc' THEN
                RETURN val;
            END IF;

            WITH RECURSIVE nodes AS (
                SELECT doc AS node
                UNION ALL
                SELECT child
                FROM nodes, jsonb_array_elements(node->'content') AS child
                WHERE node->'content' IS NOT NULL
            )
            SELECT string_agg(
                CASE
                    WHEN node->>'text' IS NOT NULL THEN node->>'text'
                    WHEN node->>'type' IN ('mention', 'hashtagMention')
                        THEN coalesce(node->'attrs'->>'label', '')
                    ELSE NULL
                END,
                ' '
            )
            INTO result
            FROM nodes
            WHERE node->>'text' IS NOT NULL
               OR node->>'type' IN ('mention', 'hashtagMention');

            RETURN coalesce(result, '');
        END;
        $$
    """)

    # Recreate search_vector on corpus_node using tiptap_to_plain
    op.execute("DROP INDEX IF EXISTS ix_corpus_node_search")
    op.execute("ALTER TABLE corpus_node DROP COLUMN IF EXISTS search_vector")
    op.execute("""
        ALTER TABLE corpus_node
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('dutch', coalesce(title, '')), 'A') ||
            setweight(to_tsvector('dutch', tiptap_to_plain(coalesce(description, ''))), 'B')
        ) STORED
    """)
    op.execute("""
        CREATE INDEX ix_corpus_node_search
        ON corpus_node USING GIN (search_vector)
    """)

    # Recreate search_vector on task using tiptap_to_plain
    op.execute("DROP INDEX IF EXISTS ix_task_search")
    op.execute("ALTER TABLE task DROP COLUMN IF EXISTS search_vector")
    op.execute("""
        ALTER TABLE task
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('dutch', coalesce(title, '')), 'A') ||
            setweight(to_tsvector('dutch', tiptap_to_plain(coalesce(description, ''))), 'B')
        ) STORED
    """)
    op.execute("""
        CREATE INDEX ix_task_search
        ON task USING GIN (search_vector)
    """)


def downgrade() -> None:
    # Restore original corpus_node search_vector (without tiptap_to_plain)
    op.execute("DROP INDEX IF EXISTS ix_corpus_node_search")
    op.execute("ALTER TABLE corpus_node DROP COLUMN IF EXISTS search_vector")
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

    # Restore original task search_vector
    op.execute("DROP INDEX IF EXISTS ix_task_search")
    op.execute("ALTER TABLE task DROP COLUMN IF EXISTS search_vector")
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

    # Drop the function
    op.execute("DROP FUNCTION IF EXISTS tiptap_to_plain(text)")
