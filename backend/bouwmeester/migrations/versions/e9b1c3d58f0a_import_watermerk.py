"""Keep the watermark of a feed import across restarts

The import of kamerstukken (tkconv) and of news imports what appeared
after the newest thing it has handled. That moment lived in the memory of
the worker, so a restart put it back to "now" and whatever appeared
between the last round and the restart was never imported. It gets a row
of its own.

The row for tkconv starts two days back. On 6 and 7 October the worker
was restarted about fifteen times by deploys, and documents that appeared
in those gaps were not alerted. Going back two days imports them after
all; what was imported before is recognised by its document number and
skipped.

Revision ID: e9b1c3d58f0a
Revises: d8a0b2c47e9b
Create Date: 2026-10-07

"""

import sqlalchemy as sa
from alembic import op

revision: str = "e9b1c3d58f0a"
down_revision: str | None = "d8a0b2c47e9b"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "import_watermerk",
        sa.Column("bron", sa.String(64), primary_key=True),
        sa.Column("tijdstip", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.execute(
        "INSERT INTO import_watermerk (bron, tijdstip)"
        " VALUES ('tkconv_document', now() - interval '48 hours')"
    )


def downgrade() -> None:
    op.drop_table("import_watermerk")
