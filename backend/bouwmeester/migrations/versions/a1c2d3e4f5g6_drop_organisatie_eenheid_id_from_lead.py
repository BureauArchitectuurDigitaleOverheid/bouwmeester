"""drop organisatie_eenheid_id from lead

Revision ID: a1c2d3e4f5g6
Revises: b4711ce6b47c
Create Date: 2026-03-27 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c2d3e4f5g6"
down_revision: str | None = "b4711ce6b47c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Drop legacy organisatie_eenheid_id from lead
    op.drop_constraint("lead_organisatie_eenheid_id_fkey", "lead", type_="foreignkey")
    op.drop_index("ix_lead_organisatie_eenheid_id", table_name="lead")
    op.drop_column("lead", "organisatie_eenheid_id")

    # 2. Add missing indices for initiatief access control queries
    op.create_index(
        "ix_initiatief_member_person_id",
        "initiatief_member",
        ["person_id"],
    )
    op.create_index(
        "ix_initiatief_eenheid_eenheid_id",
        "initiatief_eenheid",
        ["eenheid_id"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_initiatief_created_by_id",
        "initiatief",
        ["created_by_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_initiatief_created_by_id", table_name="initiatief")
    op.drop_index(
        "ix_initiatief_eenheid_eenheid_id",
        table_name="initiatief_eenheid",
    )
    op.drop_index(
        "ix_initiatief_member_person_id",
        table_name="initiatief_member",
    )

    op.add_column(
        "lead",
        sa.Column("organisatie_eenheid_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        "ix_lead_organisatie_eenheid_id",
        "lead",
        ["organisatie_eenheid_id"],
    )
    op.create_foreign_key(
        "lead_organisatie_eenheid_id_fkey",
        "lead",
        "organisatie_eenheid",
        ["organisatie_eenheid_id"],
        ["id"],
        ondelete="SET NULL",
    )
