"""drop legacy manager_id and organisatie_eenheid_manager

Revision ID: 724a3a1f3435
Revises: bab492de98f7
Create Date: 2026-03-28 21:00:10.597077

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "724a3a1f3435"
down_revision: str | None = "bab492de98f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop the legacy manager_id FK and column from organisatie_eenheid.
    # Manager is now resolved from person_role (role_id='unit_manager').
    op.drop_constraint(
        "organisatie_eenheid_manager_id_fkey",
        "organisatie_eenheid",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_organisatie_eenheid_manager_id",
        table_name="organisatie_eenheid",
    )
    op.drop_column("organisatie_eenheid", "manager_id")

    # Drop the legacy temporal manager table.
    # History is now tracked via person_role start_datum/eind_datum.
    op.drop_table("organisatie_eenheid_manager")


def downgrade() -> None:
    # Recreate temporal manager table
    op.create_table(
        "organisatie_eenheid_manager",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "eenheid_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "manager_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("geldig_van", sa.Date(), nullable=False),
        sa.Column("geldig_tot", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["eenheid_id"],
            ["organisatie_eenheid.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["manager_id"],
            ["person.id"],
            ondelete="SET NULL",
        ),
    )

    # Recreate manager_id column on organisatie_eenheid
    op.add_column(
        "organisatie_eenheid",
        sa.Column(
            "manager_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "organisatie_eenheid_manager_id_fkey",
        "organisatie_eenheid",
        "person",
        ["manager_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_organisatie_eenheid_manager_id",
        "organisatie_eenheid",
        ["manager_id"],
    )
