"""Keep what is said in a turn, and where the reading of the subtitles stands

The timeline posts one message per turn at speaking. The text of the turn,
read from the subtitle track of the stream, is added to that message. A row
keeps the text and how much of it is in the channel; the sessie keeps how
far the subtitles of each part have been read.

Revision ID: b8e5f2a04c63
Revises: f3c6b9d52e87
Create Date: 2026-10-05

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8e5f2a04c63"
down_revision: str | None = "f3c6b9d52e87"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "debat_sessie", sa.Column("ondertitels", postgresql.JSONB(), nullable=True)
    )
    op.add_column("debat_spreekbeurt", sa.Column("kop", sa.Text(), nullable=True))
    op.add_column("debat_spreekbeurt", sa.Column("tekst", sa.Text(), nullable=True))
    op.add_column(
        "debat_spreekbeurt",
        sa.Column(
            "tekst_geplaatst", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )
    op.add_column(
        "debat_spreekbeurt",
        sa.Column("vervolg_post_ids", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("debat_spreekbeurt", "vervolg_post_ids")
    op.drop_column("debat_spreekbeurt", "tekst_geplaatst")
    op.drop_column("debat_spreekbeurt", "tekst")
    op.drop_column("debat_spreekbeurt", "kop")
    op.drop_column("debat_sessie", "ondertitels")
