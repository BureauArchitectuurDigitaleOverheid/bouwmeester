"""unify resource_permission with eenheid scope

Adds organisatie_eenheid_id to resource_permission, migrates
initiatief_eenheid data, and drops the initiatief_eenheid table.

Revision ID: b5e3c1a2f490
Revises: da29f7a85818
Create Date: 2026-03-30 08:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b5e3c1a2f490"
down_revision: str | None = "da29f7a85818"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Drop the old unique constraint and check constraint (if any)
    op.drop_constraint("uq_resource_permission", "resource_permission", type_="unique")

    # 2. Make person_id nullable
    op.alter_column(
        "resource_permission",
        "person_id",
        existing_type=sa.UUID(),
        nullable=True,
    )

    # 3. Add organisatie_eenheid_id column
    op.add_column(
        "resource_permission",
        sa.Column(
            "organisatie_eenheid_id",
            sa.UUID(),
            sa.ForeignKey("organisatie_eenheid.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_resource_permission_eenheid_id",
        "resource_permission",
        ["organisatie_eenheid_id"],
    )

    # 4. Add check constraint: exactly one of person_id or eenheid_id
    op.create_check_constraint(
        "ck_resource_permission_scope",
        "resource_permission",
        "(person_id IS NOT NULL AND organisatie_eenheid_id IS NULL)"
        " OR "
        "(person_id IS NULL AND organisatie_eenheid_id IS NOT NULL)",
    )

    # 5. New unique constraint including eenheid_id
    op.create_unique_constraint(
        "uq_resource_permission",
        "resource_permission",
        ["person_id", "organisatie_eenheid_id", "resource_type", "resource_id", "rol"],
    )

    # 6. Migrate initiatief_eenheid data into resource_permission
    op.execute("""
        INSERT INTO resource_permission
            (id, organisatie_eenheid_id, resource_type, resource_id, rol, created_at)
        SELECT
            gen_random_uuid(),
            eenheid_id,
            'initiatief',
            initiatief_id,
            rol,
            created_at
        FROM initiatief_eenheid
    """)

    # 7. Drop initiatief_eenheid table
    op.drop_table("initiatief_eenheid")


def downgrade() -> None:
    # 1. Recreate initiatief_eenheid table
    op.create_table(
        "initiatief_eenheid",
        sa.Column("initiatief_id", sa.UUID(), nullable=False),
        sa.Column("eenheid_id", sa.UUID(), nullable=False),
        sa.Column(
            "rol",
            sa.String(),
            server_default="contributor",
            nullable=False,
            comment="eigenaar|contributor|viewer",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
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

    # 2. Migrate data back
    op.execute("""
        INSERT INTO initiatief_eenheid (initiatief_id, eenheid_id, rol, created_at)
        SELECT resource_id, organisatie_eenheid_id, rol, created_at
        FROM resource_permission
        WHERE resource_type = 'initiatief'
          AND organisatie_eenheid_id IS NOT NULL
    """)

    # 3. Delete eenheid-scoped rows from resource_permission
    op.execute("""
        DELETE FROM resource_permission
        WHERE organisatie_eenheid_id IS NOT NULL
    """)

    # 4. Drop new constraints and column
    op.drop_constraint(
        "ck_resource_permission_scope", "resource_permission", type_="check"
    )
    op.drop_constraint("uq_resource_permission", "resource_permission", type_="unique")
    op.drop_index("ix_resource_permission_eenheid_id", "resource_permission")
    op.drop_column("resource_permission", "organisatie_eenheid_id")

    # 5. Make person_id NOT NULL again
    op.alter_column(
        "resource_permission",
        "person_id",
        existing_type=sa.UUID(),
        nullable=False,
    )

    # 6. Restore original unique constraint
    op.create_unique_constraint(
        "uq_resource_permission",
        "resource_permission",
        ["person_id", "resource_type", "resource_id", "rol"],
    )
