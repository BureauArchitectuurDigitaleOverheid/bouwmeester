"""Remember which Debat Direct debates belong to a sessie, and what was posted

The timeline posts who speaks when, in the channel of a debate. It needs to
know which Debat Direct debates are this activiteit (found on the day
itself), and which events it has already dealt with, so that a restart does
not post a debate twice.

Revision ID: f3c6b9d52e87
Revises: e2b5a8c41d76
Create Date: 2026-10-05

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f3c6b9d52e87"
down_revision: str | None = "e2b5a8c41d76"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "debat_sessie",
        sa.Column("debat_direct_ids", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "debat_sessie", sa.Column("tijdlijn_status", sa.String(20), nullable=True)
    )
    op.add_column(
        "debat_sessie",
        sa.Column(
            "tijdlijn_gecontroleerd_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.create_table(
        "debat_spreekbeurt",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "sessie_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("debat_sessie.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("debat_direct_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("event_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("object_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("post_id", sa.String(26), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "sessie_id",
            "debat_direct_id",
            "event_type",
            "event_start",
            "object_id",
            name="uq_debat_spreekbeurt_event",
        ),
    )
    op.create_index(
        "ix_debat_spreekbeurt_sessie_id", "debat_spreekbeurt", ["sessie_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_debat_spreekbeurt_sessie_id", table_name="debat_spreekbeurt")
    op.drop_table("debat_spreekbeurt")
    op.drop_column("debat_sessie", "tijdlijn_gecontroleerd_at")
    op.drop_column("debat_sessie", "tijdlijn_status")
    op.drop_column("debat_sessie", "debat_direct_ids")
