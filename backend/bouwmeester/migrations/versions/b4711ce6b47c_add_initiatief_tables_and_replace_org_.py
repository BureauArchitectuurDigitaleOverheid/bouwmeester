"""add initiatief tables and replace org_eenheid on lead

Revision ID: b4711ce6b47c
Revises: 16ce0b6e5fb6
Create Date: 2026-03-27 19:55:57.749812

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4711ce6b47c"
down_revision: str | None = "16ce0b6e5fb6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create initiatief table
    op.create_table(
        "initiatief",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("naam", sa.String(), nullable=False),
        sa.Column("beschrijving", sa.Text(), nullable=True),
        sa.Column("kleur", sa.String(), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["person.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("naam", name="uq_initiatief_naam"),
    )

    # 2. Create initiatief_member table
    op.create_table(
        "initiatief_member",
        sa.Column("initiatief_id", sa.UUID(), nullable=False),
        sa.Column("person_id", sa.UUID(), nullable=False),
        sa.Column(
            "rol",
            sa.String(),
            server_default="contributor",
            nullable=False,
            comment="eigenaar|contributor",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["initiatief_id"], ["initiatief.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("initiatief_id", "person_id"),
    )

    # 3. Create initiatief_eenheid table
    op.create_table(
        "initiatief_eenheid",
        sa.Column("initiatief_id", sa.UUID(), nullable=False),
        sa.Column("eenheid_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["initiatief_id"], ["initiatief.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["eenheid_id"], ["organisatie_eenheid.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("initiatief_id", "eenheid_id"),
    )

    # 4. Add initiatief_id column to lead (nullable for migration)
    op.add_column("lead", sa.Column("initiatief_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_lead_initiatief_id"), "lead", ["initiatief_id"])
    op.create_foreign_key(
        "fk_lead_initiatief",
        "lead",
        "initiatief",
        ["initiatief_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 5. Make organisatie_eenheid_id nullable (keep for now,
    #    drop in a later migration after data is migrated)
    op.alter_column(
        "lead",
        "organisatie_eenheid_id",
        existing_type=sa.UUID(),
        nullable=True,
    )


def downgrade() -> None:
    # Restore organisatie_eenheid_id to NOT NULL
    op.alter_column(
        "lead",
        "organisatie_eenheid_id",
        existing_type=sa.UUID(),
        nullable=False,
    )

    # Drop initiatief_id from lead
    op.drop_constraint("fk_lead_initiatief", "lead", type_="foreignkey")
    op.drop_index(op.f("ix_lead_initiatief_id"), table_name="lead")
    op.drop_column("lead", "initiatief_id")

    # Drop tables
    op.drop_table("initiatief_eenheid")
    op.drop_table("initiatief_member")
    op.drop_table("initiatief")
