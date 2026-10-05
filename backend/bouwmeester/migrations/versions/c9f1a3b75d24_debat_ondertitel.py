"""Keep every line of subtitle as a row, with the turn it belongs to

Which turn a line belongs to was decided once, by time, and the text was
glued onto the turn. The events of Debat Direct are seconds off, so at a
change of speaker a line can be under the wrong person, and the voices
decide that later. For that a line has to be able to move.

The text of a turn stays where it is and becomes derived: the lines of the
turn in order. A turn that already has text gets that text as one line at
its own moment, so nothing that is in a channel changes.

Voices are not in here. They are kept in the memory of the worker for as
long as a debate runs, and nowhere else.

Revision ID: c9f1a3b75d24
Revises: a7d4e1c93b52
Create Date: 2026-10-05

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9f1a3b75d24"
down_revision: str | None = "a7d4e1c93b52"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "debat_ondertitel",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("sessie_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("debat_direct_id", sa.String(length=36), nullable=False),
        sa.Column("start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("einde", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tekst", sa.Text(), nullable=False),
        sa.Column("spreekbeurt_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "toewijzing", sa.String(length=8), server_default="tijd", nullable=False
        ),
        sa.Column(
            "stem_klaar", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["sessie_id"], ["debat_sessie.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["spreekbeurt_id"], ["debat_spreekbeurt.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sessie_id", "debat_direct_id", "start", name="uq_debat_ondertitel_start"
        ),
    )
    op.create_index("ix_debat_ondertitel_sessie_id", "debat_ondertitel", ["sessie_id"])
    op.create_index(
        "ix_debat_ondertitel_spreekbeurt_id", "debat_ondertitel", ["spreekbeurt_id"]
    )
    op.add_column(
        "debat_spreekbeurt",
        sa.Column("tekst_geplaatst_hash", sa.String(length=16), nullable=True),
    )
    # A line is put behind the event it follows, so of the rows of one
    # moment only the last one has text: two of these never collide.
    op.execute(
        """
        INSERT INTO debat_ondertitel
            (sessie_id, debat_direct_id, start, einde, tekst, spreekbeurt_id,
             stem_klaar)
        SELECT sessie_id, debat_direct_id, event_start, event_start, tekst, id, true
        FROM debat_spreekbeurt
        WHERE tekst IS NOT NULL AND tekst <> ''
        ON CONFLICT ON CONSTRAINT uq_debat_ondertitel_start DO NOTHING
        """
    )


def downgrade() -> None:
    # The text of every turn is still on its row.
    op.drop_column("debat_spreekbeurt", "tekst_geplaatst_hash")
    op.drop_index("ix_debat_ondertitel_spreekbeurt_id", table_name="debat_ondertitel")
    op.drop_index("ix_debat_ondertitel_sessie_id", table_name="debat_ondertitel")
    op.drop_table("debat_ondertitel")
