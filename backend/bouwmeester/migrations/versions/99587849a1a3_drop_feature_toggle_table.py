"""drop feature_toggle table

Revision ID: 99587849a1a3
Revises: c44e4533e993
Create Date: 2026-03-28 15:04:19.395974

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "99587849a1a3"
down_revision: str | None = "c44e4533e993"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("feature_toggle")


def downgrade() -> None:
    op.create_table(
        "feature_toggle",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "organisatie_eenheid_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("feature_key", sa.String(), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["organisatie_eenheid_id"],
            ["organisatie_eenheid.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organisatie_eenheid_id",
            "feature_key",
            name="uq_feature_toggle_eenheid_key",
        ),
    )
