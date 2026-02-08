"""add temporal org relations naam parent manager

Revision ID: f01b49dfb7ef
Revises: c43f045e002f
Create Date: 2026-02-08 20:46:07.433086

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f01b49dfb7ef"
down_revision: str | None = "c43f045e002f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- New temporal tables ---

    op.create_table(
        "organisatie_eenheid_naam",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("eenheid_id", sa.UUID(), nullable=False),
        sa.Column("naam", sa.String(), nullable=False),
        sa.Column("geldig_van", sa.Date(), nullable=False),
        sa.Column("geldig_tot", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["eenheid_id"],
            ["organisatie_eenheid.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_organisatie_eenheid_naam_eenheid_id",
        "organisatie_eenheid_naam",
        ["eenheid_id"],
    )
    op.create_index(
        "ix_org_naam_active",
        "organisatie_eenheid_naam",
        ["eenheid_id"],
        unique=True,
        postgresql_where=sa.text("geldig_tot IS NULL"),
    )

    op.create_table(
        "organisatie_eenheid_parent",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("eenheid_id", sa.UUID(), nullable=False),
        sa.Column("parent_id", sa.UUID(), nullable=False),
        sa.Column("geldig_van", sa.Date(), nullable=False),
        sa.Column("geldig_tot", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["eenheid_id"],
            ["organisatie_eenheid.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["organisatie_eenheid.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_organisatie_eenheid_parent_eenheid_id",
        "organisatie_eenheid_parent",
        ["eenheid_id"],
    )
    op.create_index(
        "ix_org_parent_active",
        "organisatie_eenheid_parent",
        ["eenheid_id"],
        unique=True,
        postgresql_where=sa.text("geldig_tot IS NULL"),
    )

    op.create_table(
        "organisatie_eenheid_manager",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("eenheid_id", sa.UUID(), nullable=False),
        sa.Column("manager_id", sa.UUID(), nullable=True),
        sa.Column("geldig_van", sa.Date(), nullable=False),
        sa.Column("geldig_tot", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_organisatie_eenheid_manager_eenheid_id",
        "organisatie_eenheid_manager",
        ["eenheid_id"],
    )
    op.create_index(
        "ix_org_manager_active",
        "organisatie_eenheid_manager",
        ["eenheid_id"],
        unique=True,
        postgresql_where=sa.text("geldig_tot IS NULL"),
    )

    # --- Add geldig_van/geldig_tot to anchor table ---

    op.add_column(
        "organisatie_eenheid",
        sa.Column(
            "geldig_van",
            sa.Date(),
            server_default=sa.text("CURRENT_DATE"),
            nullable=False,
        ),
    )
    op.add_column(
        "organisatie_eenheid",
        sa.Column("geldig_tot", sa.Date(), nullable=True),
    )

    # Update type comment to include cluster
    op.alter_column(
        "organisatie_eenheid",
        "type",
        existing_type=sa.VARCHAR(),
        comment=(
            "ministerie|directoraat_generaal|directie|afdeling|cluster|bureau|team"
        ),
        existing_comment=(
            "e.g. ministerie|directoraat_generaal|directie|dienst|bureau|afdeling|team"
        ),
        existing_nullable=False,
    )

    # --- Data migration: copy existing fields into temporal tables ---

    op.execute(
        """
        INSERT INTO organisatie_eenheid_naam (eenheid_id, naam, geldig_van)
        SELECT id, naam, created_at::date
        FROM organisatie_eenheid
        """
    )
    op.execute(
        """
        INSERT INTO organisatie_eenheid_parent (eenheid_id, parent_id, geldig_van)
        SELECT id, parent_id, created_at::date
        FROM organisatie_eenheid
        WHERE parent_id IS NOT NULL
        """
    )
    op.execute(
        """
        INSERT INTO organisatie_eenheid_manager
            (eenheid_id, manager_id, geldig_van)
        SELECT id, manager_id, created_at::date
        FROM organisatie_eenheid
        WHERE manager_id IS NOT NULL
        """
    )


def downgrade() -> None:
    # Drop temporal tables
    op.drop_index("ix_org_manager_active", table_name="organisatie_eenheid_manager")
    op.drop_index(
        "ix_organisatie_eenheid_manager_eenheid_id",
        table_name="organisatie_eenheid_manager",
    )
    op.drop_table("organisatie_eenheid_manager")

    op.drop_index("ix_org_parent_active", table_name="organisatie_eenheid_parent")
    op.drop_index(
        "ix_organisatie_eenheid_parent_eenheid_id",
        table_name="organisatie_eenheid_parent",
    )
    op.drop_table("organisatie_eenheid_parent")

    op.drop_index("ix_org_naam_active", table_name="organisatie_eenheid_naam")
    op.drop_index(
        "ix_organisatie_eenheid_naam_eenheid_id",
        table_name="organisatie_eenheid_naam",
    )
    op.drop_table("organisatie_eenheid_naam")

    # Remove geldig columns from anchor
    op.drop_column("organisatie_eenheid", "geldig_tot")
    op.drop_column("organisatie_eenheid", "geldig_van")

    # Restore type comment
    op.alter_column(
        "organisatie_eenheid",
        "type",
        existing_type=sa.VARCHAR(),
        comment=(
            "e.g. ministerie|directoraat_generaal|directie|dienst|bureau|afdeling|team"
        ),
        existing_comment=(
            "ministerie|directoraat_generaal|directie|afdeling|cluster|bureau|team"
        ),
        existing_nullable=False,
    )
