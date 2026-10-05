"""Remember what was marked in a debate, and where each markering stands

A question to the bewindspersoon becomes a thread under the turn at speaking
it was asked in. The row is the question as a state: the list of open rows
is what the model gets with every next turn, so the same question is not
marked twice. A later turn that comes back to a question is a vermelding on
it instead of a new row.

Revision ID: a7d4e1c93b52
Revises: f3c6b9d52e87
Create Date: 2026-10-05

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7d4e1c93b52"
down_revision: str | None = "f3c6b9d52e87"
branch_labels: str | None = None
depends_on: str | None = None


def _id() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "debat_markering",
        _id(),
        sa.Column(
            "sessie_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("debat_sessie.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "spreekbeurt_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("debat_spreekbeurt.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("beurt_sleutel", sa.String(255), nullable=False),
        sa.Column("volgnummer", sa.Integer(), nullable=False),
        sa.Column("soort", sa.String(32), nullable=False, server_default="vraag"),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("channel_id", sa.String(26), nullable=False),
        sa.Column("beurt_post_id", sa.String(26), nullable=True),
        sa.Column("thread_post_id", sa.String(26), nullable=True),
        sa.Column("post_pogingen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("statusregel_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("spreker", sa.Text(), nullable=False),
        sa.Column("fractie", sa.String(64), nullable=True),
        sa.Column("gericht_aan", sa.String(255), nullable=False),
        sa.Column("citaat", sa.Text(), nullable=False),
        sa.Column("samenvatting", sa.Text(), nullable=False),
        sa.Column("stuk", sa.Text(), nullable=True),
        sa.Column("moment", sa.DateTime(timezone=True), nullable=False),
        sa.Column("moment_url", sa.Text(), nullable=True),
        _created_at(),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # Also the index on sessie_id: it is the first column.
        sa.UniqueConstraint(
            "sessie_id", "volgnummer", name="uq_debat_markering_volgnummer"
        ),
    )
    op.create_index(
        "ix_debat_markering_spreekbeurt_id", "debat_markering", ["spreekbeurt_id"]
    )
    op.create_index(
        "ix_debat_markering_beurt_post_id", "debat_markering", ["beurt_post_id"]
    )

    op.create_table(
        "debat_markering_vermelding",
        _id(),
        sa.Column(
            "markering_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("debat_markering.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sessie_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("debat_sessie.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "spreekbeurt_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("debat_spreekbeurt.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("beurt_sleutel", sa.String(255), nullable=False),
        sa.Column("soort", sa.String(32), nullable=False, server_default="herhaling"),
        sa.Column("beurt_post_id", sa.String(26), nullable=True),
        sa.Column("spreker", sa.Text(), nullable=False),
        sa.Column("fractie", sa.String(64), nullable=True),
        sa.Column("citaat", sa.Text(), nullable=False),
        sa.Column("moment", sa.DateTime(timezone=True), nullable=False),
        sa.Column("moment_url", sa.Text(), nullable=True),
        _created_at(),
    )
    op.create_index(
        "ix_debat_markering_vermelding_markering_id",
        "debat_markering_vermelding",
        ["markering_id"],
    )
    op.create_index(
        "ix_debat_markering_vermelding_sessie_id",
        "debat_markering_vermelding",
        ["sessie_id"],
    )
    op.create_index(
        "ix_debat_markering_vermelding_spreekbeurt_id",
        "debat_markering_vermelding",
        ["spreekbeurt_id"],
    )


def downgrade() -> None:
    op.drop_table("debat_markering_vermelding")
    op.drop_table("debat_markering")
