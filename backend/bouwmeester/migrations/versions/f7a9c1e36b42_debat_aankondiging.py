"""Remember which debates were announced for which initiatief

A debate can be announced in the channels of an initiatief, from the
Signalen tab. The row is what the reminder of the day itself is sent from,
and what the tab lists.

Revision ID: f7a9c1e36b42
Revises: e9b1c3d58f0a
Create Date: 2026-10-09

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f7a9c1e36b42"
down_revision: str | None = "e9b1c3d58f0a"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "debat_aankondiging",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "initiatief_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("initiatief.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("activiteit_id", sa.String(36), nullable=False),
        sa.Column("activiteit_nummer", sa.String(32), nullable=True),
        sa.Column("soort", sa.String(128), nullable=True),
        sa.Column("onderwerp", sa.Text(), nullable=False),
        sa.Column("commissie", sa.Text(), nullable=True),
        sa.Column("aanvang", sa.DateTime(timezone=True), nullable=True),
        sa.Column("einde", sa.DateTime(timezone=True), nullable=True),
        sa.Column("channel_id", sa.String(26), nullable=True),
        sa.Column(
            "stand",
            sa.String(20),
            nullable=False,
            server_default="aangekondigd",
        ),
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("person.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "initiatief_id", "activiteit_id", name="uq_debat_aankondiging_activiteit"
        ),
    )
    op.create_index(
        "ix_debat_aankondiging_initiatief_id",
        "debat_aankondiging",
        ["initiatief_id"],
    )
    op.create_index(
        "ix_debat_aankondiging_created_by_id",
        "debat_aankondiging",
        ["created_by_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_debat_aankondiging_created_by_id", table_name="debat_aankondiging"
    )
    op.drop_index(
        "ix_debat_aankondiging_initiatief_id", table_name="debat_aankondiging"
    )
    op.drop_table("debat_aankondiging")
