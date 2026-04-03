"""add fcc sync fields to opdracht and fcc_sync_log table

Revision ID: d91d47089680
Revises: a3b4c5d6e7f8
Create Date: 2026-03-30 16:54:37.785264

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d91d47089680"
down_revision: str | None = "a3b4c5d6e7f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create fcc_sync_log table
    op.create_table(
        "fcc_sync_log",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("opdracht_id", sa.UUID(), nullable=True),
        sa.Column(
            "direction",
            sa.String(),
            nullable=False,
            comment="inbound|outbound",
        ),
        sa.Column(
            "action",
            sa.String(),
            nullable=False,
            comment="created|updated|conflict|error",
        ),
        sa.Column(
            "details",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["opdracht_id"],
            ["opdracht.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_fcc_sync_log_opdracht_id",
        "fcc_sync_log",
        ["opdracht_id"],
    )

    # Add FCC sync columns to opdracht
    op.add_column(
        "opdracht",
        sa.Column("fcc_id", sa.String(), nullable=True),
    )
    op.add_column(
        "opdracht",
        sa.Column("fcc_entity_type", sa.String(), nullable=True),
    )
    op.add_column(
        "opdracht",
        sa.Column(
            "sync_status",
            sa.String(),
            nullable=True,
            comment="synced|pending_push|pending_pull|conflict|error",
        ),
    )
    op.add_column(
        "opdracht",
        sa.Column(
            "sync_direction",
            sa.String(),
            nullable=True,
            comment="inbound|outbound|bidirectional",
        ),
    )
    op.add_column(
        "opdracht",
        sa.Column(
            "fcc_raw_data",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "opdracht",
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "opdracht",
        sa.Column("fcc_modified_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Indexes and constraints
    op.create_index("ix_opdracht_fcc_id", "opdracht", ["fcc_id"], unique=True)
    op.create_check_constraint(
        "ck_opdracht_sync_status",
        "opdracht",
        "sync_status IS NULL OR sync_status IN "
        "('synced', 'pending_push', 'pending_pull', 'conflict', 'error')",
    )
    op.create_check_constraint(
        "ck_opdracht_sync_direction",
        "opdracht",
        "sync_direction IS NULL OR sync_direction IN "
        "('inbound', 'outbound', 'bidirectional')",
    )

    # Make instrument_id nullable for FCC-imported opdrachten
    op.alter_column("opdracht", "instrument_id", nullable=True)

    # Seed fcc:sync permission and assign to super_admin
    permission_table = sa.table(
        "permission",
        sa.column("id", sa.String),
        sa.column("category", sa.String),
    )
    op.bulk_insert(
        permission_table,
        [{"id": "fcc:sync", "category": "fcc"}],
    )
    # Assign to super_admin role
    role_permission_table = sa.table(
        "role_permission",
        sa.column("role_id", sa.String),
        sa.column("permission_id", sa.String),
    )
    op.bulk_insert(
        role_permission_table,
        [{"role_id": "super_admin", "permission_id": "fcc:sync"}],
    )


def downgrade() -> None:
    # Remove fcc:sync permission
    op.execute("DELETE FROM role_permission WHERE permission_id = 'fcc:sync'")
    op.execute("DELETE FROM permission WHERE id = 'fcc:sync'")

    # Restore instrument_id NOT NULL
    op.alter_column("opdracht", "instrument_id", nullable=False)

    # Remove constraints and indexes
    op.drop_constraint("ck_opdracht_sync_direction", "opdracht")
    op.drop_constraint("ck_opdracht_sync_status", "opdracht")
    op.drop_index("ix_opdracht_fcc_id", table_name="opdracht")

    # Remove FCC columns from opdracht
    op.drop_column("opdracht", "fcc_modified_at")
    op.drop_column("opdracht", "last_synced_at")
    op.drop_column("opdracht", "fcc_raw_data")
    op.drop_column("opdracht", "sync_direction")
    op.drop_column("opdracht", "sync_status")
    op.drop_column("opdracht", "fcc_entity_type")
    op.drop_column("opdracht", "fcc_id")

    # Drop fcc_sync_log table
    op.drop_index("ix_fcc_sync_log_opdracht_id", table_name="fcc_sync_log")
    op.drop_table("fcc_sync_log")
