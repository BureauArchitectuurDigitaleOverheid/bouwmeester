"""tiptap json to markdown

Rewrites every rich-text column that holds a TipTap document into the markdown
`nldd-text-editor` reads and writes. Mentions survive as links with a scheme
(`[@Anne](user:<id>)`), so no reference to a person, node or task is lost.

Values that are not TipTap documents are left exactly as they are, which is most
of them: these columns hold a mix of JSON, markdown and plain text depending on
when they were written.

Reversible in shape but not in substance: `downgrade()` cannot rebuild the
original JSON, because markdown does not record which of several TipTap
documents produced it. It therefore refuses rather than corrupting data
silently. The way back is a database restore.

Revision ID: 6b1e04a7c8d2
Revises: 54ec9a7df491
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from bouwmeester.core.tiptap_markdown import tiptap_to_markdown

revision = "6b1e04a7c8d2"
down_revision = "54ec9a7df491"
branch_labels = None
depends_on = None

# (table, column) for every field the app edits with a rich-text editor, taken
# from the RichTextEditor / RichTextFormField call sites in the frontend.
#
# Deliberately NOT included: the *_attachment.content_type columns (MIME types),
# fcc_sync_log.error_message (machine-written), and bron/parlementair summary
# fields, which are produced by an LLM as plain markdown already.
COLUMNS: list[tuple[str, str]] = [
    ("corpus_node", "description"),
    ("task", "description"),
    ("lead", "description"),
    ("lead_activity", "content"),
    ("lead_update", "body_internal"),
    ("lead_update", "body_public"),
    ("initiatief", "beschrijving"),
    ("initiatief_update", "body"),
    ("opdracht", "beschrijving"),
    ("organisatie_eenheid", "beschrijving"),
    ("samenwerkingsverband", "beschrijving"),
    ("person", "description"),
    ("notification", "message"),
]


def _existing_columns(bind: sa.engine.Connection) -> set[tuple[str, str]]:
    """What this database actually has.

    The list above spans features that arrived at different times, so an older
    database legitimately lacks some of them. Skipping a missing column beats
    failing the whole migration over a table that was never created here.
    """
    rows = bind.execute(
        sa.text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public'"
        )
    ).fetchall()
    return {(row[0], row[1]) for row in rows}


def upgrade() -> None:
    bind = op.get_bind()
    present = _existing_columns(bind)

    for table, column in COLUMNS:
        if (table, column) not in present:
            continue

        # Only the rows that could be TipTap. A JSON document always starts with
        # `{`, so this skips the bulk of plain-text rows without loading them.
        rows = bind.execute(
            sa.text(
                f"SELECT id, {column} FROM {table} "  # noqa: S608 - names are literals above
                f"WHERE {column} IS NOT NULL AND ltrim({column}) LIKE '{{%'"
            )
        ).fetchall()

        for row_id, value in rows:
            converted = tiptap_to_markdown(value)
            if converted == value:
                continue
            bind.execute(
                sa.text(
                    f"UPDATE {table} SET {column} = :value WHERE id = :id"  # noqa: S608
                ),
                {"value": converted, "id": row_id},
            )


def downgrade() -> None:
    raise RuntimeError(
        "Kan niet terug: markdown legt niet vast welk TipTap-document het ooit was. "
        "Zet een back-up terug om deze migratie ongedaan te maken."
    )
