"""add eenheid_module table

Revision ID: da29f7a85818
Revises: 7491883fe128
Create Date: 2026-03-29 12:49:32.374811

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "da29f7a85818"
down_revision: str | None = "7491883fe128"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "eenheid_module",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("organisatie_eenheid_id", sa.UUID(), nullable=False),
        sa.Column(
            "module",
            sa.String(),
            nullable=False,
            comment="corpus|taken|leads|initiatieven|opdrachten",
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organisatie_eenheid_id"],
            ["organisatie_eenheid.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organisatie_eenheid_id", "module", name="uq_eenheid_module"
        ),
    )
    op.create_index(
        "ix_eenheid_module_organisatie_eenheid_id",
        "eenheid_module",
        ["organisatie_eenheid_id"],
    )


def downgrade() -> None:
    op.drop_table("eenheid_module")
