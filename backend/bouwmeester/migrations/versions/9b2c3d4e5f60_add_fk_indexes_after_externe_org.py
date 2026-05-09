"""add FK indexes after externe-org migration

Revision ID: 9b2c3d4e5f60
Revises: 9a1b2c3d4e5f
Create Date: 2026-05-09
"""

from collections.abc import Sequence

from alembic import op

revision: str = "9b2c3d4e5f60"
down_revision: str | None = "9a1b2c3d4e5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_lead_organisatie_eenheid_id"),
        "lead",
        ["organisatie_eenheid_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        op.f("ix_opdracht_opdrachtnemer_eenheid_id"),
        "opdracht",
        ["opdrachtnemer_eenheid_id"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_opdracht_opdrachtnemer_eenheid_id"), table_name="opdracht")
    op.drop_index(op.f("ix_lead_organisatie_eenheid_id"), table_name="lead")
