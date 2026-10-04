"""Remember which channel belongs to which debate

The start button under a convocatie sets up a channel for that debate. This
table remembers which channel that is, so a second press points to the
existing channel instead of creating another one.

The unique key on (activiteit_id, team_id) is also the lock: the row is
inserted before the channel is created.

Revision ID: e2b5a8c41d76
Revises: c4e7b19f2a83
Create Date: 2026-10-04

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e2b5a8c41d76"
down_revision: str | None = "c4e7b19f2a83"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "debat_sessie",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("activiteit_id", sa.String(36), nullable=False),
        sa.Column("activiteit_nummer", sa.String(32), nullable=True),
        sa.Column("onderwerp", sa.Text(), nullable=False),
        sa.Column("aanvang", sa.DateTime(timezone=True), nullable=True),
        sa.Column("team_id", sa.String(26), nullable=False),
        sa.Column("channel_id", sa.String(26), nullable=True),
        sa.Column("channel_name", sa.String(64), nullable=True),
        sa.Column("stukken_post_id", sa.String(26), nullable=True),
        sa.Column(
            "parlementair_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("parlementair_item.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("started_by_mattermost_user_id", sa.String(26), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "activiteit_id", "team_id", name="uq_debat_sessie_activiteit"
        ),
        # The name Postgres gives a `unique=True` column, so autogenerate
        # does not see the model's constraint as missing.
        sa.UniqueConstraint("channel_id", name="debat_sessie_channel_id_key"),
    )
    # Postgres does not index a foreign key by itself. Without this,
    # deleting an item scans the whole table to set the reference to NULL.
    op.create_index(
        "ix_debat_sessie_parlementair_item_id",
        "debat_sessie",
        ["parlementair_item_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_debat_sessie_parlementair_item_id", table_name="debat_sessie")
    op.drop_table("debat_sessie")
