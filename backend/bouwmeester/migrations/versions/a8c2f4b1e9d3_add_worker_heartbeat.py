"""add worker_heartbeat table

Revision ID: a8c2f4b1e9d3
Revises: 1fe90cecedd9
Create Date: 2026-05-06 22:00:00.000000

Per worker-loop een rij met laatste tick-tijd en status, zodat de admin-UI
kan tonen of de loops draaien zonder dat operators in container-logs hoeven
te graven.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a8c2f4b1e9d3"
down_revision: str | None = "1fe90cecedd9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker_heartbeat",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("loop_name", sa.String(), nullable=False),
        sa.Column(
            "status", sa.String(), nullable=False, server_default=sa.text("'ok'")
        ),
        sa.Column("detail", sa.String(), nullable=True),
        sa.Column(
            "last_tick_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("loop_name", name="uq_worker_heartbeat_loop_name"),
    )


def downgrade() -> None:
    op.drop_table("worker_heartbeat")
