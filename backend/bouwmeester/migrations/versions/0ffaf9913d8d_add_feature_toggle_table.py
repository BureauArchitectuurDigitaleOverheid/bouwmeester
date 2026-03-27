"""add feature_toggle table

Revision ID: 0ffaf9913d8d
Revises: b1e3f5a7c9d2
Create Date: 2026-03-26 22:54:56.019010

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0ffaf9913d8d"
down_revision: str | None = "b1e3f5a7c9d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feature_toggle",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("organisatie_eenheid_id", sa.UUID(), nullable=False),
        sa.Column("feature_key", sa.String(), nullable=False),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organisatie_eenheid_id"], ["organisatie_eenheid.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organisatie_eenheid_id",
            "feature_key",
            name="uq_feature_toggle_eenheid_key",
        ),
    )
    op.create_index(
        op.f("ix_feature_toggle_organisatie_eenheid_id"),
        "feature_toggle",
        ["organisatie_eenheid_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_feature_toggle_organisatie_eenheid_id"), table_name="feature_toggle"
    )
    op.drop_table("feature_toggle")
